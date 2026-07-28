"""Series-level difference-in-differences for the maker-fee question
(docs/analysis_plan.md Addendum 3).

Why this exists
---------------
§2.1 specifies `delta_fee` as the slope break at a single exchange-wide date.
Sourcing Kalshi's published fee schedules (docs/sources/fees/, 16 dated
captures) showed there was no exchange-wide fee change: the maker fee is a
surcharge on an enumerated list of SERIES -- 29 at introduction on 2025-05-13,
then 39, 48, 101, 111 as series were added and a few removed. In the window
the first list was in force, the treated series were 5.3% of in-scope markets
and 25.9% of traded volume.

So `delta_fee` as originally written estimates a break whose treatment reached
a twentieth of the sample, and a null on it says little about fees. The same
fact supplies a better design: treated and untreated series trade side by side
in the same months, giving a within-venue control group.

The estimand
------------
Treatment is TIME-VARYING and STAGGERED -- a market is treated if its series
was on the maker-fee list on the day it closed, which this module reads
straight off `data/fees.yaml` rather than re-encoding the dates:

    (Y-P) = alpha + psi*P
          + alpha_E*Ever + delta_E*(Ever*P)          # treated-series baseline
          + alpha_M*Month + delta_M*(Month*P)        # common calendar path
          + alpha_D*Now + delta_D*(Now*P)            # <- the estimand
          + epsilon

`Ever` absorbs any permanent difference between treated and untreated series
(sports and macro series are not like politics markets, in level OR in slope).
The month terms absorb whatever happened exchange-wide that month, including
the publication boundary and the sports-composition shift. `delta_D` is then
identified off variation WITHIN a month BETWEEN series that had the fee that
month and series that did not: the differential change in the favorite-longshot
slope caused by charging makers.

Standard errors cluster on the event, as everywhere else in this repo
(spec S4's nesting argument), with the same wild cluster bootstrap fallback
below 50 clusters that r2/regression.py uses.

Known limitation, stated rather than discovered
-----------------------------------------------
Staggered adoption plus two-way fixed effects is the Goodman-Bacon /
Callaway-Sant'Anna problem: already-treated units serve as controls for
later-treated ones, and with heterogeneous dynamic effects the estimator can
put negative weight on some comparisons. `fit_did(..., clean_controls=True)`
gives the robust variant -- each treated observation is compared only against
NEVER-treated series, which removes the bad comparisons at the cost of
precision. Both are reported; they should agree, and if they do not, the
clean-controls estimate is the one to believe.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import numpy as np
import polars as pl
import statsmodels.api as sm

from kalshi_mt.fees.schedule import FeeScheduleGapError, entry_for
from kalshi_mt.r2.regression import (
    WILD_BOOTSTRAP_CLUSTER_THRESHOLD,
    _cluster_ids,
    _wild_cluster_bootstrap_ci,
)


@dataclass
class DidResult:
    """delta_did is the estimand: the differential change in the MZ slope for
    series while they carry a maker fee, net of the common calendar path and
    of any permanent treated/untreated difference. Units are the same as psi
    (cents of (Y-P) per cent of P)."""

    delta_did: float
    delta_did_se: float
    delta_did_ci_lo: float
    delta_did_ci_hi: float
    alpha_did: float
    psi_untreated: float
    delta_ever: float           # permanent slope difference of treated series
    n: int
    n_clusters: int
    n_treated_obs: int
    n_control_obs: int
    n_treated_series: int
    months: int
    used_wild_bootstrap: bool
    clean_controls: bool


def treated_flags(
    panel: pl.DataFrame, fee_schedule: dict[str, Any],
) -> tuple[np.ndarray, np.ndarray]:
    """(now, ever) treatment indicators for each panel row.

    `now` asks the fee schedule the same question the fee code asks: does a
    maker fill in this series, on this market's closing date, actually cost
    anything? Reading it off `entry_for` rather than re-listing the dates here
    means the DiD and the net-return layers can never disagree about who was
    treated -- one artifact, one answer.

    `ever` is series-level: 1 for every row of a series that is treated at any
    point in the panel's own span. It is deliberately NOT "treated at any point
    in history" -- a series first treated after the panel ends contributes no
    variation and would only dilute the control group.
    """
    if panel.is_empty():
        return np.zeros(0), np.zeros(0)

    series = panel["series_ticker"].to_list()
    close_epoch = panel["close_time_epoch"].to_list()

    # One lookup per (series, date) pair, not per row: a panel carries up to 11
    # rows per market and every one of them shares a closing date.
    cache: dict[tuple[str | None, str], bool] = {}

    def charged(series_ticker: str | None, epoch: int | None) -> bool:
        if series_ticker is None or epoch is None:
            return False
        as_of = datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d")
        key = (series_ticker, as_of)
        if key not in cache:
            try:
                entry = entry_for(fee_schedule, "maker", as_of, series_ticker=series_ticker)
                cache[key] = entry.get("form") != "none" and float(entry.get("rate", 0.0)) != 0.0
            except FeeScheduleGapError:
                cache[key] = False
        return cache[key]

    now = np.array([charged(s, e) for s, e in zip(series, close_epoch)], dtype=float)
    treated_series = {s for s, flag in zip(series, now) if flag and s is not None}
    ever = np.array([1.0 if s in treated_series else 0.0 for s in series], dtype=float)
    return now, ever


def _month_index(close_epoch: np.ndarray) -> np.ndarray:
    """Calendar-month label per row, as YYYYMM integers."""
    return np.array([
        int(datetime.fromtimestamp(int(e), tz=timezone.utc).strftime("%Y%m")) for e in close_epoch
    ])


def fit_did(
    panel: pl.DataFrame,
    fee_schedule: dict[str, Any],
    *,
    clean_controls: bool = False,
    n_wild_bootstrap: int = 999,
    seed: int = 0,
) -> DidResult | None:
    """Fit the maker-fee DiD on a Yes-only panel (r1/panel.py's PANEL_SCHEMA).

    Returns None when the design is not identified: no treated rows, no
    control rows, fewer than two months, fewer than two event clusters, or no
    price variation. A None here means "this cannot be estimated on this
    sample", which callers must report as such -- never as a null result.
    """
    if panel.is_empty() or "series_ticker" not in panel.columns:
        return None

    now, ever = treated_flags(panel, fee_schedule)
    if now.sum() == 0:
        return None

    if clean_controls:
        # Drop control observations drawn from ever-treated series, so every
        # comparison is treated-vs-never-treated and no already-treated unit
        # can serve as a control for a later-treated one.
        keep = (now == 1.0) | (ever == 0.0)
        panel = panel.filter(pl.Series(keep))
        now, ever = now[keep], ever[keep]
        if panel.is_empty() or now.sum() == 0:
            return None

    y = panel["y"].to_numpy()
    p = panel["p"].to_numpy()
    close_epoch = panel["close_time_epoch"].to_numpy()
    y_minus_p_cents = (y - p) * 100.0
    p_cents = p * 100.0
    if np.ptp(p_cents) == 0:
        return None

    months = _month_index(close_epoch)
    unique_months = np.unique(months)
    if len(unique_months) < 2:
        return None
    n_control = int((now == 0.0).sum())
    if n_control == 0:
        return None

    # Month dummies AND month-x-price interactions: the estimand is a slope,
    # so a common calendar path has to be allowed in the slope too, not just
    # in the level. First month dropped as the reference.
    month_cols = []
    for m in unique_months[1:]:
        d = (months == m).astype(float)
        month_cols.append(d)
        month_cols.append(d * p_cents)

    # The `ever` terms exist to absorb permanent treated-vs-untreated
    # differences while a treated series is still untreated. Under
    # clean_controls those rows are exactly what was dropped, so `ever` and
    # `now` become the same column and the design goes rank-deficient. Omit
    # them there rather than letting the rank guard turn a well-posed
    # comparison into a silent None.
    base_cols = [np.ones_like(p_cents), p_cents]
    if not clean_controls:
        base_cols += [ever, ever * p_cents]
    delta_idx = len(base_cols) + 1  # now*p_cents sits right after `now`
    x = np.column_stack([*base_cols, now, now * p_cents, *month_cols])

    clusters = _cluster_ids(panel)
    n_clusters = len(np.unique(clusters))
    if n_clusters < 2 or len(panel) <= x.shape[1]:
        return None
    if np.linalg.matrix_rank(x) < x.shape[1]:
        # Collinear design -- e.g. treatment perfectly aligned with one month,
        # which happens on a short panel. Not estimable; say so.
        return None

    fit = sm.OLS(y_minus_p_cents, x).fit(cov_type="cluster", cov_kwds={"groups": clusters})
    use_wild = n_clusters < WILD_BOOTSTRAP_CLUSTER_THRESHOLD
    delta = float(fit.params[delta_idx])
    if use_wild:
        delta_se, ci_lo, ci_hi = _wild_cluster_bootstrap_ci(
            y_minus_p_cents, x, clusters, delta_idx, n_reps=n_wild_bootstrap, seed=seed,
        )
    else:
        delta_se = float(fit.bse[delta_idx])
        ci_lo, ci_hi = delta - 1.96 * delta_se, delta + 1.96 * delta_se

    treated_series = {
        s for s, flag in zip(panel["series_ticker"].to_list(), now) if flag and s is not None
    }
    return DidResult(
        delta_did=delta,
        delta_did_se=delta_se,
        delta_did_ci_lo=ci_lo,
        delta_did_ci_hi=ci_hi,
        alpha_did=float(fit.params[delta_idx - 1]),
        psi_untreated=float(fit.params[1]),
        # No `ever` term under clean_controls (see the design-matrix note);
        # nan rather than 0.0 so a reader cannot mistake "not estimated" for
        # "estimated at zero".
        delta_ever=float("nan") if clean_controls else float(fit.params[3]),
        n=len(panel),
        n_clusters=n_clusters,
        n_treated_obs=int(now.sum()),
        n_control_obs=n_control,
        n_treated_series=len(treated_series),
        months=len(unique_months),
        used_wild_bootstrap=use_wild,
        clean_controls=clean_controls,
    )


def run_did_pair(
    panel: pl.DataFrame, fee_schedule: dict[str, Any], *, n_wild_bootstrap: int = 999, seed: int = 0,
) -> dict[str, DidResult | None]:
    """Both variants, always reported together: the two-way fixed-effects fit
    and the clean-controls fit that drops already-treated units as controls.
    Agreement between them is the evidence that staggered-adoption weighting
    is not driving the result; disagreement means believing the clean one."""
    return {
        "twfe": fit_did(panel, fee_schedule, clean_controls=False,
                        n_wild_bootstrap=n_wild_bootstrap, seed=seed),
        "clean_controls": fit_did(panel, fee_schedule, clean_controls=True,
                                  n_wild_bootstrap=n_wild_bootstrap, seed=seed),
    }
