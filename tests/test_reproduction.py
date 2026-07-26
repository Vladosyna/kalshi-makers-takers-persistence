from __future__ import annotations

import polars as pl

from kalshi_mt.r1.panel import PANEL_SCHEMA
from kalshi_mt.r1.reproduction import (
    by_category_psi,
    by_year_psi,
    maker_taker_split,
    returns_by_band,
    win_rate_by_band,
    write_divergence_log,
)


def _epoch(year, month=6, day=1):
    from datetime import datetime, timezone
    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp())


def _panel_row(ticker, event, p, y, *, lookback_day=0, category="Weather", close_epoch=None,
               count_fp=100.0, taker_outcome_side="yes"):
    """count_fp defaults to 100 contracts -- the fee model rounds the ORDER
    TOTAL up to the next cent, so the order size is load-bearing for any net
    return (spec S1: "compute fees on actual per-order contract counts")."""
    return {
        "ticker": ticker, "event_ticker": event, "lookback_day": lookback_day, "category": category,
        "close_time_epoch": close_epoch or _epoch(2023), "side": "yes", "y": y, "p": p, "source": "live",
        "count_fp": count_fp, "taker_outcome_side": taker_outcome_side,
    }


def _panel(rows):
    return pl.DataFrame(rows, schema=PANEL_SCHEMA)


# ---------------------------------------------------------------------------
# by_year_psi
# ---------------------------------------------------------------------------

def test_by_year_psi_buckets_by_close_year():
    rows = [
        _panel_row("T1", "E1", 0.1, 0.0, close_epoch=_epoch(2022)),
        _panel_row("T2", "E2", 0.3, 0.0, close_epoch=_epoch(2022)),
        _panel_row("T3", "E3", 0.7, 1.0, close_epoch=_epoch(2022)),
        _panel_row("T4", "E4", 0.9, 1.0, close_epoch=_epoch(2022)),
        _panel_row("T5", "E5", 0.5, 1.0, close_epoch=_epoch(2023)),
        _panel_row("T6", "E6", 0.5, 0.0, close_epoch=_epoch(2023)),
    ]
    result = by_year_psi(_panel(rows))
    assert "2022" in result
    assert "2023" in result
    assert result["2022"]["fit"] is not None
    assert result["2022"]["bdw_psi"] == 0.023


def test_by_year_psi_verdict_confirmed_when_ci_contains_target():
    """A tight-ish fit whose CI happens to bracket BDW's own point estimate."""
    rows = [
        _panel_row("T1", "E1", 0.1, 0.0, close_epoch=_epoch(2022)),
        _panel_row("T2", "E2", 0.2, 0.0, close_epoch=_epoch(2022)),
        _panel_row("T3", "E3", 0.3, 0.0, close_epoch=_epoch(2022)),
        _panel_row("T4", "E4", 0.7, 1.0, close_epoch=_epoch(2022)),
        _panel_row("T5", "E5", 0.8, 1.0, close_epoch=_epoch(2022)),
        _panel_row("T6", "E6", 0.9, 1.0, close_epoch=_epoch(2022)),
    ]
    result = by_year_psi(_panel(rows))
    entry = result["2022"]
    assert entry["verdict"] in ("confirmed", "partially_confirmed")  # not diverged -- same-sign, positive psi


def test_by_year_psi_verdict_diverged_on_opposite_sign():
    # Reversed FLB pattern: high price loses, low price wins -- psi negative.
    rows = [
        _panel_row("T1", "E1", 0.1, 1.0, close_epoch=_epoch(2022)),
        _panel_row("T2", "E2", 0.2, 1.0, close_epoch=_epoch(2022)),
        _panel_row("T3", "E3", 0.3, 1.0, close_epoch=_epoch(2022)),
        _panel_row("T4", "E4", 0.7, 0.0, close_epoch=_epoch(2022)),
        _panel_row("T5", "E5", 0.8, 0.0, close_epoch=_epoch(2022)),
        _panel_row("T6", "E6", 0.9, 0.0, close_epoch=_epoch(2022)),
    ]
    result = by_year_psi(_panel(rows))
    assert result["2022"]["verdict"] == "diverged"


def test_by_year_psi_insufficient_data_when_single_cluster():
    rows = [_panel_row("T1", "E1", 0.5, 1.0, close_epoch=_epoch(2022))]
    result = by_year_psi(_panel(rows))
    assert result["2022"]["verdict"] == "insufficient_data"
    assert result["2022"]["fit"] is None


def test_by_year_psi_empty_panel():
    assert by_year_psi(pl.DataFrame(schema=PANEL_SCHEMA)) == {}


# ---------------------------------------------------------------------------
# by_category_psi
# ---------------------------------------------------------------------------

def test_by_category_psi_separates_categories():
    rows = [
        _panel_row("T1", "E1", 0.1, 0.0, category="Weather"),
        _panel_row("T2", "E2", 0.9, 1.0, category="Weather"),
        _panel_row("T3", "E3", 0.5, 1.0, category="Politics"),
        _panel_row("T4", "E4", 0.5, 0.0, category="Politics"),
    ]
    result = by_category_psi(_panel(rows))
    assert set(result.keys()) == {"Weather", "Politics"}


# ---------------------------------------------------------------------------
# win_rate_by_band
# ---------------------------------------------------------------------------

def test_win_rate_by_band_basic():
    doubled = pl.DataFrame([
        {**_panel_row("T1", "E1", 0.05, 0.0), "side": "yes"},
        {**_panel_row("T1", "E1", 0.95, 1.0), "side": "no"},
        {**_panel_row("T2", "E2", 0.05, 0.0), "side": "yes"},
    ], schema=PANEL_SCHEMA)
    result = win_rate_by_band(doubled)
    assert result["1-10c"]["n"] == 2
    assert result["1-10c"]["win_rate"] == 0.0
    assert result["91-99c"]["n"] == 1
    assert result["91-99c"]["win_rate"] == 1.0


def test_win_rate_by_band_empty():
    assert win_rate_by_band(pl.DataFrame(schema=PANEL_SCHEMA)) == {}


# ---------------------------------------------------------------------------
# returns_by_band
# ---------------------------------------------------------------------------

def _fee_schedule():
    return {"schedule": [
        {"effective_from": "2022-09-22", "role": "taker", "category": "default", "rate": 0.07},
    ]}


def test_returns_by_band_gross_and_net():
    # 100 contracts at 50c: order fee = ceil(0.07*100*0.5*0.5*100)/100 = $1.75,
    # i.e. $0.0175 per contract -- the honest rate. Rounding is per ORDER, so a
    # 1-contract assumption would charge a whole cent and overstate it.
    rows = [_panel_row("T1", "E1", 0.5, 1.0, lookback_day=0, close_epoch=_epoch(2023),
                        count_fp=100.0)]
    result = returns_by_band(_panel(rows), _fee_schedule())
    band = result["41-50c"]
    assert band["n"] == 1
    # gross: (1.0 - 0.5) / 0.5 = 1.0
    assert abs(band["mean_gross_return"] - 1.0) < 1e-9
    # net: (1.0 - 0.5 - 0.0175) / 0.5 = 0.965
    assert abs(band["mean_net_return"] - 0.965) < 1e-6
    assert band["fee_schedule_gap_excluded"] == 0


def test_returns_by_band_net_return_respects_the_fee_rate_floor():
    """The pinned convention is r = (payout - P - f) / P -- divided by the
    STAKE, not by total outlay -- so a total loss gives -1 - f/P, slightly
    below -100%, and that is correct rather than a bug. With a proportional
    fee f = rate*P*(1-P), f/P = rate*(1-P) <= rate, so the floor is
    -(1 + rate) = -1.07 at BDW's 7% taker rate.

    That bound is what catches the real error: charging the ceil-to-cent fee as
    if every order were 1 contract makes f/P as large as 1.0 at a 1c price, and
    measured 2026-07-26 it drove the 1-10c band to -181% -- far outside the
    floor, and concentrated in exactly the tail bins the FLB headline rests
    on."""
    rows = [
        _panel_row("T1", "E1", 0.01, 0.0, close_epoch=_epoch(2023), count_fp=5000.0),
        _panel_row("T2", "E2", 0.03, 0.0, close_epoch=_epoch(2023), count_fp=5000.0),
    ]
    result = returns_by_band(_panel(rows), _fee_schedule())
    net = result["1-10c"]["mean_net_return"]
    assert net is not None
    assert net >= -1.07 - 1e-6, f"net return {net} is below the -(1 + fee rate) floor"
    assert net < -1.0  # a total loss plus a fee IS worse than -100% of stake


def test_returns_by_band_missing_order_size_is_excluded_not_assumed():
    """The skip-rule panel has no count_fp (price_panel never stored it). Such
    rows must be excluded from the NET figure and counted, never silently
    charged a 1-contract fee."""
    rows = [_panel_row("T1", "E1", 0.5, 1.0, close_epoch=_epoch(2023), count_fp=None)]
    result = returns_by_band(_panel(rows), _fee_schedule())
    band = result["41-50c"]
    assert band["mean_gross_return"] is not None   # gross needs no fee
    assert band["mean_net_return"] is None
    assert band["fee_schedule_gap_excluded"] == 1


def test_returns_by_band_uses_every_observation_as_an_entry_price():
    """Amended 2026-07-26: this asserted the opposite -- that only
    lookback_day == 0 counted. BDW's own ~-20% average pre-fee return settles
    it: all observations give -0.250 on our universe, closing-day-only gives
    -0.701, because a contract still at 1-10c on its final day has almost no
    chance left and that band alone reaches -97%. Every observed price is an
    entry price, which also makes Fig 5 and the MZ regression describe the same
    sample (BDW's n = 156,986 is the full panel, not one row per contract)."""
    rows = [
        _panel_row("T1", "E1", 0.5, 1.0, lookback_day=0),
        _panel_row("T1", "E1", 0.4, 1.0, lookback_day=1),
    ]
    result = returns_by_band(_panel(rows), _fee_schedule())
    assert sum(b["n"] for b in result.values()) == 2
    assert set(result) == {"41-50c", "31-40c"}


def test_returns_by_band_fee_gap_excluded_from_net_not_gross():
    # 2021 predates the fee schedule's earliest entry (2022-09-22).
    rows = [_panel_row("T1", "E1", 0.5, 1.0, lookback_day=0, close_epoch=_epoch(2021))]
    result = returns_by_band(_panel(rows), _fee_schedule())
    band = result["41-50c"]
    assert band["mean_gross_return"] is not None
    assert band["mean_net_return"] is None
    assert band["fee_schedule_gap_excluded"] == 1


def test_returns_by_band_empty():
    assert returns_by_band(pl.DataFrame(schema=PANEL_SCHEMA), _fee_schedule()) == {}


# ---------------------------------------------------------------------------
# maker_taker_split -- operates on the DOUBLED PANEL, not the fill tape.
# Verified against the primary PDF: Table 10 totals 313,972 observations (the
# doubled panel) with Makers exactly 156,986, and the text pins the unit as the
# up-to-11-observations-per-contract panel, not fills.
# ---------------------------------------------------------------------------

def _doubled(rows):
    from kalshi_mt.r1.panel import build_doubled_panel
    return build_doubled_panel(_panel(rows))


def test_maker_taker_split_role_follows_the_side_the_taker_took():
    """Taker bought YES at 0.9, market resolves YES. The Yes observation is the
    Taker's; the complementary No observation at 0.10 is the Maker's."""
    rows = [_panel_row("T1", "E1", 0.9, 1.0, taker_outcome_side="yes")]
    result = maker_taker_split(_doubled(rows), _fee_schedule())
    assert result["n_taker_obs"] == 1
    assert result["n_maker_obs"] == 1
    # Maker pays no fee in BDW's window, so its return is gross: (0 - 0.1)/0.1.
    assert abs(result["maker_return"] - (-1.0)) < 1e-9
    # Taker's is post-fee, so strictly below the gross (1 - 0.9)/0.9.
    assert result["taker_return"] < (1.0 - 0.9) / 0.9


def test_maker_taker_split_maker_share_by_band_uses_complementary_prices():
    rows = [_panel_row("T1", "E1", 0.95, 1.0, taker_outcome_side="yes")]
    result = maker_taker_split(_doubled(rows), _fee_schedule())
    # yes side (0.95) is the taker's; no side (0.05) is the maker's.
    assert result["maker_share_by_band"]["91-99c"] == 0.0
    assert result["maker_share_by_band"]["1-10c"] == 1.0


def test_maker_taker_split_makers_pay_no_fee_takers_do():
    """Fig 6 reports POST-fee returns, and in BDW's window makers were
    fee-exempt while takers paid 0.07*P*(1-P) on the order total. Part of the
    headline gap is the fee itself, so the asymmetry must be in the code."""
    rows = [
        _panel_row("T1", "E1", 0.5, 1.0, taker_outcome_side="yes"),
        _panel_row("T2", "E2", 0.5, 1.0, taker_outcome_side="no"),
    ]
    result = maker_taker_split(_doubled(rows), _fee_schedule())
    # Both roles see one winning and one losing 50c observation, so any gap
    # between them is purely the taker fee.
    assert result["maker_return"] > result["taker_return"]


def test_maker_taker_split_reports_the_50c_plus_maker_margin():
    """BDW's "makers who buy contracts costing 50c and over earn 2.6%" -- the
    escalation rule in spec S5 keys off this margin, so it must be reported
    rather than recomputed ad hoc."""
    rows = [_panel_row("T1", "E1", 0.6, 1.0, taker_outcome_side="no")]  # maker holds the 0.6 Yes
    result = maker_taker_split(_doubled(rows), _fee_schedule())
    assert result["maker_return_50c_plus"] is not None
    assert abs(result["maker_return_50c_plus"] - ((1.0 - 0.6) / 0.6)) < 1e-9


def test_maker_taker_split_skips_observations_without_a_taker_side():
    """The skip-rule panel carries no taker side (price_panel never stored it),
    so those observations must be skipped, never guessed at."""
    rows = [_panel_row("T1", "E1", 0.5, 1.0, taker_outcome_side=None)]
    result = maker_taker_split(_doubled(rows), _fee_schedule())
    assert result["n_maker_obs"] == 0
    assert result["n_taker_obs"] == 0


def test_maker_taker_split_empty_panel():
    result = maker_taker_split(_doubled([]), _fee_schedule())
    assert result["maker_return"] is None
    assert result["taker_return"] is None
