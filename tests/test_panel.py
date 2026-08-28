from __future__ import annotations

from kalshi_mt.r1.panel import (
    basis_counts,
    build_doubled_panel,
    build_yes_only_panel,
    build_yes_only_panel_backfilled,
    price_band,
)
from kalshi_mt.store import db
from kalshi_mt.store.parquet import TradeStore


def _seed_market_with_panel(conn, ticker, *, result="yes", category="Weather",
                             lookback_prices=None):
    lookback_prices = lookback_prices if lookback_prices is not None else {0: 0.9}
    db.upsert_market(conn, {
        "ticker": ticker, "result": result, "category": category,
        "close_time_epoch": 1000, "in_r1_window": 1,
    })
    for day, price in lookback_prices.items():
        db.upsert_price_panel_row(conn, {
            "ticker": ticker, "lookback_day": day, "trade_id": f"t{day}",
            "yes_price_dollars": price, "created_time": "2022-01-01T00:00:00Z", "source": "live",
        })
    conn.commit()


def test_build_yes_only_panel_basic(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed_market_with_panel(conn, "A-1", result="yes", lookback_prices={0: 0.9, 1: 0.85})
    df = build_yes_only_panel(conn, {"A-1"})
    assert len(df) == 2
    assert set(df["side"].to_list()) == {"yes"}
    assert set(df["y"].to_list()) == {1.0}


def test_build_yes_only_panel_no_outcome(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed_market_with_panel(conn, "A-1", result="no", lookback_prices={0: 0.1})
    df = build_yes_only_panel(conn, {"A-1"})
    row = df.row(0, named=True)
    assert row["y"] == 0.0
    assert row["p"] == 0.1


def test_build_yes_only_panel_excludes_unresolved_markets(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed_market_with_panel(conn, "PENDING", result="")
    df = build_yes_only_panel(conn, {"PENDING"})
    assert df.is_empty()


def test_build_yes_only_panel_excludes_out_of_scope_tickers(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed_market_with_panel(conn, "IN-SCOPE")
    _seed_market_with_panel(conn, "OUT-OF-SCOPE")
    df = build_yes_only_panel(conn, {"IN-SCOPE"})
    assert len(df) == 1
    assert df["ticker"][0] == "IN-SCOPE"


def test_build_yes_only_panel_empty_scope(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed_market_with_panel(conn, "A-1")
    df = build_yes_only_panel(conn, set())
    assert df.is_empty()


def test_build_doubled_panel_complements_price_and_outcome(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed_market_with_panel(conn, "A-1", result="yes", lookback_prices={0: 0.9})
    yes_only = build_yes_only_panel(conn, {"A-1"})
    doubled = build_doubled_panel(yes_only)
    assert len(doubled) == 2
    sides = {row["side"]: row for row in doubled.iter_rows(named=True)}
    assert sides["yes"]["p"] == 0.9
    assert sides["yes"]["y"] == 1.0
    assert abs(sides["no"]["p"] - 0.1) < 1e-9
    assert sides["no"]["y"] == 0.0


def test_build_doubled_panel_empty_input(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    df = build_yes_only_panel(conn, set())
    doubled = build_doubled_panel(df)
    assert doubled.is_empty()


def test_basis_counts_invariant_holds(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed_market_with_panel(conn, "A-1", lookback_prices={0: 0.9, 1: 0.5, 2: 0.4})
    yes_only = build_yes_only_panel(conn, {"A-1"})
    doubled = build_doubled_panel(yes_only)
    counts = basis_counts(yes_only, doubled)
    assert counts["yes_only_n"] == 3
    assert counts["doubled_n"] == 6
    assert counts["doubled_equals_2x_yes_only"] is True


def test_price_band_boundaries():
    assert price_band(0.01) == "1-10c"
    assert price_band(0.10) == "1-10c"
    assert price_band(0.11) == "11-20c"
    assert price_band(0.50) == "41-50c"
    assert price_band(0.51) == "51-60c"
    assert price_band(0.99) == "91-99c"
    assert price_band(0.91) == "91-99c"


# ---------------------------------------------------------------------------
# build_yes_only_panel_backfilled -- the PRIMARY construction since the
# 2026-07-26 amendment to CLAUDE.md S3. Built from Pass 2's tape, so the
# fixtures here seed trades, not price_panel rows.
# ---------------------------------------------------------------------------

def _tape_trade(ticker, trade_id, created_time, price):
    return {
        "trade_id": trade_id, "ticker": ticker, "count_fp": 10.0,
        "yes_price_dollars": price, "no_price_dollars": round(1 - price, 4),
        "taker_outcome_side": "yes", "taker_book_side": "yes", "taker_side": "yes",
        "created_time": created_time, "is_block_trade": False, "source": "historical",
    }


def _close_epoch(iso):
    from kalshi_mt.util import iso_to_epoch
    return iso_to_epoch(iso)


def test_backfilled_panel_carries_the_last_price_across_a_silent_day(tmp_path):
    """The rule the amendment turns on: a lookback day with no trade of its own
    takes the last known price forward instead of vanishing. Trades exist only
    on the closing day and 3 ET days earlier, so the two intervening days must
    still produce rows, all carrying the older price."""
    conn = db.connect(tmp_path / "t.db")
    store = TradeStore(tmp_path / "parquet")
    close_iso = "2024-06-20T20:00:00Z"
    db.upsert_market(conn, {
        "ticker": "A-1", "event_ticker": "EVT-1", "result": "yes", "category": "Weather",
        "close_time_epoch": _close_epoch(close_iso), "in_r1_window": 1,
    })
    conn.commit()
    store.append([
        _tape_trade("A-1", "t-close", "2024-06-20T19:00:00Z", 0.80),
        _tape_trade("A-1", "t-old", "2024-06-17T19:00:00Z", 0.40),
    ])

    panel = build_yes_only_panel_backfilled(conn, store, {"A-1"})
    by_day = {r["lookback_day"]: r["p"] for r in panel.to_dicts()}
    assert by_day[0] == 0.80                       # closing-day trade
    assert by_day[1] == 0.40 and by_day[2] == 0.40  # silent days carry it forward
    assert by_day[3] == 0.40                       # the older trade's own day
    # Nothing before the first trade ever existed.
    assert max(by_day) == 3


def test_backfilled_panel_keeps_a_contract_with_no_closing_day_trade(tmp_path):
    """Under the skip rule this contract contributes NOTHING -- its last trade
    missed the closing ET day, and fetch_price_panel is all-or-nothing. That is
    21.2% of the in-scope universe, so retaining them is most of why the
    contract count moves from 25,803 to 32,728."""
    conn = db.connect(tmp_path / "t.db")
    store = TradeStore(tmp_path / "parquet")
    db.upsert_market(conn, {
        "ticker": "STALE", "event_ticker": "EVT-1", "result": "no", "category": "Weather",
        "close_time_epoch": _close_epoch("2024-06-20T20:00:00Z"), "in_r1_window": 1,
    })
    conn.commit()
    # Only trade is days before the close -- nothing on the closing ET day.
    store.append([_tape_trade("STALE", "t-old", "2024-06-15T12:00:00Z", 0.25)])

    panel = build_yes_only_panel_backfilled(conn, store, {"STALE"})
    assert not panel.is_empty()
    assert panel.to_dicts()[0]["p"] == 0.25
    assert panel.to_dicts()[0]["y"] == 0.0  # result 'no'


def test_backfilled_panel_excludes_unresolved_and_out_of_scope(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    store = TradeStore(tmp_path / "parquet")
    for ticker, result in (("RESOLVED", "yes"), ("PENDING", None)):
        db.upsert_market(conn, {
            "ticker": ticker, "event_ticker": "EVT-1", "result": result, "category": "Weather",
            "close_time_epoch": _close_epoch("2024-06-20T20:00:00Z"), "in_r1_window": 1,
        })
        store.append([_tape_trade(ticker, f"{ticker}-t", "2024-06-20T19:00:00Z", 0.6)])
    conn.commit()

    tickers = {r["ticker"] for r in build_yes_only_panel_backfilled(conn, store, {"RESOLVED", "PENDING"}).to_dicts()}
    assert tickers == {"RESOLVED"}          # unresolved contributes nothing
    assert build_yes_only_panel_backfilled(conn, store, set()).is_empty()


def test_backfilled_panel_yields_more_rows_than_the_skip_rule(tmp_path):
    """The headline of the amendment, as a property rather than a number: on
    the same market the backfilled panel is never shallower than skip, and here
    strictly deeper."""
    conn = db.connect(tmp_path / "t.db")
    store = TradeStore(tmp_path / "parquet")
    close_iso = "2024-06-20T20:00:00Z"
    db.upsert_market(conn, {
        "ticker": "A-1", "event_ticker": "EVT-1", "result": "yes", "category": "Weather",
        "close_time_epoch": _close_epoch(close_iso), "in_r1_window": 1,
    })
    # Skip-rule panel as Pass 1 would have stored it: only the two days that
    # actually had trades.
    for day, price, iso in ((0, 0.80, "2024-06-20T19:00:00Z"), (3, 0.40, "2024-06-17T19:00:00Z")):
        db.upsert_price_panel_row(conn, {
            "ticker": "A-1", "lookback_day": day, "trade_id": f"t{day}",
            "yes_price_dollars": price, "created_time": iso, "source": "historical",
        })
    conn.commit()
    store.append([
        _tape_trade("A-1", "t-close", "2024-06-20T19:00:00Z", 0.80),
        _tape_trade("A-1", "t-old", "2024-06-17T19:00:00Z", 0.40),
    ])

    skip = build_yes_only_panel(conn, {"A-1"})
    backfilled = build_yes_only_panel_backfilled(conn, store, {"A-1"})
    assert len(skip) == 2
    assert len(backfilled) == 4
    assert len(backfilled) > len(skip)
