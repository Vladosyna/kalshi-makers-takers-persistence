from __future__ import annotations

from kalshi_mt.r1.filters import (
    DOLLAR_BRANCH_LOG_WINDOW,
    MIN_OPEN_SECONDS,
    apply_and_log,
    apply_r1_filters,
    summarize,
)
from kalshi_mt.store import db


def _seed(conn, ticker, *, volume_fp=2000.0, spread=0.05, open_epoch=0,
          close_epoch=2 * 86400, result="yes", day0_price=0.9, in_r1=1, with_quote=True,
          settlement_value=None):
    # settlement_value defaults to whatever `result` says, so a test that does
    # not care about the settlement-consistency check never trips it.
    if settlement_value is None and result in ("yes", "no"):
        settlement_value = 1.0 if result == "yes" else 0.0
    db.upsert_market(conn, {
        "ticker": ticker, "volume_fp": volume_fp, "open_time_epoch": open_epoch,
        "close_time_epoch": close_epoch, "result": result, "in_r1_window": in_r1,
        "settlement_value_dollars": settlement_value,
    })
    if with_quote:
        db.upsert_quote(conn, {
            "ticker": ticker, "end_period_ts": close_epoch, "yes_bid_close": 0.45,
            "yes_ask_close": 0.45 + spread, "spread": spread, "source": "live",
        })
    if day0_price is not None:
        db.upsert_price_panel_row(conn, {
            "ticker": ticker, "lookback_day": 0, "trade_id": "t0",
            "yes_price_dollars": day0_price, "created_time": "2022-01-01T00:00:00Z", "source": "live",
        })
    conn.commit()


def test_market_passing_every_filter(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "OK-1")
    results = apply_r1_filters(conn)
    assert len(results) == 1
    assert results[0].passed is True
    assert results[0].reason_codes == []


def test_low_volume_fails(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "LOW-VOL", volume_fp=500.0)
    r = apply_r1_filters(conn)[0]
    assert r.passed is False
    assert "volume_below_1000" in r.reason_codes


def test_wide_spread_fails(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "WIDE", spread=0.25)
    r = apply_r1_filters(conn)[0]
    assert "spread_above_20c" in r.reason_codes


def test_no_quote_row_at_all_fails_as_not_yet_fetched(tmp_path):
    """No `quotes` row means Pass 1 hasn't attempted this ticker's quote
    fetch yet -- an operational gap, not a structural one."""
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "NOQUOTE", with_quote=False)
    r = apply_r1_filters(conn)[0]
    assert "spread_filter_not_yet_fetched" in r.reason_codes
    assert "spread_filter_not_computable" not in r.reason_codes


def test_attempted_quote_with_no_data_fails_as_not_computable(tmp_path):
    """A `quotes` row DOES exist (Pass 1 tried live+historical) but
    spread is null -- Kalshi genuinely has no bid/ask history here (Step
    Zero Check 5's own finding). Structural, not operational -- must not
    collapse into the same reason code as an unattempted ticker."""
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "NODATA", with_quote=False)
    db.upsert_quote(conn, {
        "ticker": "NODATA", "end_period_ts": None, "yes_bid_close": None,
        "yes_ask_close": None, "spread": None, "source": "historical",
    })
    conn.commit()
    r = apply_r1_filters(conn)[0]
    assert "spread_filter_not_computable" in r.reason_codes
    assert "spread_filter_not_yet_fetched" not in r.reason_codes


def test_short_open_duration_fails(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "SHORT", open_epoch=0, close_epoch=MIN_OPEN_SECONDS - 1)
    r = apply_r1_filters(conn)[0]
    assert "open_below_24h" in r.reason_codes


def test_exactly_24h_passes_the_duration_check(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "EXACT", open_epoch=0, close_epoch=MIN_OPEN_SECONDS)
    r = apply_r1_filters(conn)[0]
    assert "open_below_24h" not in r.reason_codes


def test_settlement_value_contradicting_result_is_dropped(tmp_path):
    """Kalshi's own settlement value disagreeing with its own `result` for the
    same contract -- the one unambiguous data error the public fields expose,
    and what replaced the inert last-trade proxy on 2026-07-28."""
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "CONTRADICTS", result="yes", settlement_value=0.0)
    r = apply_r1_filters(conn)[0]
    assert r.passed is False
    assert "settlement_contradicts_result" in r.reason_codes


def test_a_losing_final_trade_is_not_a_mismatch(tmp_path):
    """An upset is not a data error. The proxy this replaced would have called
    a contract whose last trade sat on the losing side a mismatch; on a
    favorite-longshot-bias paper that is precisely the wrong thing to drop."""
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "UPSET", result="no", day0_price=0.9)
    r = apply_r1_filters(conn)[0]
    assert r.passed is True
    assert r.reason_codes == []


def test_missing_settlement_value_is_not_treated_as_a_contradiction(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "NO-SETTLE", result="yes", settlement_value=0.0)
    _seed(conn, "UNKNOWN", result="yes")
    conn.execute("UPDATE markets SET settlement_value_dollars = NULL WHERE ticker = 'UNKNOWN'")
    conn.commit()
    by_ticker = {r.ticker: r for r in apply_r1_filters(conn)}
    assert "settlement_contradicts_result" in by_ticker["NO-SETTLE"].reason_codes
    assert by_ticker["UNKNOWN"].reason_codes == []


def test_settlement_agreement_not_flagged(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "AGREE", result="yes", day0_price=0.95)
    r = apply_r1_filters(conn)[0]
    assert "settlement_contradicts_result" not in r.reason_codes


def test_missing_result_flagged_as_visible_exclusion(tmp_path):
    """A stale/unsynced `result` (Pass 1's live sweep can leave it NULL for
    older markets -- fetch/pass1.py's own docstring) must fail visibly here
    with 'result_missing_or_invalid', not silently pass this gate only to
    be invisibly dropped later by r1/panel.py's `WHERE result IN
    ('yes','no')` -- an unattributed shortfall against BDW's 156,986
    (2026-07-21 audit)."""
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "STALE", result=None)
    r = apply_r1_filters(conn)[0]
    assert r.passed is False
    assert "result_missing_or_invalid" in r.reason_codes
    assert "settlement_contradicts_result" not in r.reason_codes


def test_no_price_panel_row_does_not_trigger_mismatch(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "NOPANEL", result="yes", day0_price=None)
    r = apply_r1_filters(conn)[0]
    assert "settlement_contradicts_result" not in r.reason_codes


# ---------------------------------------------------------------------------
# dollar_volume_by_ticker mode -- the $1k DOLLAR-NOTIONAL reading of BDW's
# volume filter. Since 2026-07-26 this is the reported SENSITIVITY branch, not
# the primary: the contract reading reproduces BDW's own event/contract
# integers to within 0.1%/2.9% (r1/filters.py's VOLUME_READING_PIN). Both
# readings are exercised; neither is "the approximation".
# ---------------------------------------------------------------------------

def test_dollar_volume_mode_passes_market_clearing_true_notional(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "REAL-VOL")
    db.upsert_pass2_progress(conn, {
        "ticker": "REAL-VOL", "status": "done", "cursor": None, "source": "historical", "trade_count": 1,
    })
    conn.commit()
    r = apply_r1_filters(conn, dollar_volume_by_ticker={"REAL-VOL": 5000.0})[0]
    assert r.passed is True
    assert "volume_below_1000" not in r.reason_codes


def test_dollar_volume_mode_fails_market_below_true_notional_despite_high_contract_count(tmp_path):
    """The whole point of the fix: a market with plenty of CONTRACTS but
    thin real DOLLAR notional (cheap price) must fail here, even though
    the old volume_fp proxy would have passed it."""
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "CHEAP-CONTRACTS", volume_fp=5000.0)  # would pass the OLD contract-count proxy
    db.upsert_pass2_progress(conn, {
        "ticker": "CHEAP-CONTRACTS", "status": "done", "cursor": None, "source": "historical", "trade_count": 1,
    })
    conn.commit()
    r = apply_r1_filters(conn, dollar_volume_by_ticker={"CHEAP-CONTRACTS": 100.0})[0]  # real notional: $100
    assert r.passed is False
    assert "volume_below_1000" in r.reason_codes


def test_dollar_volume_mode_pass2_not_done_fails_as_not_yet_fetched(tmp_path):
    """A market Pass 2 hasn't finished must fail 'dollar_volume_not_yet_fetched'
    (operational), never silently 'volume_below_1000' just because it's
    absent from the aggregate dict."""
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "NOT-DONE")
    conn.commit()  # no pass2_progress row at all
    r = apply_r1_filters(conn, dollar_volume_by_ticker={})[0]
    assert r.passed is False
    assert "dollar_volume_not_yet_fetched" in r.reason_codes
    assert "volume_below_1000" not in r.reason_codes


def test_dollar_volume_mode_none_falls_back_to_contract_count_proxy(tmp_path):
    """dollar_volume_by_ticker=None thresholds Kalshi's own volume_fp, i.e.
    the CONTRACT reading -- the pinned PRIMARY since 2026-07-26, and also what
    callers without Pass 2 data get."""
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "LOW-VOL", volume_fp=500.0)
    r = apply_r1_filters(conn, dollar_volume_by_ticker=None)[0]
    assert r.passed is False
    assert "volume_below_1000" in r.reason_codes


def test_r2_window_markets_excluded_from_r1_filters(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "R2ONLY", in_r1=0)
    assert apply_r1_filters(conn) == []


def test_summarize_counts_reasons(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "OK-1")
    _seed(conn, "LOW-VOL", volume_fp=100.0)
    _seed(conn, "WIDE", spread=0.5)
    summary = summarize(apply_r1_filters(conn))
    assert summary["total"] == 3
    assert summary["passed"] == 1
    assert summary["failed"] == 2
    assert summary["reason_counts"]["volume_below_1000"] == 1
    assert summary["reason_counts"]["spread_above_20c"] == 1


def test_apply_and_log_writes_universe_log(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "OK-1")
    _seed(conn, "LOW-VOL", volume_fp=100.0)
    summary = apply_and_log(conn)
    assert summary["passed"] == 1
    rows = conn.execute("SELECT ticker, reason_code FROM universe_log").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "LOW-VOL"
    assert rows[0][1] == "volume_below_1000"


def test_apply_and_log_multiple_reasons_write_multiple_rows(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "BAD", volume_fp=100.0, spread=0.9)
    apply_and_log(conn)
    rows = conn.execute("SELECT reason_code FROM universe_log WHERE ticker='BAD'").fetchall()
    assert {r[0] for r in rows} == {"volume_below_1000", "spread_above_20c"}


def test_log_window_keeps_the_sensitivity_branch_out_of_the_primary_universe(tmp_path):
    """The dual-branch design's load-bearing invariant. In-scope is computed as
    "NOT IN universe_log WHERE window = 'r1'", so logging the dollar-notional
    sensitivity branch under that same label would silently shrink the PRIMARY
    analysis universe by the other reading's exclusions -- and the two readings
    disagree on roughly half the sample, so that would be a large, invisible
    error rather than a small one."""
    conn = db.connect(tmp_path / "t.db")
    # 2000 contracts at $0.10 = $200 notional: passes the CONTRACT reading,
    # fails the dollar one. Exactly the population the two readings split on.
    _seed(conn, "CHEAP", volume_fp=2000.0, day0_price=0.10, result="no")
    # The dollar branch only evaluates real notional once Pass 2 is 'done';
    # without this it correctly reports dollar_volume_not_yet_fetched instead,
    # which would test the operational path rather than the readings' split.
    db.upsert_pass2_progress(conn, {
        "ticker": "CHEAP", "status": "done", "cursor": None,
        "source": "historical", "trade_count": 2000,
    })
    conn.commit()

    primary = apply_and_log(conn, window="r1", dollar_volume_by_ticker=None)
    assert primary["passed"] == 1

    sensitivity = apply_and_log(
        conn, window="r1", dollar_volume_by_ticker={"CHEAP": 200.0},
        log_window=DOLLAR_BRANCH_LOG_WINDOW,
    )
    assert sensitivity["passed"] == 0  # $200 < $1000

    # The primary universe must be untouched by the sensitivity run.
    in_scope = {
        r[0] for r in conn.execute(
            "SELECT ticker FROM markets WHERE in_r1_window = 1 "
            "AND ticker NOT IN (SELECT ticker FROM universe_log WHERE window = 'r1')"
        ).fetchall()
    }
    assert in_scope == {"CHEAP"}

    # ...while the sensitivity branch's own exclusions stay queryable.
    dollar_reasons = {
        r[0] for r in conn.execute(
            "SELECT reason_code FROM universe_log WHERE window = ?",
            (DOLLAR_BRANCH_LOG_WINDOW,),
        ).fetchall()
    }
    assert "volume_below_1000" in dollar_reasons


def test_dollar_branch_log_window_is_not_the_primary_label(tmp_path):
    """Guards the constant itself -- if it ever became 'r1' the isolation above
    would silently stop holding."""
    assert DOLLAR_BRANCH_LOG_WINDOW != "r1"


def test_apply_and_log_replaces_rather_than_appends_so_a_repin_takes_effect(tmp_path):
    """In-scope is "NOT IN universe_log WHERE window = ?", so appending makes
    the universe a running INTERSECTION of every construction ever run against
    the database. Confirmed live 2026-07-26: after re-pinning the volume filter
    from dollar notional to contract count, the primary branch's counts came
    back byte-identical to the sensitivity branch's, because the earlier run's
    dollar exclusions were still sitting under window='r1'."""
    conn = db.connect(tmp_path / "t.db")
    _seed(conn, "CHEAP", volume_fp=2000.0, day0_price=0.10, result="no")
    db.upsert_pass2_progress(conn, {
        "ticker": "CHEAP", "status": "done", "cursor": None,
        "source": "historical", "trade_count": 2000,
    })
    conn.commit()

    # First run under the DOLLAR reading excludes it ($200 < $1000)...
    apply_and_log(conn, window="r1", dollar_volume_by_ticker={"CHEAP": 200.0})
    assert conn.execute(
        "SELECT COUNT(*) FROM universe_log WHERE window='r1' AND ticker='CHEAP'"
    ).fetchone()[0] > 0

    # ...and re-running under the CONTRACT reading must clear it, not stack.
    summary = apply_and_log(conn, window="r1", dollar_volume_by_ticker=None)
    assert summary["passed"] == 1
    assert conn.execute(
        "SELECT COUNT(*) FROM universe_log WHERE window='r1'"
    ).fetchone()[0] == 0


def test_replace_universe_exclusions_is_scoped_to_its_own_window(tmp_path):
    """Replacing one window must not disturb another -- the primary and
    sensitivity branches share this table under different labels."""
    conn = db.connect(tmp_path / "t.db")
    db.replace_universe_exclusions(conn, "r1", [("A", "volume_below_1000")])
    db.replace_universe_exclusions(conn, "r2", [("B", "spread_above_20c")])
    db.replace_universe_exclusions(conn, "r1", [("C", "open_below_24h")])
    conn.commit()
    rows = {
        (r[0], r[1]) for r in conn.execute("SELECT window, ticker FROM universe_log").fetchall()
    }
    assert rows == {("r1", "C"), ("r2", "B")}
