"""R1 reproduction report (spec S1/S2): by-year psi vs BDW Table 9,
by-category psi vs Table 8, win-rate-vs-price curve vs Fig 3, returns-by-
band vs Fig 5, maker/taker split vs Fig 6/Table 10.

Verdict vocabulary (confirmed/partially confirmed/diverged,
docs/analysis_plan.md S1) is applied only where BDW give an exact numeric
target: by-year psi (Table 9). Everywhere else BDW describe a PATTERN, not
a point target (e.g. Table 8: "smaller/insignificant for politics and
entertainment"), so this module reports those comparisons descriptively
rather than forcing a verdict label onto a target the source paper never
pinned to a number.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import polars as pl

from kalshi_mt.fees.schedule import FeeScheduleGapError, fee_usd_for
from kalshi_mt.r1.panel import price_band
from kalshi_mt.r1.regression import MZResult, fit_mz_regression
from kalshi_mt.util import now_utc_iso

# BDW Table 9 (spec S1): the one exact-number by-year reproduction target.
# 2025 covers Jan-Apr only (R1's own window boundary), not the full year.
BDW_PSI_BY_YEAR: dict[str, float] = {
    "2021": 0.041, "2022": 0.023, "2023": 0.036, "2024": 0.048, "2025": 0.021,
}


def _year_label(close_time_epoch: int | None) -> str | None:
    if close_time_epoch is None:
        return None
    return str(datetime.fromtimestamp(close_time_epoch, tz=timezone.utc).year)


def _verdict(fit: MZResult, bdw_psi: float) -> str:
    """confirmed: same sign as BDW AND our 95% CI contains BDW's point
    estimate. partially_confirmed: same sign, CI excludes BDW's point (a
    materially different magnitude). diverged: opposite sign."""
    ci_lo = fit.psi - 1.96 * fit.psi_se
    ci_hi = fit.psi + 1.96 * fit.psi_se
    if (fit.psi > 0) != (bdw_psi > 0):
        return "diverged"
    if ci_lo <= bdw_psi <= ci_hi:
        return "confirmed"
    return "partially_confirmed"


def by_year_psi(yes_only: pl.DataFrame) -> dict[str, dict[str, Any]]:
    if yes_only.is_empty():
        return {}
    df = yes_only.with_columns(
        pl.col("close_time_epoch").map_elements(_year_label, return_dtype=pl.String).alias("year")
    ).filter(pl.col("year").is_not_null())

    results: dict[str, dict[str, Any]] = {}
    for year in sorted(df["year"].unique().to_list()):
        fit = fit_mz_regression(df.filter(pl.col("year") == year))
        target = BDW_PSI_BY_YEAR.get(year)
        results[year] = {
            "fit": fit, "bdw_psi": target,
            "verdict": _verdict(fit, target) if (fit is not None and target is not None) else "insufficient_data",
        }
    return results


def by_category_psi(yes_only: pl.DataFrame) -> dict[str, dict[str, Any]]:
    """No exact BDW target per category (Table 8 gives a pattern only) --
    reported descriptively, verdict left to the reader/paper prose."""
    if yes_only.is_empty():
        return {}
    results: dict[str, dict[str, Any]] = {}
    for category in sorted(c for c in yes_only["category"].unique().to_list() if c):
        results[category] = {"fit": fit_mz_regression(yes_only.filter(pl.col("category") == category))}
    return results


def win_rate_by_band(doubled: pl.DataFrame) -> dict[str, dict[str, Any]]:
    """Fig 3's win-rate-vs-price curve, doubled Yes+No basis."""
    if doubled.is_empty():
        return {}
    df = doubled.with_columns(pl.col("p").map_elements(price_band, return_dtype=pl.String).alias("band"))
    results: dict[str, dict[str, Any]] = {}
    for (band,), group in df.group_by("band"):
        results[band] = {"n": len(group), "win_rate": float(group["y"].mean()), "mean_price": float(group["p"].mean())}
    return results


def returns_by_band(yes_only: pl.DataFrame, fee_schedule: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Fig 5's returns-by-10c-band: buy at EVERY observed panel price, hold to
    resolution. Gross (f=0) and net-of-taker-fee (BDW's own "takers only" fee
    model in their window), per docs/analysis_plan.md S3.1:
    r = (payout - P - f) / P. A market whose close_time predates the fee
    schedule's earliest entry (data/fees.yaml's documented gap) contributes to
    the gross figure but is excluded from net -- not silently zero-feed.

    Every panel observation is an entry price, NOT just the closing day's
    (lookback_day == 0), which is what this computed until 2026-07-26. BDW's
    own headline settles it -- they report an average pre-fee return of about
    -20%, and measured on our universe:

        all panel observations   -0.250   (n = 121,803)
        closing day only         -0.701   (n =  32,728)

    Restricting to the closing day is not a small variation: a contract still
    priced at 1-10c on its final day has almost no chance left, so that band
    alone comes out near -97% and drags the whole figure to -70%. Using all
    observations also matches the panel that feeds the MZ regression (BDW's
    n = 156,986 is the full price panel, not one row per contract), so Fig 5
    and the regression describe the same sample."""
    if yes_only.is_empty():
        return {}
    df = yes_only.with_columns(pl.col("p").map_elements(price_band, return_dtype=pl.String).alias("band"))

    results: dict[str, dict[str, Any]] = {}
    for (band,), group in df.group_by("band"):
        gross, net = [], []
        gap_excluded = 0
        for row in group.iter_rows(named=True):
            p, payout = row["p"], row["y"]
            if p <= 0:
                continue
            gross.append((payout - p) / p)
            as_of = datetime.fromtimestamp(row["close_time_epoch"], tz=timezone.utc).isoformat()
            # ACTUAL order size, never a hardcoded 1 (spec S1: "compute fees on
            # actual per-order contract counts", with BDW's own C=100 line
            # reproduced separately by fee_usd_bdw_illustration). The fee rounds
            # the ORDER TOTAL up to the next cent, so a 1-contract assumption
            # inflates the effective rate by up to 14x at 1c -- measured
            # 2026-07-26, that alone drove the 1-10c band's net return to
            # -181%, an arithmetic impossibility for a long position and a
            # distortion concentrated in exactly the tail bins the FLB headline
            # rests on. Per-contract fee is then count-invariant, which is the
            # point: it is a rate, not a per-order charge.
            count = row.get("count_fp")
            if count is None or count <= 0:
                gap_excluded += 1
                continue
            try:
                order_fee = fee_usd_for(fee_schedule, "taker", row["category"], count, p, as_of)
                fee_per_contract = order_fee / count
                net.append((payout - p - fee_per_contract) / p)
            except FeeScheduleGapError:
                gap_excluded += 1
        results[band] = {
            "n": len(group),
            "mean_gross_return": float(np.mean(gross)) if gross else None,
            "mean_net_return": float(np.mean(net)) if net else None,
            "fee_schedule_gap_excluded": gap_excluded,
        }
    return results


def maker_taker_split(
    doubled: pl.DataFrame, fee_schedule: dict[str, Any],
) -> dict[str, Any]:
    """Fig 6 / Table 10: post-fee return to Makers vs Takers, and Maker share
    by price band, over the DOUBLED PRICE PANEL.

    The unit of observation is a panel observation, not a fill -- verified
    against the primary PDF, which is explicit on both counts. Table 10 totals
    313,972 observations with Makers exactly 156,986, i.e. the doubled panel
    with one role per side of every observation; and the text states "Because
    we include the same contract at different points during its lifetime, we
    want to make sure that our results are not driven by the small minority of
    contracts that are in the sample up to 11 times" -- which only makes sense
    if the returns are computed over the up-to-11-per-contract panel.

    Averaging over all ~9.9M fills instead (what this did until 2026-07-27)
    gives a flat ~50% Maker share in every band and a far smaller return gap:
    the fill population is dominated by heavily-traded mid-price markets, while
    the panel weights each contract's lifetime equally.

    Role attribution follows the trade that SET each observation's price: if
    that trade's taker bought Yes, the Yes-side observation is the Taker's and
    the complementary No-side observation at (1 - p) is the Maker's, and vice
    versa. Kalshi records this directly, which is why BDW note it "eliminates a
    major source of measurement error" versus inferring direction Lee-Ready
    style.

    Fees are asymmetric and that is not incidental: Figure 6 reports POST-fee
    returns, and in BDW's window Makers paid no fee at all while Takers paid
    the 0.07*P*(1-P) order-total formula. Part of the headline gap is therefore
    the fee itself, not behaviour.
    """
    if doubled.is_empty():
        return {"maker_return": None, "taker_return": None, "maker_share_by_band": {}}

    maker_returns: list[float] = []
    taker_returns: list[float] = []
    maker_returns_50c_plus: list[float] = []
    band_counts: dict[str, dict[str, int]] = {}
    gap_excluded = 0

    for row in doubled.iter_rows(named=True):
        price, payout, side = row["p"], row["y"], row["side"]
        taker_side = row["taker_outcome_side"]
        if taker_side not in ("yes", "no") or price is None or not (0.0 < price < 1.0):
            continue
        role = "taker" if side == taker_side else "maker"

        band = price_band(price)
        counts = band_counts.setdefault(band, {"maker": 0, "total": 0})
        counts["total"] += 1
        if role == "maker":
            counts["maker"] += 1

        if role == "maker":
            # No maker fee in BDW's window -- post-fee equals gross here.
            ret = (payout - price) / price
            maker_returns.append(ret)
            if price >= 0.50:
                maker_returns_50c_plus.append(ret)
            continue

        count = row.get("count_fp")
        if count is None or count <= 0:
            gap_excluded += 1
            continue
        as_of = datetime.fromtimestamp(row["close_time_epoch"], tz=timezone.utc).isoformat()
        try:
            order_fee = fee_usd_for(fee_schedule, "taker", row["category"], count, price, as_of)
        except FeeScheduleGapError:
            gap_excluded += 1
            continue
        taker_returns.append((payout - price - order_fee / count) / price)

    return {
        "maker_return": float(np.mean(maker_returns)) if maker_returns else None,
        "taker_return": float(np.mean(taker_returns)) if taker_returns else None,
        "maker_return_50c_plus": (
            float(np.mean(maker_returns_50c_plus)) if maker_returns_50c_plus else None
        ),
        "n_maker_obs": len(maker_returns),
        "n_taker_obs": len(taker_returns),
        "fee_schedule_gap_excluded": gap_excluded,
        "maker_share_by_band": {
            band: (c["maker"] / c["total"] if c["total"] else None)
            for band, c in band_counts.items()
        },
    }


def write_divergence_log(report: dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"# R1 divergence log -- {now_utc_iso()}", ""]

    lines += ["## By-year psi vs BDW Table 9", "", "| Year | Our psi | BDW psi | Verdict |", "|---|---|---|---|"]
    for year, entry in sorted(report.get("by_year_psi", {}).items()):
        fit = entry["fit"]
        our_psi = f"{fit.psi:.4f}" if fit else "n/a"
        bdw = entry["bdw_psi"]
        lines.append(f"| {year} | {our_psi} | {bdw if bdw is not None else 'n/a'} | {entry['verdict']} |")
    lines.append("")

    lines += ["## By-category psi (descriptive, no BDW point target)", "", "| Category | psi | n |", "|---|---|---|"]
    for category, entry in sorted(report.get("by_category_psi", {}).items()):
        fit = entry["fit"]
        if fit:
            lines.append(f"| {category} | {fit.psi:.4f} | {fit.n} |")
        else:
            lines.append(f"| {category} | insufficient data | - |")
    lines.append("")

    field_population = report.get("taker_field_population_by_era")
    if field_population:
        lines += [
            "## Taker-field population by era (full Pass 2 tape)",
            "",
            "Step Zero Check 3 (reports/step_zero/findings.md) samples one market per "
            "era via a live probe -- three of its four eras returned zero trades for "
            "their sampled candidate, so its PASS verdict rests on a single 2021 market. "
            "This table recomputes the same population rates over every trade Pass 2 has "
            "actually fetched, per era.",
            "",
            "| Era | Trades | outcome_side pop. | book_side pop. | legacy taker_side pop. |",
            "|---|---|---|---|---|",
        ]
        for era, entry in field_population.items():
            label = "unassigned (unparseable/out-of-range)" if era == "_unassigned" else era
            n = entry.get("trade_count", 0)
            if n == 0:
                lines.append(f"| {label} | 0 | n/a | n/a | n/a |")
            else:
                lines.append(
                    f"| {label} | {n} | {entry['taker_outcome_side_population']:.4f} | "
                    f"{entry['taker_book_side_population']:.4f} | "
                    f"{entry['taker_side_legacy_population']:.4f} |"
                )
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path
