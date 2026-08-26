"""Fee-sensitivity ribbon (docs/analysis_plan.md S3.3): recompute a margin
across a fee-rate grid, find its break-even rate, and apply the
pre-registered "fragile" rule -- a sign flip anywhere inside the plausible
fee band means that result is labeled fragile and cannot trigger
escalation on its own (spec S5), regardless of the point estimate at the
actual sourced rate.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable

log = logging.getLogger(__name__)


@dataclass
class RibbonResult:
    rates: list[float]
    margins: list[float]
    break_even_rate: float | None  # None if the margin never crosses zero across the grid
    sign_flips: bool               # True if the margin's sign differs anywhere in the grid
    fragile: bool                  # sign_flips, restated as the pre-registered label


def default_fee_grid(sourced_rate: float, plausible_band: float = 0.5) -> list[float]:
    """Zero-fee plus a 10-point sweep spanning
    [sourced_rate*(1-band), sourced_rate*(1+band)] -- analysis_plan.md
    S3.3's "zero-fee; ... plausible maker-fee bounds" grid."""
    lo = sourced_rate * (1 - plausible_band)
    hi = sourced_rate * (1 + plausible_band)
    step = (hi - lo) / 9 if hi > lo else 0.0
    grid = [0.0] + [round(lo + i * step, 8) for i in range(10)]
    return sorted(set(grid))


def compute_ribbon(margin_fn: Callable[[float], float], rates: list[float]) -> RibbonResult:
    """margin_fn(rate) -> the margin's value at that flat fee rate (e.g. a
    maker>=50c average return, or a tail-bin loss rate, recomputed with the
    fee rate substituted). The sign_flips/fragile flags are read directly
    off the sampled margins, not off the interpolated break-even, so they
    stay correct even where margin_fn isn't perfectly monotonic in rate."""
    if not rates:
        return RibbonResult(rates=[], margins=[], break_even_rate=None, sign_flips=False, fragile=False)

    # Log every evaluation. margin_fn re-reads the whole in-scope tape, and on
    # the real R2 universe that is ~134M fills per call against an 11-point
    # grid: the escalate run of 2026-08-26 spent NINETEEN HOURS in here with no
    # output at all, and working out how far along it was took a morning of
    # inference from spill-directory names and CPU counters. Two lines of
    # progress would have answered it immediately. Cheap at one line per call,
    # which is once every tens of minutes.
    margins = []
    for i, r in enumerate(rates, 1):
        t0 = time.monotonic()
        margins.append(margin_fn(r))
        log.info(
            "fee-sensitivity ribbon: rate %d/%d (%.6f) -> margin %s in %.0fs",
            i, len(rates), r, f"{margins[-1]:.6f}", time.monotonic() - t0,
        )
    signs = {m > 0 for m in margins}
    sign_flips = len(signs) > 1

    break_even = None
    for i in range(len(rates) - 1):
        m0, m1 = margins[i], margins[i + 1]
        if (m0 > 0) != (m1 > 0) and m1 != m0:
            r0, r1 = rates[i], rates[i + 1]
            break_even = r0 + (0 - m0) * (r1 - r0) / (m1 - m0)
            break

    return RibbonResult(
        rates=rates, margins=margins, break_even_rate=break_even,
        sign_flips=sign_flips, fragile=sign_flips,
    )
