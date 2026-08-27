from __future__ import annotations

from kalshi_mt.fees.ribbon import RibbonResult
from kalshi_mt.r2.verdicts import DeltaBarEstimate
from kalshi_mt.report.escalation import determine_escalation

SIGNIFICANT_FEE = DeltaBarEstimate(delta_bar=-2.0, ci_lo=-3.0, ci_hi=-1.0)
NOT_SIGNIFICANT = DeltaBarEstimate(delta_bar=0.1, ci_lo=-0.5, ci_hi=0.5)

FRAGILE_RIBBON = RibbonResult(
    rates=[0.0, 0.01], margins=[1.0, -1.0], break_even_rate=0.005, sign_flips=True, fragile=True,
)
SURVIVING_RIBBON = RibbonResult(
    rates=[0.0, 0.01], margins=[1.0, 2.0], break_even_rate=None, sign_flips=False, fragile=False,
)

# The fee arm reads off the DiD in BOTH fits (analysis_plan.md Addendum 3).
BOTH_DID_REJECT = {"twfe": SIGNIFICANT_FEE, "clean_controls": SIGNIFICANT_FEE}
ONE_DID_REJECTS = {"twfe": SIGNIFICANT_FEE, "clean_controls": NOT_SIGNIFICANT}
NEITHER_DID_REJECTS = {"twfe": NOT_SIGNIFICANT, "clean_controls": NOT_SIGNIFICANT}


def test_delta_bar_fee_alone_no_longer_triggers():
    """Addendum 3 moved the fee arm onto the DiD. delta_bar_fee is still
    reported -- the plan keeps it deliberately -- but a significant one with
    no DiD behind it must NOT escalate. This is the exact case that fired on
    2026-08-26 under the unamended code."""
    result = determine_escalation(SIGNIFICANT_FEE, None, None, None, None)
    assert result.escalate is False
    assert result.triggers == []
    assert result.detail["delta_bar_fee"]["rejects_zero"] is True
    assert result.detail["delta_bar_fee"]["triggers_escalation"] is False
    assert result.detail["did_fee"]["condition_met"] is False
    assert result.detail["did_fee"]["fits"]["twfe"]["identified"] is False


def test_did_fee_triggers_only_when_both_fits_reject():
    both = determine_escalation(None, None, None, None, None, did_fee_fits=BOTH_DID_REJECT)
    assert both.escalate is True
    assert both.triggers == ["did_fee_significant_in_both_fits"]

    one = determine_escalation(None, None, None, None, None, did_fee_fits=ONE_DID_REJECTS)
    assert one.escalate is False
    assert one.detail["did_fee"]["fits"]["twfe"]["rejects_zero"] is True
    assert one.detail["did_fee"]["fits"]["clean_controls"]["rejects_zero"] is False

    neither = determine_escalation(None, None, None, None, None, did_fee_fits=NEITHER_DID_REJECTS)
    assert neither.escalate is False


def test_unidentified_did_fit_is_not_a_null_result():
    """Addendum 3: a fit with no treated rows / no controls / one month is
    'not identified', reported as such and never as a null. It cannot reject,
    so it cannot trigger -- and `identified` says which of the two it was."""
    result = determine_escalation(
        None, None, None, None, None,
        did_fee_fits={"twfe": SIGNIFICANT_FEE, "clean_controls": None},
    )
    assert result.escalate is False
    fits = result.detail["did_fee"]["fits"]
    assert fits["twfe"]["identified"] is True and fits["twfe"]["rejects_zero"] is True
    assert fits["clean_controls"]["identified"] is False
    assert fits["clean_controls"]["rejects_zero"] is False


def test_delta_bar_pub_significant_triggers_alone():
    result = determine_escalation(None, SIGNIFICANT_FEE, None, None, None)
    assert result.escalate is True
    assert result.triggers == ["delta_bar_pub_significant"]
    assert result.detail["delta_bar_fee"]["available"] is False
    assert result.detail["delta_bar_pub"]["rejects_zero"] is True


def test_maker_margin_sign_flip_survives_ribbon_triggers_alone():
    result = determine_escalation(None, None, 5.0, -3.0, SURVIVING_RIBBON)
    assert result.escalate is True
    assert result.triggers == ["maker_margin_sign_flip_survives_ribbon"]
    detail = result.detail["maker_margin_sign_flip"]
    assert detail["sign_flip"] is True
    assert detail["survives_ribbon"] is True
    assert detail["layer_a"] == 5.0
    assert detail["layer_c"] == -3.0


def test_all_conditions_false_or_none_yields_no_escalation():
    result = determine_escalation(NOT_SIGNIFICANT, NOT_SIGNIFICANT, 5.0, 3.0, SURVIVING_RIBBON)
    assert result.escalate is False
    assert result.triggers == []


def test_all_five_inputs_none_yields_no_escalation():
    result = determine_escalation(None, None, None, None, None)
    assert result.escalate is False
    assert result.triggers == []
    assert result.detail["delta_bar_fee"]["available"] is False
    assert result.detail["maker_margin_sign_flip"]["margins_available"] is False


def test_multiple_conditions_firing_are_all_reported():
    result = determine_escalation(
        SIGNIFICANT_FEE, SIGNIFICANT_FEE, 5.0, -3.0, SURVIVING_RIBBON,
        did_fee_fits=BOTH_DID_REJECT,
    )
    assert result.escalate is True
    assert set(result.triggers) == {
        "did_fee_significant_in_both_fits",
        "delta_bar_pub_significant",
        "maker_margin_sign_flip_survives_ribbon",
    }
    assert len(result.triggers) == 3


def test_sign_flip_with_fragile_ribbon_does_not_escalate():
    result = determine_escalation(None, None, 5.0, -3.0, FRAGILE_RIBBON)
    assert result.escalate is False
    assert result.triggers == []
    detail = result.detail["maker_margin_sign_flip"]
    assert detail["sign_flip"] is True
    assert detail["ribbon_fragile"] is True
    assert detail["survives_ribbon"] is False
    assert detail["condition_met"] is False


def test_no_sign_flip_with_non_fragile_ribbon_does_not_escalate():
    result = determine_escalation(None, None, 5.0, 3.0, SURVIVING_RIBBON)
    assert result.escalate is False
    detail = result.detail["maker_margin_sign_flip"]
    assert detail["sign_flip"] is False
    assert detail["survives_ribbon"] is True
    assert detail["condition_met"] is False


def test_none_ribbon_with_qualifying_sign_flip_does_not_escalate():
    result = determine_escalation(None, None, 5.0, -3.0, None)
    assert result.escalate is False
    assert result.triggers == []
    detail = result.detail["maker_margin_sign_flip"]
    assert detail["sign_flip"] is True
    assert detail["ribbon_available"] is False
    assert detail["ribbon_fragile"] is None
    assert detail["survives_ribbon"] is False
    assert detail["condition_met"] is False


def test_delta_bar_ci_touching_zero_at_lo_does_not_reject():
    estimate = DeltaBarEstimate(delta_bar=1.0, ci_lo=0.0, ci_hi=2.0)
    result = determine_escalation(estimate, None, None, None, None)
    assert result.escalate is False
    assert result.detail["delta_bar_fee"]["rejects_zero"] is False


def test_delta_bar_ci_touching_zero_at_hi_does_not_reject():
    estimate = DeltaBarEstimate(delta_bar=-1.0, ci_lo=-2.0, ci_hi=0.0)
    result = determine_escalation(None, estimate, None, None, None)
    assert result.escalate is False
    assert result.detail["delta_bar_pub"]["rejects_zero"] is False


def test_exactly_zero_margin_layer_a_is_not_a_sign_flip():
    result = determine_escalation(None, None, 0.0, -3.0, SURVIVING_RIBBON)
    assert result.escalate is False
    detail = result.detail["maker_margin_sign_flip"]
    assert detail["sign_flip"] is False
    assert detail["condition_met"] is False


def test_exactly_zero_margin_layer_c_is_not_a_sign_flip():
    result = determine_escalation(None, None, 5.0, 0.0, SURVIVING_RIBBON)
    assert result.escalate is False
    detail = result.detail["maker_margin_sign_flip"]
    assert detail["sign_flip"] is False
    assert detail["condition_met"] is False


def test_both_margins_exactly_zero_is_not_a_sign_flip():
    result = determine_escalation(None, None, 0.0, 0.0, SURVIVING_RIBBON)
    assert result.escalate is False
    detail = result.detail["maker_margin_sign_flip"]
    assert detail["sign_flip"] is False
    assert detail["condition_met"] is False
