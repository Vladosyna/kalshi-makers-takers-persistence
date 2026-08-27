"""Escalation rule (docs/analysis_plan.md S5), verbatim:

  ## 5. Escalation rule (bound to S2.2's tests, no informal language)

  Escalate from a replication note to a standalone short paper iff:

  ( delta_bar_fee rejects zero at 5%, under the primary composition-weighted test )
                                OR
  ( delta_bar_pub rejects zero at 5%, under the primary composition-weighted test )
                                OR
  ( the maker >=50c margin changes sign between layers (a) and (c)
    AND survives the entire fee-sensitivity ribbon -- i.e. is NOT labeled 'fragile' per S3.3 )

  No other trigger. 'Materially regime-shifted' is not used as a standalone
  justification anywhere in this repo's write-up -- every escalation claim
  traces to one of the three conditions above.

AMENDED by docs/analysis_plan.md Addendum 3 (committed 2026-07-28, before
any estimate existed), which replaces the FEE arm of that OR:

  "Escalation (S5), tightened not loosened. The fee arm's trigger now reads
   off delta_did, and requires rejection at 5% in BOTH fits. That is a
   stricter bar than S5's original single test on delta_bar_fee, so this
   cannot manufacture an escalation that the committed rule would have
   withheld."

That amendment was written into the plan but never into this module, and the
gap decided an outcome: on 2026-08-26 the fee arm fired here on delta_bar_fee
(CI [+0.0071, +0.0726]) while both DiD fits contained zero (TWFE
[-0.0139, +0.0365], clean controls [-0.0141, +0.0109]), so the code said
escalate and the committed plan said do not.

Implementing it after the estimates were seen is defensible only because of
the property Addendum 3 asserts about itself: the amendment is strictly
stricter, so applying it can WITHHOLD an escalation but can never create one.
The reverse -- loosening a trigger after seeing a result -- would be
indefensible, and the distinction is the whole reason this is safe to correct
now rather than being frozen as a known-wrong implementation.

delta_bar_fee is still computed, still reported in `detail`, and still written
to the locked artifact (Addendum 3 keeps it deliberately: "Reporting only the
new estimand would hide a specification change instead of recording one"). It
simply no longer TRIGGERS.

This module implements that three-condition OR as a single pure function.
It does no I/O and performs no fetching -- every value it needs (the two
composition-weighted delta_bar estimates with their CIs, the two maker
margins, and the fee-sensitivity ribbon) is computed elsewhere and passed
in directly.

"Rejects zero at 5%" reuses this repo's own established convention
(r2/verdicts.py's _excludes_zero, used for S2.2's verdict tests): a 95% CI
"rejects zero" iff it strictly excludes zero (ci_lo > 0 or ci_hi < 0). A CI
edge that lands exactly on zero does NOT count as excluding it -- the
comparisons below use the same strict inequalities, not <=/>=.

None-handling: delta_bar_fee, delta_bar_pub, either maker margin, or the
ribbon can each independently be None (an estimate that could not be
computed from insufficient data -- an expected, documented possibility,
not an error condition). A None value simply means the condition(s) that
depend on it cannot fire; it never raises, and it never affects the other
conditions' evaluation. In particular, a None ribbon means the sign-flip
condition's fragility check has nothing to check, so that condition is
treated as NOT surviving the ribbon (you cannot claim a result "survives
the entire fee-sensitivity ribbon" when the ribbon was never run). If all
five inputs are None, determine_escalation returns escalate=False with an
empty triggers list -- not an error.

Sign-flip edge case: "changes sign between layers (a) and (c)" is
evaluated as sign(margin_a) != sign(margin_c), where sign is strictly
positive vs strictly negative. A margin of exactly 0.0 is deliberately
treated as having NEITHER sign -- it hasn't "flipped" to or from anything,
it's the boundary itself. This matters because the superficially
equivalent check `margin_a * margin_c < 0` happens to give the same
answer for "opposite strict signs" but for the wrong reason (it's a
product-sign trick, not a statement about what a sign flip means), and it
does not make the exactly-zero case explicit or documented -- a margin of
0.0 on either side yields product 0, which correctly fails the `< 0` test,
but only incidentally. _sign_of below makes the zero case a first-class,
explicit branch (sign 0, neither positive nor negative) so the "did it
flip" logic reads as what it means rather than relying on that
coincidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kalshi_mt.fees.ribbon import RibbonResult
from kalshi_mt.r2.verdicts import DeltaBarEstimate, _excludes_zero


@dataclass
class EscalationResult:
    escalate: bool
    triggers: list[str] = field(default_factory=list)
    detail: dict[str, Any] = field(default_factory=dict)


def _sign_of(x: float) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def _sign_flip(margin_a: float, margin_c: float) -> bool:
    sign_a = _sign_of(margin_a)
    sign_c = _sign_of(margin_c)
    if sign_a == 0 or sign_c == 0:
        return False
    return sign_a != sign_c


def _delta_bar_detail(estimate: DeltaBarEstimate | None) -> dict[str, Any]:
    if estimate is None:
        return {"available": False, "delta_bar": None, "ci_lo": None, "ci_hi": None, "rejects_zero": False}
    rejects_zero = _excludes_zero(estimate.ci_lo, estimate.ci_hi)
    return {
        "available": True,
        "delta_bar": estimate.delta_bar,
        "ci_lo": estimate.ci_lo,
        "ci_hi": estimate.ci_hi,
        "rejects_zero": rejects_zero,
    }


def _maker_margin_detail(
    maker_margin_layer_a: float | None,
    maker_margin_layer_c: float | None,
    ribbon: RibbonResult | None,
) -> dict[str, Any]:
    margins_available = maker_margin_layer_a is not None and maker_margin_layer_c is not None
    sign_flip = _sign_flip(maker_margin_layer_a, maker_margin_layer_c) if margins_available else False
    ribbon_available = ribbon is not None
    ribbon_fragile = ribbon.fragile if ribbon_available else None
    survives_ribbon = ribbon_available and not ribbon.fragile
    condition_met = margins_available and sign_flip and survives_ribbon
    return {
        "margins_available": margins_available,
        "layer_a": maker_margin_layer_a,
        "layer_c": maker_margin_layer_c,
        "sign_flip": sign_flip,
        "ribbon_available": ribbon_available,
        "ribbon_fragile": ribbon_fragile,
        "survives_ribbon": survives_ribbon,
        "condition_met": condition_met,
    }


DID_FITS = ("twfe", "clean_controls")


def _did_fee_detail(fits: dict[str, DeltaBarEstimate | None] | None) -> dict[str, Any]:
    """The fee arm per Addendum 3: rejection at 5% in BOTH fits.

    A fit that is absent or None means "not identified", which Addendum 3 is
    explicit must never be read as a null result. Here that distinction has
    one consequence: an unidentified fit cannot reject zero, so the trigger
    cannot fire on it -- and `identified` records why, rather than leaving a
    False that looks like a measured non-rejection."""
    fits = fits or {}
    per_fit: dict[str, Any] = {}
    for name in DID_FITS:
        est = fits.get(name)
        if est is None:
            per_fit[name] = {
                "identified": False, "delta_did": None,
                "ci_lo": None, "ci_hi": None, "rejects_zero": False,
            }
            continue
        per_fit[name] = {
            "identified": True,
            "delta_did": est.delta_bar,
            "ci_lo": est.ci_lo,
            "ci_hi": est.ci_hi,
            "rejects_zero": _excludes_zero(est.ci_lo, est.ci_hi),
        }
    both_reject = all(per_fit[n]["rejects_zero"] for n in DID_FITS)
    return {
        "rule": "Addendum 3: rejection at 5% required in BOTH fits",
        "fits": per_fit,
        "condition_met": both_reject,
    }


def determine_escalation(
    delta_bar_fee: DeltaBarEstimate | None,
    delta_bar_pub: DeltaBarEstimate | None,
    maker_margin_layer_a: float | None,
    maker_margin_layer_c: float | None,
    ribbon: RibbonResult | None,
    did_fee_fits: dict[str, DeltaBarEstimate | None] | None = None,
) -> EscalationResult:
    """The pure S5 escalation OR, with Addendum 3's fee arm. Every condition
    is evaluated independently -- no short-circuiting -- so `triggers` can
    report all conditions that fired, not just the first one checked."""
    detail: dict[str, Any] = {}
    triggers: list[str] = []

    # delta_bar_fee is REPORTED but no longer TRIGGERS -- Addendum 3 moved the
    # fee arm onto the DiD. Kept in `detail` so a reader can see both, which is
    # the point of retaining it at all.
    fee_detail = _delta_bar_detail(delta_bar_fee)
    fee_detail["triggers_escalation"] = False
    fee_detail["superseded_by"] = "did_fee (Addendum 3)"
    detail["delta_bar_fee"] = fee_detail

    did_detail = _did_fee_detail(did_fee_fits)
    detail["did_fee"] = did_detail
    if did_detail["condition_met"]:
        triggers.append("did_fee_significant_in_both_fits")

    pub_detail = _delta_bar_detail(delta_bar_pub)
    detail["delta_bar_pub"] = pub_detail
    if pub_detail["rejects_zero"]:
        triggers.append("delta_bar_pub_significant")

    margin_detail = _maker_margin_detail(maker_margin_layer_a, maker_margin_layer_c, ribbon)
    detail["maker_margin_sign_flip"] = margin_detail
    if margin_detail["condition_met"]:
        triggers.append("maker_margin_sign_flip_survives_ribbon")

    return EscalationResult(escalate=bool(triggers), triggers=triggers, detail=detail)
