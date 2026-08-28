from __future__ import annotations

from datetime import UTC, datetime

import polars as pl

from kalshi_mt.r1.panel import PANEL_SCHEMA
from kalshi_mt.r2.did import fit_did, run_did_pair, treated_flags

TREATED = "KXNBA"
CONTROL = "KXPRESPARTY"
LATE = "KXNFLGAME"


def _schedule():
    """Staggered adoption, as the real schedule has: KXNBA from 2025-05-13,
    KXNFLGAME joining on 2025-07-08, KXPRESPARTY never."""
    return {
        "version": 2,
        "schedule": [
            {"effective_from": "2021-07-01", "role": "taker", "form": "quadratic",
             "rate": 0.07, "scope": {"kind": "all"}},
            {"effective_from": "2021-07-01", "role": "maker", "form": "none",
             "rate": 0.0, "scope": {"kind": "all"}},
            {"effective_from": "2025-05-13", "role": "maker", "form": "flat_per_contract",
             "rate": 0.0025, "scope": {"kind": "series", "series": [TREATED]}},
            {"effective_from": "2025-07-08", "role": "maker", "form": "quadratic",
             "rate": 0.0175, "scope": {"kind": "series", "series": [TREATED, LATE]}},
        ],
    }


def _epoch(y: int, m: int, d: int) -> int:
    return int(datetime(y, m, d, tzinfo=UTC).timestamp())


def _rows(series: str, close_epoch: int, prices: list[float], outcomes: list[float], tag: str):
    return [
        {
            "ticker": f"{series}-{tag}-{i}", "event_ticker": f"{series}-{tag}-{i}",
            "series_ticker": series, "lookback_day": 0, "category": "Sports",
            "close_time_epoch": close_epoch, "side": "yes", "y": o, "p": p,
            "source": "tape", "count_fp": 100.0, "taker_outcome_side": "yes",
        }
        for i, (p, o) in enumerate(zip(prices, outcomes))
    ]


def _panel(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows, schema=PANEL_SCHEMA)


# --- treatment assignment ----------------------------------------------------


def test_treated_flags_read_treatment_off_the_fee_schedule():
    panel = _panel(
        _rows(TREATED, _epoch(2025, 4, 1), [0.5], [1.0], "pre")
        + _rows(TREATED, _epoch(2025, 6, 1), [0.5], [1.0], "post")
        + _rows(CONTROL, _epoch(2025, 6, 1), [0.5], [1.0], "ctl")
    )
    now, ever = treated_flags(panel, _schedule())
    assert list(now) == [0.0, 1.0, 0.0]
    # `ever` is series-level: the treated series' PRE-treatment row is also 1,
    # which is what lets the design separate a permanent series difference
    # from the treatment itself.
    assert list(ever) == [1.0, 1.0, 0.0]


def test_treated_flags_respect_staggered_entry():
    panel = _panel(
        _rows(LATE, _epoch(2025, 6, 1), [0.5], [1.0], "before")
        + _rows(LATE, _epoch(2025, 8, 1), [0.5], [1.0], "after")
    )
    now, _ = treated_flags(panel, _schedule())
    assert list(now) == [0.0, 1.0]


def test_treated_flags_treat_a_null_series_as_never_treated():
    """Polymarket control rows carry no Kalshi series -- they must not blow up
    and must not be counted as treated."""
    rows = _rows(CONTROL, _epoch(2025, 6, 1), [0.5], [1.0], "ctl")
    rows[0]["series_ticker"] = None
    now, ever = treated_flags(_panel(rows), _schedule())
    assert list(now) == [0.0]
    assert list(ever) == [0.0]


# --- identification guards ---------------------------------------------------


def test_returns_none_when_nothing_is_treated():
    panel = _panel(
        _rows(CONTROL, _epoch(2025, 6, 1), [0.2, 0.8], [0.0, 1.0], "a")
        + _rows(CONTROL, _epoch(2025, 8, 1), [0.3, 0.7], [0.0, 1.0], "b")
    )
    assert fit_did(panel, _schedule()) is None


def test_returns_none_when_there_is_no_control_group():
    panel = _panel(
        _rows(TREATED, _epoch(2025, 6, 1), [0.2, 0.8], [0.0, 1.0], "a")
        + _rows(TREATED, _epoch(2025, 8, 1), [0.3, 0.7], [0.0, 1.0], "b")
    )
    assert fit_did(panel, _schedule()) is None


def test_returns_none_on_a_single_month():
    panel = _panel(
        _rows(TREATED, _epoch(2025, 8, 1), [0.2, 0.8], [0.0, 1.0], "a")
        + _rows(CONTROL, _epoch(2025, 8, 1), [0.3, 0.7], [0.0, 1.0], "b")
    )
    assert fit_did(panel, _schedule()) is None


def test_returns_none_on_an_empty_panel():
    assert fit_did(_panel([]), _schedule()) is None


# --- the estimand ------------------------------------------------------------


def _staggered_panel(treated_slope_shift: float) -> pl.DataFrame:
    """Two months either side of KXNBA's 2025-05-13 entry, treated and control
    series in both. Outcomes are built so that (Y-P) is linear in P with a
    known slope, and the treated series' slope shifts by
    `treated_slope_shift` (in (Y-P)-cents per P-cent) once treated."""
    prices = [0.1, 0.2, 0.3, 0.4, 0.6, 0.7, 0.8, 0.9]
    base_psi = 0.05

    def outcomes(psi: float) -> list[float]:
        # y = p + (psi * p_cents)/100 keeps (Y-P)_cents = psi * P_cents exactly.
        return [p + psi * (p * 100.0) / 100.0 for p in prices]

    rows = []
    for month, epoch in ((4, _epoch(2025, 4, 15)), (6, _epoch(2025, 6, 15))):
        treated_psi = base_psi + (treated_slope_shift if month == 6 else 0.0)
        rows += _rows(TREATED, epoch, prices, outcomes(treated_psi), f"t{month}")
        rows += _rows(CONTROL, epoch, prices, outcomes(base_psi), f"c{month}")
    return _panel(rows)


def test_delta_did_recovers_a_planted_slope_shift():
    result = fit_did(_staggered_panel(treated_slope_shift=-0.03), _schedule(), n_wild_bootstrap=99)
    assert result is not None
    # (Y-P) and P are both in cents, so a slope shift of -0.03 in probability
    # units is -0.03 in the regression's units too.
    assert abs(result.delta_did - (-0.03)) < 1e-6
    assert result.n_treated_obs == 8
    assert result.n_treated_series == 1
    assert result.months == 2


def test_delta_did_is_zero_when_both_arms_move_together():
    """A common calendar shift affecting treated and control alike must land
    in the month terms, not in delta_did -- that is the whole point of having
    a control group."""
    prices = [0.1, 0.3, 0.5, 0.7, 0.9]

    def outcomes(psi: float) -> list[float]:
        return [p + psi * p for p in prices]

    rows = []
    for month, epoch, psi in ((4, _epoch(2025, 4, 15), 0.05), (6, _epoch(2025, 6, 15), 0.01)):
        rows += _rows(TREATED, epoch, prices, outcomes(psi), f"t{month}")
        rows += _rows(CONTROL, epoch, prices, outcomes(psi), f"c{month}")
    result = fit_did(_panel(rows), _schedule(), n_wild_bootstrap=99)
    assert result is not None
    assert abs(result.delta_did) < 1e-6


def test_permanent_series_difference_lands_in_ever_not_in_did():
    """Treated series differ from control series in level and slope for
    reasons that have nothing to do with fees (they are sports and macro
    series). That difference must be absorbed by `ever`."""
    prices = [0.1, 0.3, 0.5, 0.7, 0.9]

    def outcomes(psi: float) -> list[float]:
        return [p + psi * p for p in prices]

    rows = []
    for month, epoch in ((4, _epoch(2025, 4, 15)), (6, _epoch(2025, 6, 15))):
        rows += _rows(TREATED, epoch, prices, outcomes(0.09), f"t{month}")
        rows += _rows(CONTROL, epoch, prices, outcomes(0.02), f"c{month}")
    result = fit_did(_panel(rows), _schedule(), n_wild_bootstrap=99)
    assert result is not None
    assert abs(result.delta_did) < 1e-6
    assert abs(result.delta_ever - 0.07) < 1e-6


def test_clean_controls_drops_ever_treated_rows_from_the_control_side():
    panel = _staggered_panel(treated_slope_shift=-0.03)
    both = run_did_pair(panel, _schedule(), n_wild_bootstrap=99)
    assert both["twfe"] is not None and both["clean_controls"] is not None
    # In the clean variant a treated series contributes only its treated rows,
    # so its pre-period observations are gone.
    assert both["clean_controls"].n < both["twfe"].n
    assert both["clean_controls"].clean_controls is True
    assert both["twfe"].clean_controls is False
    # Both must find the same planted effect; disagreement here would be the
    # staggered-adoption weighting problem showing up.
    assert abs(both["clean_controls"].delta_did - both["twfe"].delta_did) < 1e-6
    # `ever` is not estimated in the clean variant -- nan, never a spurious 0.
    assert both["clean_controls"].delta_ever != both["clean_controls"].delta_ever


def test_result_reports_the_arm_sizes_it_was_identified_from():
    result = fit_did(_staggered_panel(treated_slope_shift=-0.02), _schedule(), n_wild_bootstrap=99)
    assert result is not None
    assert result.n == result.n_treated_obs + result.n_control_obs
    assert result.n_clusters > 1
    assert result.used_wild_bootstrap is True  # far below 50 event clusters
