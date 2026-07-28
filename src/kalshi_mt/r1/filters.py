"""R1 filters (spec S1): volume>=$1k, spread<=20c, open>=24h, and a
settlement-consistency check. Operates on markets already discovered by Pass 1
(store/db.py's markets/quotes/price_panel tables), restricted to the R1 window
(2021-01-01..2025-04-30).

THE 63-MISMATCH FILTER CANNOT BE REPRODUCED, and that is a finding rather than
a gap to paper over (re-pinned 2026-07-28; the spec's own placeholder asked for
"the exact field behind 'separately-reported' -- settlement price vs last
price"). BDW drop 63 of 46,282 Yes contracts, 0.136%, "for mismatch vs Kalshi's
separately-reported final prices". Every reading available from Kalshi's public
fields was measured against that rate on our own R1 universe
(`tools/measure_mismatch_filter.py`):

    reading                                          rate      vs BDW
    proxy: result vs side implied by last trade      0.000%     never fires
    tape day-0 price vs Kalshi last_price, >=1c      4.345%     32x too many
    ...same, >25c                                    0.090%     0.7x (arbitrary threshold)
    settlement value vs result                       0.003%     45x too few

The proxy is what this module used until now, and it is INERT: it asks whether
the final trade landed on the winning side, and by the close a market's price
has already converged to its outcome, so it fired zero times in 25,803
contracts. It never removed anything, and it never would.

The price comparison is the closest in spirit but does not survive scrutiny as
a filter: the two quantities differ by DEFINITION (our "last trade at or before
close_time" against Kalshi's own last-price snapshot), so a disagreement is not
evidence of an error, and only an arbitrary threshold brings its rate near
BDW's. Tuning that threshold to land on 63 would be fitting a filter whose
definition we do not know to a number we do.

What IS implemented is the one unambiguous data error available: Kalshi's own
separately-reported SETTLEMENT VALUE contradicting its own `result` for the
same contract. Binary, no tolerance, no judgment. It catches 1 contract in
32,728.

So we retain contracts BDW dropped. At 0.136% of their sample that difference
cannot move any reported quantity, and it is logged as a divergence rather than
hidden -- see DIVERGENCE_NOTES and docs/r1_reproduction_findings.md.

The price comparison is kept, but as a VALIDATION rather than a filter, and it
is a strong one: 95.7% of our tape-derived closing prices match Kalshi's
independently reported final price to the cent, with the median, p90 and p95
differences all exactly 0.0000. That is independent evidence that the tape
reconstruction is right.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kalshi_mt.store import db

# 1000 in whichever unit the active volume reading uses -- see
# VOLUME_READING_PIN. Deliberately one constant: the two readings differ in
# UNITS, not in the threshold BDW wrote down.
MIN_VOLUME_FP = 1000.0
MAX_SPREAD = 0.20
MIN_OPEN_SECONDS = 24 * 3600

# universe_log label for the dollar-notional sensitivity branch. Must NOT be
# 'r1': in-scope is computed as "NOT IN universe_log WHERE window = 'r1'", so
# logging a second branch under that label would silently shrink the primary
# analysis universe by the other reading's exclusions.
DOLLAR_BRANCH_LOG_WINDOW = "r1_dollar_volume"

VOLUME_READING_PIN = """Volume filter, pinned 2026-07-26 after the first real gate run.

BDW write "total traded volume at closure >= $1,000", which reads as dollar
notional. Kalshi's `volume` field, however, is denominated in CONTRACTS and the
API exposes no notional field; because a contract settles at $1 the two are
nearly indistinguishable in prose, so "volume >= 1000" turns into "$1,000"
easily. The choice is not settled by guessing their intent -- psi is only
comparable on a comparable sample, and a construction that systematically
drops cheap strikes yields a different psi BY CONSTRUCTION, which would make
R1 say nothing about their result.

Measured, on our own independently collected R1 universe, at the
volume>=1000-CONTRACTS stage (before the 24h and spread filters):

    contracts  44,946  vs BDW 46,282   (-2.9%)
    events     12,416  vs BDW 12,403   (+0.1%)

A 0.1% event match on independently collected data is not coincidence, so the
CONTRACT reading is PRIMARY. The dollar-notional reading is retained as a
reported sensitivity branch, not discarded: it is the literal text, and under
it the sample roughly halves (13,632 contracts / 39,818 prices), which is
itself a finding -- a sample rule in a favorite-longshot-bias paper that
differentially removes longshots.

What the switch does NOT fix, and must not be presented as fixing: prices per
contract stays near 2.5 against BDW's implied 3.39, and events after our 24h
and spread filters stay near 10k against their 12,403. See DIVERGENCE_NOTES.
"""

DIVERGENCE_NOTES = """Known R1 construction divergences beyond the volume reading.

1. Structural spread-filter loss (8.2%). Of the 39,794 markets clearing
   volume+24h, 3,257 (8.2%) have a quote row whose spread is NULL -- Kalshi
   genuinely serves no bid/ask history for them (Step Zero Check 5's PARTIAL
   finding), so this cannot shrink by fetching more. Only 11 markets (0.0%)
   are merely not-yet-fetched, so the shortfall is not an artifact of
   incomplete collection. BDW did not lose these.

2. Skip-vs-backfill on no-trade lookback days -- MEASURED 2026-07-26, and it
   turns out to drive BOTH the depth gap and a fifth of the contract gap.

   This repo's pinned rule is "on a no-trade lookback day, SKIP (no
   backfill)", matching a last-trade-BEFORE-time construction. Projecting the
   alternative from data already on disk (day-0 anchors from price_panel,
   first-trade times from Pass 2's tape, production's own ET helpers -- no
   refetch):

       our skip rule        64,614 prices   2.50 per contract
       backfill (projected) 90,277 prices   3.50 per contract
       BDW                 156,986 prices   3.39 per contract

   3.50 against their 3.39 is a 3.2% match, versus 26% low under skip. And it
   is not only depth: the same rule applied at day 0 drops whole contracts.
   Of 32,728 in-scope contracts, 6,925 (21.2%) have NO panel row at all, and
   exactly 0 have rows without a day-0 row -- fetch_price_panel is
   all-or-nothing, so a contract whose last trade fell outside its closing ET
   calendar day contributes nothing. Under backfill those 6,925 would carry a
   price forward and be retained, taking contracts from 25,803 to 32,728.

   So BDW very likely carried prices forward. Combined projection: ~32,728
   contracts and ~114,500 prices, i.e. -29%/-27% against their integers
   rather than -44%/-59%. Deliberately NOT changed here -- it is a pinned
   construction choice, and the volume filter's own re-pin showed why these
   are decided on measurement and reported as branches, not switched quietly.

3. Residual after both of the above: contracts ~32.7k vs 46,282. Our funnel
   loses 5,152 to the 24h filter and 6,555 to the spread filter (3,298
   genuinely wide, 3,257 structurally uncomputable per item 1), off 44,946 at
   the volume stage. For BDW to report 46,282 AFTER those same filters, their
   spread and duration filters must have bitten far less than ours -- which
   for the spread half is exactly the bid/ask-history asymmetry of item 1.
"""


@dataclass
class FilterResult:
    ticker: str
    passed: bool
    reason_codes: list[str] = field(default_factory=list)


def _settlement_contradicts_result(result: str | None, settlement_value: float | None) -> bool:
    """Kalshi's own separately-reported settlement value disagreeing with its
    own categorical `result` for the same contract. Settlement is binary in
    this universe (measured: 24,124 rows at 0.0 and 8,604 at 1.0, nothing
    else), so 'contradicts' is unambiguous and needs no tolerance.

    Unknowable rather than false when either field is missing: a contract we
    cannot check is not a contract we have caught out."""
    if result not in ("yes", "no") or settlement_value is None:
        return False
    return (result == "yes") != (float(settlement_value) >= 0.5)


def apply_r1_filters(
    conn, window: str = "r1", dollar_volume_by_ticker: dict[str, float] | None = None,
) -> list[FilterResult]:
    """One row per market in the given window (`in_r1_window` or
    `in_r2_window`) that Pass 1 has reached at least once (has a markets
    row). Same filter thresholds for both windows -- analysis_plan.md S2's
    R2 spec is described as an extension of R1's own construction, with no
    separate filter definition restated, so R2 reuses R1's volume/spread/
    duration/settlement-mismatch criteria unchanged, applied to the R2
    window's markets. A market with no quote row yet fails on
    'spread_filter_not_yet_fetched' (operational -- Pass 1 hasn't attempted
    it); a market whose quote WAS attempted (live+historical) but Kalshi had
    no bid/ask history fails on 'spread_filter_not_computable' (structural --
    won't resolve by fetching more, per Step Zero Check 5's own finding).
    Neither is silently skipped -- incomplete Pass 1 coverage should be
    visible in the reconciliation counts, split by which of the two it is
    (reconcile.py's coverage_gap_breakdown), not swallowed into one bucket.

    A market whose stored `result` is neither 'yes' nor 'no' -- Pass 1's
    live sweep upserts status/result fields that are documented as
    "frequently stale for older markets" (fetch/pass1.py's module
    docstring), and no re-derivation from trade/settlement evidence is
    implemented yet (2026-07-21 audit finding, deferred pending a design
    decision on what "re-derive" means) -- now fails on
    'result_missing_or_invalid' rather than silently passing here only to
    be dropped later, invisibly, by r1/panel.py's `WHERE result IN
    ('yes','no')`. This does not change which contracts end up in the
    final panel; it makes an already-happening drop visible in
    universe_log/reconcile.py's coverage_gap_breakdown instead of an
    unattributed shortfall against BDW's 156,986.

    `dollar_volume_by_ticker` selects WHICH READING of BDW's volume filter to
    apply, and the two are not ranked as approximation-vs-truth (they were
    until 2026-07-26; VOLUME_READING_PIN above has the measurement that
    re-ranked them):

      None  -> CONTRACT reading, thresholding Kalshi's own `volume_fp`. This
               is the PINNED PRIMARY: at this stage our independently
               collected R1 universe lands within 0.1% of BDW's 12,403 events
               and 2.9% of their 46,282 contracts.
      dict  -> DOLLAR-NOTIONAL reading (store/parquet.py's
               TradeStore.dollar_volume_by_ticker(), summed from Pass 2's real
               tape). The literal text of the paper, kept as a reported
               SENSITIVITY branch. Since every trade price is <$1,
               count>=1000 admits notional under $1000, so this reading
               removes cheap strikes -- roughly halving the sample, and
               concentrated in exactly the tail bins the FLB headline rests
               on. A market Pass 2 hasn't finished (no 'done' pass2_progress
               row) fails 'dollar_volume_not_yet_fetched' (operational,
               mirroring the spread_filter split) rather than being silently
               treated as below threshold.

    cli.py's `build` runs BOTH and reports both; only the primary writes the
    universe_log label the analysis universe is derived from."""
    window_column = {"r1": "in_r1_window", "r2": "in_r2_window"}[window]
    rows = conn.execute(
        f"""
        SELECT m.ticker, m.volume_fp, m.open_time_epoch, m.close_time_epoch, m.result,
               m.settlement_value_dollars,
               q.spread, (q.ticker IS NOT NULL) AS quote_attempted,
               p.status AS pass2_status
        FROM markets m
        LEFT JOIN quotes q ON q.ticker = m.ticker
        LEFT JOIN pass2_progress p ON p.ticker = m.ticker
        WHERE m.{window_column} = 1
        """
    ).fetchall()

    results = []
    for row in rows:
        reasons = []
        if dollar_volume_by_ticker is None:
            if row["volume_fp"] is None or row["volume_fp"] < MIN_VOLUME_FP:
                reasons.append("volume_below_1000")
        elif row["pass2_status"] != "done":
            reasons.append("dollar_volume_not_yet_fetched")
        elif dollar_volume_by_ticker.get(row["ticker"], 0.0) < MIN_VOLUME_FP:
            reasons.append("volume_below_1000")
        if not row["quote_attempted"]:
            reasons.append("spread_filter_not_yet_fetched")
        elif row["spread"] is None:
            reasons.append("spread_filter_not_computable")
        elif row["spread"] > MAX_SPREAD:
            reasons.append("spread_above_20c")
        if row["open_time_epoch"] is None or row["close_time_epoch"] is None:
            reasons.append("missing_open_or_close_time")
        elif (row["close_time_epoch"] - row["open_time_epoch"]) < MIN_OPEN_SECONDS:
            reasons.append("open_below_24h")
        if row["result"] not in ("yes", "no"):
            reasons.append("result_missing_or_invalid")
        elif _settlement_contradicts_result(row["result"], row["settlement_value_dollars"]):
            reasons.append("settlement_contradicts_result")
        results.append(FilterResult(ticker=row["ticker"], passed=not reasons, reason_codes=reasons))
    return results


def summarize(results: list[FilterResult]) -> dict[str, Any]:
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    reason_counts: dict[str, int] = {}
    for r in results:
        for code in r.reason_codes:
            reason_counts[code] = reason_counts.get(code, 0) + 1
    return {"total": total, "passed": passed, "failed": total - passed, "reason_counts": reason_counts}


def apply_and_log(
    conn, window: str = "r1", dollar_volume_by_ticker: dict[str, float] | None = None,
    log_window: str | None = None,
) -> dict[str, Any]:
    """Runs the filters and persists every exclusion to universe_log
    (spec-wide defense against selection-bias claims -- see db.py's own
    universe_log docstring). See apply_r1_filters for
    `dollar_volume_by_ticker`.

    `log_window` decouples the universe_log LABEL from the window column
    `window` selects, so a sensitivity branch can be logged without polluting
    the primary universe: in-scope is computed as "NOT IN universe_log WHERE
    window = 'r1'" (an exact match), so logging the dollar-notional branch
    under e.g. 'r1_dollar_volume' keeps both queryable while leaving the
    primary analysis set untouched. Defaults to `window`, i.e. the primary."""
    results = apply_r1_filters(conn, window=window, dollar_volume_by_ticker=dollar_volume_by_ticker)
    exclusions = [
        (r.ticker, code) for r in results if not r.passed for code in r.reason_codes
    ]
    db.replace_universe_exclusions(conn, log_window or window, exclusions)
    conn.commit()
    return summarize(results)
