"""The event study exists to make the DiD's identifying assumption testable,
so its own ability to detect a violation has to be tested rather than assumed.

These scenarios caught a real bug on first run: the clean-controls filter
inherited from fit_did drops not-yet-treated rows of treated series, which are
exactly the pre-periods, and the estimator returned post-treatment effects with
no leads at all.
"""

from __future__ import annotations

import numpy as np
import polars as pl
import pytest

import kalshi_mt.r2.did as did
from kalshi_mt.r2.did import fit_event_study


def _panel(pretrend: float = 0.0, effect: float = 0.0, n_series: int = 40, months: int = 24):
    """Half the series treated, three staggered cohorts. `effect` shifts the
    slope from a series' own cohort month; `pretrend` adds a LINEAR divergence
    before it, which the pre-period coefficients must catch."""
    rng = np.random.default_rng(0)
    rows = []
    for si in range(n_series):
        s, treated = f"KX{si:03d}", si < n_series // 2
        cohort = 12 + (si % 3)
        for m in range(months):
            for j in range(12):
                p = rng.uniform(0.05, 0.95)
                k = m - cohort
                slope = 0.03 + ((effect if k >= 0 else pretrend * k) if treated else 0.0)
                y = p + (slope * p * 100 - 1.0) / 100 + rng.normal(0, 0.02)
                rows.append({
                    "ticker": f"{s}-{m}-{j}", "event_ticker": f"{s}-{m}",
                    "series_ticker": s, "y": float(y), "p": float(p),
                    "close_time_epoch": 1735689600 + m * 2592000,
                    "_now": bool(treated and k >= 0), "_ever": float(treated),
                })
    return pl.DataFrame(rows)


@pytest.fixture(autouse=True)
def _flags_from_fixture(monkeypatch):
    """Drive treatment off the fixture's own columns, so these tests exercise
    the estimator rather than data/fees.yaml."""
    monkeypatch.setattr(
        did, "treated_flags",
        lambda panel, schedule: (
            panel["_now"].cast(pl.Float64).to_numpy(), panel["_ever"].to_numpy()
        ),
    )


def test_pre_periods_are_estimated_at_all():
    """The regression that caught the clean-controls bug. An event study whose
    leads are all missing is not an event study."""
    r = fit_event_study(_panel(), {}, leads=4, lags=4)
    assert r is not None
    pre = [k for k in r.coefficients if k < r.reference]
    assert pre, "no pre-treatment coefficients were estimated"
    assert not np.isnan(r.pretrend_p)


def test_clean_data_does_not_flag_a_pre_trend():
    r = fit_event_study(_panel(pretrend=0.0, effect=0.0), {}, leads=4, lags=4)
    assert r.pretrend_p > 0.05
    assert r.posttrend_p > 0.05


def test_a_real_effect_is_recovered_without_flagging_pre_trends():
    r = fit_event_study(_panel(pretrend=0.0, effect=0.02), {}, leads=4, lags=4)
    post = [r.coefficients[k] for k in r.coefficients if k >= 0]
    assert np.mean(post) == pytest.approx(0.02, abs=0.01)
    assert r.pretrend_p > 0.05, "a genuine post-treatment effect must not look like a pre-trend"


def test_the_joint_post_test_has_power_against_a_large_effect():
    """Separate from the recovery test above, and deliberately at a larger
    effect. On this fixture -- 960 clusters, an effect spread over eight
    event-time coefficients -- the joint test does NOT reject at effect=0.02
    (p about 0.18) even though the mean is recovered correctly. That is a
    genuine power limitation of a joint test over many imprecise coefficients,
    not a defect, and it is worth knowing about before reading a non-rejection
    on real data as evidence of no dynamics."""
    r = fit_event_study(_panel(pretrend=0.0, effect=0.06), {}, leads=4, lags=4)
    assert r.posttrend_p < 0.05


def test_a_planted_pre_trend_is_detected():
    """Power, not just absence of false positives. Without this the pre-trend
    test could pass by never rejecting anything."""
    r = fit_event_study(_panel(pretrend=0.004, effect=0.0), {}, leads=4, lags=4)
    assert r.pretrend_p < 0.05


def test_reference_period_is_omitted():
    r = fit_event_study(_panel(), {}, leads=4, lags=4)
    assert r.reference not in r.coefficients


def test_not_identified_returns_none_rather_than_a_null():
    """No treated rows at all. Addendum 3 is explicit that this is reported as
    unidentified and never as a zero."""
    panel = _panel()
    panel = panel.with_columns(pl.lit(False).alias("_now"), pl.lit(0.0).alias("_ever"))
    assert fit_event_study(panel, {}, leads=4, lags=4) is None
