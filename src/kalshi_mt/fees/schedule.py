"""Kalshi fee schedule lookup (spec S3/S4) -- right-continuous step function
keyed on trade FILL timestamp, never seeded from a "current" row backwards.

data/fees.yaml is GENERATED from the archived primary artifacts by
tools/build_fees_yaml.py; its header carries the sourcing and the one known
scope gap. Three facts from those artifacts drive this module's shape, and
none of them survive the older "one rate per (role, category)" model:

1. **Fees have two functional forms.** The general fee is quadratic in price,
   ceil_to_cent(rate * C * P * (1-P)); but Kalshi's FIRST maker fee
   (2025-05-13 .. 2025-07-07) was FLAT per contract, ceil_to_cent(rate * C),
   with no price dependence at all. Applying the quadratic form to that era
   understates the fee ~3x at 5c and overstates it ~75% at 50c.

2. **Scope is per SERIES (and, for the index carve-out, per ticker prefix) --
   never per category.** The maker fee is a surcharge on an enumerated list of
   series; resting orders elsewhere are free, in the schedule's own words,
   "unless they are included in our 'Maker Fees' section". Category never
   determined a Kalshi fee; keying on it was wrong even when it happened to
   give the right answer.

3. **Specificity, then recency -- in that order, and generation-wise.** Two
   entries can both apply to a fill (the general taker rate and the S&P/Nasdaq
   half rate). The more specific scope wins. But within one scope kind, only
   the LATEST generation applies: when a series left the maker-fee list on
   2025-09-17, the older 2025-09-02 entry that still names it must not keep
   charging it. Hence: take the newest generation per scope kind, then walk
   kinds from most to least specific and use the first that matches. A plain
   "latest matching entry" rule silently gets that case wrong.

Return convention is pinned separately in docs/analysis_plan.md S3.1
(r = (payout - P - f) / P) -- this module only computes the fee itself.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Literal

import yaml

Role = Literal["maker", "taker"]
Form = Literal["quadratic", "flat_per_contract", "none"]

# Most specific first. `series` matches a market's series ticker exactly;
# `ticker_prefix` matches the market ticker's leading characters (the fee
# schedule's own rule for the index carve-out: "any other market beginning
# with the INX ticker"); `all` matches everything.
_SPECIFICITY: tuple[str, ...] = ("series", "ticker_prefix", "all")


class FeeScheduleGapError(RuntimeError):
    """Raised when a lookup timestamp predates every known fee entry for a
    role -- a right-continuous step function has nothing to return here.
    Silently defaulting (to 0.0, or to the earliest known rate) would
    corrupt every downstream net-of-cost number without anyone noticing;
    the approved implementation plan's own Phase 4 design is explicit that
    this must raise, not fail-soft."""


def bdw_fee_model() -> dict[str, Any]:
    """BDW's own stated fee model, as a schedule: takers pay 0.07*P*(1-P) on
    every market for the whole 2021-2025 window, makers pay nothing.

    R1's PRIMARY net-return figures use this, not the sourced schedule, and
    that is deliberate. R1's job is to reproduce BDW's numbers; if we priced
    their sample with a fee schedule they did not use, any gap in Fig 5 would
    be our fee model talking, not their data or method. The sourced schedule
    runs alongside as the sensitivity branch, and the difference between the
    two IS a finding -- see docs/r1_reproduction_findings.md:

      * 18.3% of R1's in-scope universe is S&P500/Nasdaq-100 markets, which
        pay HALF the general taker rate;
      * 45 in-scope markets closed while the rate was 0.14, not 0.07.

    Neither appears in BDW's single-formula treatment. Both are small in
    aggregate and neither touches the gross-return or psi results, which is
    exactly why stating it precisely is cheap and worth doing.
    """
    return {
        "version": 2,
        "provenance": "BDW's stated model, not Kalshi's published schedule",
        "schedule": [
            {"effective_from": "2021-01-01", "role": "taker", "form": "quadratic",
             "rate": 0.07, "scope": {"kind": "all"}},
            {"effective_from": "2021-01-01", "role": "maker", "form": "none",
             "rate": 0.0, "scope": {"kind": "all"}},
        ],
    }


def load_fee_schedule(path: Path | None = None) -> dict[str, Any]:
    """Defaults to PROJECT_ROOT / "data" / "fees.yaml", resolved via a
    local import (not a module-level constant) so that test monkeypatching
    of util.PROJECT_ROOT actually takes effect -- a constant derived once
    at import time would freeze to whatever PROJECT_ROOT was at first
    import and silently ignore any later monkeypatch.setattr."""
    if path is None:
        from kalshi_mt.util import PROJECT_ROOT

        path = PROJECT_ROOT / "data" / "fees.yaml"
    p = path
    if not p.exists():
        return {"version": 0, "schedule": []}
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    data.setdefault("schedule", [])
    return data


def _scope_matches(scope: dict[str, Any], market_ticker: str | None, series_ticker: str | None) -> bool:
    kind = scope.get("kind", "all")
    if kind == "all":
        return True
    if kind == "series":
        return series_ticker is not None and series_ticker in set(scope.get("series", ()))
    if kind == "ticker_prefix":
        if market_ticker is None:
            return False
        return any(market_ticker.startswith(prefix) for prefix in scope.get("prefixes", ()))
    return False


def entry_for(
    schedule: dict[str, Any], role: Role, as_of_ts: str,
    *, market_ticker: str | None = None, series_ticker: str | None = None,
) -> dict[str, Any]:
    """The fee entry governing a fill of `role` at `as_of_ts` for this market.

    Raises FeeScheduleGapError if as_of_ts predates every known entry for the
    role, or if no entry's scope matches (which can only happen in a schedule
    with no `all`-scoped fallback for that role -- a malformed schedule, not a
    data condition to absorb)."""
    role_entries = [e for e in schedule.get("schedule", []) if e.get("role") == role]
    if not role_entries:
        raise FeeScheduleGapError(f"no fee schedule entries at all for role={role!r}")

    earliest = min(e["effective_from"] for e in role_entries)
    if as_of_ts < earliest:
        raise FeeScheduleGapError(
            f"as_of_ts={as_of_ts!r} predates the earliest known {role!r} fee entry "
            f"({earliest!r}) -- a genuine gap in data/fees.yaml, not a bug to paper "
            "over with a default rate."
        )

    applicable = [e for e in role_entries if e.get("effective_from", "") <= as_of_ts]
    for kind in _SPECIFICITY:
        of_kind = [e for e in applicable if e.get("scope", {}).get("kind", "all") == kind]
        if not of_kind:
            continue
        # Only the newest generation of this scope kind is in force -- see the
        # module docstring's point 3 for why "latest matching entry" is wrong.
        newest = max(e["effective_from"] for e in of_kind)
        current = [e for e in of_kind if e["effective_from"] == newest]
        for candidate in current:
            if _scope_matches(candidate.get("scope", {}), market_ticker, series_ticker):
                return candidate
    raise FeeScheduleGapError(
        f"no fee entry scope matches role={role!r} market_ticker={market_ticker!r} "
        f"series_ticker={series_ticker!r} at {as_of_ts!r}; data/fees.yaml is missing "
        "an `all`-scoped fallback for this role."
    )


def rate_for(
    schedule: dict[str, Any], role: Role, as_of_ts: str,
    *, market_ticker: str | None = None, series_ticker: str | None = None,
) -> float:
    """The governing entry's rate. Note that a rate alone does not determine a
    fee: read `form` from entry_for when the distinction matters."""
    return float(entry_for(
        schedule, role, as_of_ts, market_ticker=market_ticker, series_ticker=series_ticker
    )["rate"])


def _ceil_to_cent(dollars: float) -> float:
    # Tiny epsilon guards an exact-cent float (e.g. 1.7500000000000002 from
    # binary floating point) from being spuriously rounded up an extra cent.
    return math.ceil(dollars * 100.0 - 1e-9) / 100.0


def fee_usd_for(
    schedule: dict[str, Any], role: Role,
    contract_count: float, price_dollars: float, as_of_ts: str,
    *, market_ticker: str | None = None, series_ticker: str | None = None,
) -> float:
    """Fee on the ORDER TOTAL for `contract_count` contracts -- BDW's own
    construction ("total rounded up to the next cent"), not a per-contract
    rounding multiplied out.

      quadratic          ceil_to_cent(rate * C * P * (1-P))
      flat_per_contract  ceil_to_cent(rate * C)
      none               0.0
    """
    entry = entry_for(
        schedule, role, as_of_ts, market_ticker=market_ticker, series_ticker=series_ticker
    )
    form: Form = entry.get("form", "quadratic")
    rate = float(entry["rate"])
    if form == "none" or rate == 0.0:
        return 0.0
    if form == "flat_per_contract":
        return _ceil_to_cent(rate * contract_count)
    return _ceil_to_cent(rate * contract_count * price_dollars * (1.0 - price_dollars))


def fee_usd_bdw_illustration(
    schedule: dict[str, Any], role: Role, price_dollars: float, as_of_ts: str,
    *, market_ticker: str | None = None, series_ticker: str | None = None,
) -> float:
    """BDW's own illustrative figure: the fee on a FIXED 100-contract order
    (their own "~1.77% at 50c" line, spec S1). Reported ALONGSIDE the
    actual-order-size fee_usd_for figure, never as a substitute for it."""
    return fee_usd_for(
        schedule, role, 100.0, price_dollars, as_of_ts,
        market_ticker=market_ticker, series_ticker=series_ticker,
    )
