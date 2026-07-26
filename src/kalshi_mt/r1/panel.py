"""R1 price panel construction (spec S1): turns Pass 1's raw boundary-tick
fetches (the `price_panel` SQLite table) into the two panels the rest of R1
consumes -- Yes-only (the regression basis) and doubled Yes+No (the
descriptive-statistics basis, spec's own basis-tagging rule).

Two constructions, differing in ONE rule -- what happens on a lookback day
with no trade (CLAUDE.md S3, amended 2026-07-26):

  build_yes_only_panel_backfilled  PRIMARY. Carries the last known price
      forward. Reproduces BDW's own 3.39 prices per contract (we measure 3.50);
      built from Pass 2's tape, so no refetch and no same-ET-day restriction.
  build_yes_only_panel             SENSITIVITY. Skips the day, reading Pass 1's
      stored `price_panel` rows as-is. The natural reading of BDW's prose, but
      it yields 2.50 per contract and silently drops the 21.2% of contracts
      whose last trade missed their closing ET day entirely.

The 11-row-per-market boundary-tick FETCH that feeds the sensitivity branch is
Pass 1's job (fetch/pass1.py's fetch_price_panel -- it needs live API access).
This module makes no API calls: the primary branch reads Pass 2's Parquet tape,
the sensitivity branch reads what Pass 1 already wrote.
"""

from __future__ import annotations

from typing import Any

import polars as pl

from kalshi_mt.util import epoch_to_et, et_to_epoch, shift_et_calendar_days

PANEL_SCHEMA = {
    "ticker": pl.String,
    "event_ticker": pl.String,  # the event-clustering key (spec S4's clustering unit)
    "lookback_day": pl.Int64,
    "category": pl.String,
    "close_time_epoch": pl.Int64,
    "side": pl.String,  # 'yes' | 'no'
    "y": pl.Float64,    # realized outcome for this side, 0.0 or 1.0
    "p": pl.Float64,    # market probability for this side, (0, 1)
    "source": pl.String,  # 'live' | 'historical' | 'tape' -- which family answered
    # Order size of the fill this row came from. Load-bearing for fees, not
    # decoration: the fee model rounds the ORDER TOTAL up to the next cent,
    # so assuming 1 contract inflates the effective rate up to 14x at 1c
    # (spec S1: "compute fees on actual per-order contract counts").
    # None on the skip-rule panel -- price_panel never stored it.
    "count_fp": pl.Float64,
    # Which outcome side the TAKER was on in the trade that set this price.
    # BDW attribute every panel observation to a Maker or a Taker from this
    # (their Table 10: 313,972 doubled observations, Makers exactly 156,986
    # -- one role per side). None on the skip-rule panel.
    "taker_outcome_side": pl.String,
}


def build_yes_only_panel(conn, in_scope_tickers: set[str]) -> pl.DataFrame:
    """One row per (ticker, lookback_day) price-panel observation, Yes-only
    basis -- spec S1's regression n (156,986 in BDW's own reproduction
    target). Requires a resolved result (yes/no); a market still pending or
    disputed-without-resolution contributes no rows, same as BDW's own
    resolved-markets-only construction."""
    if not in_scope_tickers:
        return pl.DataFrame(schema=PANEL_SCHEMA)

    rows = conn.execute(
        """
        SELECT p.ticker, p.lookback_day, p.yes_price_dollars, p.source,
               m.result, m.close_time_epoch, m.category, m.event_ticker
        FROM price_panel p
        JOIN markets m ON m.ticker = p.ticker
        WHERE m.result IN ('yes', 'no')
        """
    ).fetchall()

    records: list[dict[str, Any]] = []
    for r in rows:
        if r["ticker"] not in in_scope_tickers or r["yes_price_dollars"] is None:
            continue
        records.append({
            "ticker": r["ticker"], "event_ticker": r["event_ticker"],
            "lookback_day": r["lookback_day"], "category": r["category"],
            "close_time_epoch": r["close_time_epoch"], "side": "yes",
            "y": 1.0 if r["result"] == "yes" else 0.0, "p": r["yes_price_dollars"],
            "source": r["source"], "count_fp": None, "taker_outcome_side": None,
        })
    return pl.DataFrame(records, schema=PANEL_SCHEMA) if records else pl.DataFrame(schema=PANEL_SCHEMA)


PANEL_LOOKBACK_DAYS = 10


def build_yes_only_panel_backfilled(conn, trade_store, in_scope_tickers: set[str]) -> pl.DataFrame:
    """The PRIMARY R1 panel construction since the 2026-07-26 amendment to
    CLAUDE.md S3: on a lookback day with no trade, carry the last known price
    forward instead of skipping the day.

    Why this rather than `build_yes_only_panel`'s skip rule: BDW's own reported
    n settles it. 156,986 prices / 46,282 contracts = 3.39 prices per contract,
    which skip cannot reach -- measured, skip gives 2.50 and backfill 3.50 on
    our universe. The skip rule also drops whole contracts, not just rows: 21.2%
    of in-scope contracts have no closing-ET-day trade and so contribute
    nothing at all under skip.

    Built from Pass 2's full tape, NOT from the `price_panel` table, and so
    needs no refetch. That also makes it exact rather than approximate: the
    stored panel only holds the days Pass 1's guard accepted, so carrying
    forward from those rows would inherit their same-ET-day restriction, while
    the tape supports the literal "last trade at or before this instant".

    Anchoring follows the existing pin unchanged -- day 0's own trade timestamp
    is the reference clock for every later day, not close_time -- so this
    changes ONE construction rule, not two."""
    if not in_scope_tickers:
        return pl.DataFrame(schema=PANEL_SCHEMA)

    markets = {
        r["ticker"]: r
        for r in conn.execute(
            """
            SELECT ticker, event_ticker, category, close_time_epoch, result
            FROM markets
            WHERE result IN ('yes', 'no') AND close_time_epoch IS NOT NULL
            """
        ).fetchall()
        if r["ticker"] in in_scope_tickers
    }
    if not markets:
        return pl.DataFrame(schema=PANEL_SCHEMA)

    # Day 0: last trade at or before close. No same-ET-day guard -- that guard
    # is exactly what the amendment removes, and it is what was dropping 21.2%
    # of contracts outright.
    day0 = trade_store.last_trade_at_or_before(
        [(t, 0, m["close_time_epoch"]) for t, m in markets.items()]
    )

    # Days 1..10: reference instants walked back from day 0's OWN timestamp, in
    # ET calendar days, via the same helpers fetch/pass1.py uses.
    refs: list[tuple[str, int, int]] = []
    for (ticker, _key), (_price, t0_epoch, _count, _tk) in day0.items():
        t0_et = epoch_to_et(t0_epoch)
        for day in range(1, PANEL_LOOKBACK_DAYS + 1):
            refs.append((ticker, day, et_to_epoch(shift_et_calendar_days(t0_et, day))))
    later = trade_store.last_trade_at_or_before(refs) if refs else {}

    records: list[dict[str, Any]] = []
    for (ticker, day), (price, _created, count, taker_side) in {**day0, **later}.items():
        if price is None:
            continue
        m = markets[ticker]
        records.append({
            "ticker": ticker, "event_ticker": m["event_ticker"],
            "lookback_day": day, "category": m["category"],
            "close_time_epoch": m["close_time_epoch"], "side": "yes",
            "y": 1.0 if m["result"] == "yes" else 0.0, "p": price,
            "source": "tape", "count_fp": count, "taker_outcome_side": taker_side,
        })
    return pl.DataFrame(records, schema=PANEL_SCHEMA) if records else pl.DataFrame(schema=PANEL_SCHEMA)


def build_doubled_panel(yes_only: pl.DataFrame) -> pl.DataFrame:
    """Yes-only panel plus its complementary No-side rows (No price = 1 -
    Yes price, No outcome = 1 - Yes outcome) -- spec's doubled basis for
    descriptive statistics (win-rate curve, tail-bin counts, maker/taker
    split). Never the MZ regression's own input -- that stays Yes-only."""
    if yes_only.is_empty():
        return yes_only
    no_side = yes_only.with_columns([
        pl.lit("no").alias("side"),
        (1.0 - pl.col("y")).alias("y"),
        (1.0 - pl.col("p")).alias("p"),
    ])
    return pl.concat([yes_only, no_side], how="vertical")


def price_band(p: float) -> str:
    """10c band label, e.g. '1-10c', '90-99c' -- BDW's own Fig 3/5 binning.
    Prices are probabilities in (0,1); bands follow their 1-indexed cent
    convention (a price of exactly 0.10 falls in the 1-10c band, matching
    "contracts <=10c" language, not a fresh 10-20c band)."""
    cents = p * 100.0
    if cents <= 10:
        return "1-10c"
    if cents <= 20:
        return "11-20c"
    if cents <= 30:
        return "21-30c"
    if cents <= 40:
        return "31-40c"
    if cents <= 50:
        return "41-50c"
    if cents <= 60:
        return "51-60c"
    if cents <= 70:
        return "61-70c"
    if cents <= 80:
        return "71-80c"
    if cents <= 90:
        return "81-90c"
    return "91-99c"


def basis_counts(yes_only: pl.DataFrame, doubled: pl.DataFrame) -> dict[str, int]:
    """The basis-tagging invariant, checkable at build time: doubled count
    must be exactly 2x the Yes-only count (spec S1: 156,986 -> 313,972)."""
    return {
        "yes_only_n": len(yes_only),
        "doubled_n": len(doubled),
        "doubled_equals_2x_yes_only": len(doubled) == 2 * len(yes_only),
    }
