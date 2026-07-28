from __future__ import annotations

import pytest

from kalshi_mt.fees.schedule import (
    FeeScheduleGapError,
    entry_for,
    fee_usd_bdw_illustration,
    fee_usd_for,
    load_fee_schedule,
    rate_for,
)


def _schedule():
    """A miniature of data/fees.yaml's real shape: two taker generations, a
    ticker-prefix carve-out, and three maker generations whose scopes are
    NOT nested (KXOLD leaves the list in the third)."""
    return {
        "version": 2,
        "schedule": [
            {"effective_from": "2021-07-01", "role": "taker", "form": "quadratic",
             "rate": 0.14, "scope": {"kind": "all"}},
            {"effective_from": "2021-08-01", "role": "taker", "form": "quadratic",
             "rate": 0.07, "scope": {"kind": "all"}},
            {"effective_from": "2022-09-26", "role": "taker", "form": "quadratic",
             "rate": 0.035, "scope": {"kind": "ticker_prefix", "prefixes": ["INX", "NASDAQ100"]}},
            {"effective_from": "2021-07-01", "role": "maker", "form": "none",
             "rate": 0.0, "scope": {"kind": "all"}},
            {"effective_from": "2025-05-13", "role": "maker", "form": "flat_per_contract",
             "rate": 0.0025, "scope": {"kind": "series", "series": ["KXNBA", "KXOLD"]}},
            {"effective_from": "2025-07-08", "role": "maker", "form": "quadratic",
             "rate": 0.0175, "scope": {"kind": "series", "series": ["KXNBA", "KXOLD"]}},
            {"effective_from": "2025-09-17", "role": "maker", "form": "quadratic",
             "rate": 0.0175, "scope": {"kind": "series", "series": ["KXNBA"]}},
        ],
    }


# --- taker: rate generations and the index carve-out -------------------------


def test_taker_rate_was_double_in_the_first_weeks_of_2021():
    """The 2021-07-20 schedule says 14%, not 7% -- a real, dated rate change
    inside BDW's own sample window."""
    s = _schedule()
    assert rate_for(s, "taker", "2021-07-15T00:00:00Z") == 0.14
    assert rate_for(s, "taker", "2021-08-01T00:00:00Z") == 0.07
    assert rate_for(s, "taker", "2026-01-01T00:00:00Z") == 0.07


def test_index_markets_pay_half_the_general_taker_rate():
    s = _schedule()
    assert rate_for(s, "taker", "2023-01-01", market_ticker="INXD-23JAN03-B4000") == 0.035
    assert rate_for(s, "taker", "2023-01-01", market_ticker="NASDAQ100W-23JAN06") == 0.035
    assert rate_for(s, "taker", "2023-01-01", market_ticker="KXNBA-23JAN03-LAL") == 0.07


def test_index_carveout_does_not_apply_before_it_appears():
    s = _schedule()
    assert rate_for(s, "taker", "2022-01-01", market_ticker="INXD-22JAN03-B4000") == 0.07


def test_unknown_ticker_falls_back_to_the_general_rate():
    s = _schedule()
    assert rate_for(s, "taker", "2023-01-01") == 0.07


# --- maker: scope is per series, and generations supersede -------------------


def test_maker_pays_nothing_outside_the_listed_series():
    s = _schedule()
    assert rate_for(s, "maker", "2025-08-01", series_ticker="KXPRES") == 0.0
    assert fee_usd_for(s, "maker", 100.0, 0.5, "2025-08-01", series_ticker="KXPRES") == 0.0


def test_maker_pays_nothing_anywhere_before_the_first_maker_fee():
    s = _schedule()
    assert fee_usd_for(s, "maker", 100.0, 0.5, "2025-05-12", series_ticker="KXNBA") == 0.0


def test_maker_first_form_is_flat_per_contract_not_quadratic():
    """round up(0.0025 x C): no price dependence at all. The quadratic form
    would give a different answer at every price except by coincidence."""
    s = _schedule()
    at_50c = fee_usd_for(s, "maker", 1000.0, 0.50, "2025-06-01", series_ticker="KXNBA")
    at_05c = fee_usd_for(s, "maker", 1000.0, 0.05, "2025-06-01", series_ticker="KXNBA")
    assert at_50c == at_05c == pytest.approx(2.50)


def test_maker_switches_to_quadratic_on_2025_07_08():
    s = _schedule()
    fee = fee_usd_for(s, "maker", 1000.0, 0.50, "2025-07-08", series_ticker="KXNBA")
    # 0.0175 * 1000 * 0.5 * 0.5 = 4.375 -> ceil to the next cent
    assert fee == pytest.approx(4.38)
    assert fee != fee_usd_for(s, "maker", 1000.0, 0.05, "2025-07-08", series_ticker="KXNBA")


def test_a_series_that_left_the_list_stops_paying():
    """The newest generation of a scope kind supersedes older ones wholesale.
    A 'latest matching entry' rule would keep charging KXOLD forever off the
    2025-07-08 row, which still names it."""
    s = _schedule()
    assert rate_for(s, "maker", "2025-09-16", series_ticker="KXOLD") == 0.0175
    assert rate_for(s, "maker", "2025-09-17", series_ticker="KXOLD") == 0.0
    assert rate_for(s, "maker", "2025-09-17", series_ticker="KXNBA") == 0.0175


def test_series_scope_needs_the_series_ticker_not_the_market_ticker():
    s = _schedule()
    assert rate_for(s, "maker", "2025-08-01", market_ticker="KXNBA-25JAN03-LAL") == 0.0
    assert rate_for(s, "maker", "2025-08-01", series_ticker="KXNBA") == 0.0175


# --- formula, rounding, gaps -------------------------------------------------


def test_fee_usd_for_matches_hand_computed_formula():
    s = _schedule()
    fee = fee_usd_for(s, "taker", 100.0, 0.50, "2023-01-01")
    assert fee == pytest.approx(1.75)


def test_fee_usd_for_ceils_to_cent_on_order_total():
    s = _schedule()
    # 0.07 * 1 * 0.30 * 0.70 = 0.0147 -> ceils to two cents, and the ceiling
    # applies to the ORDER, so a 1-contract order pays 1.36x the rate itself.
    assert fee_usd_for(s, "taker", 1.0, 0.30, "2023-01-01") == pytest.approx(0.02)
    # 100 contracts: 1.47 exactly, no rounding penalty at all.
    assert fee_usd_for(s, "taker", 100.0, 0.30, "2023-01-01") == pytest.approx(1.47)


def test_fee_usd_for_zero_at_price_extremes():
    s = _schedule()
    assert fee_usd_for(s, "taker", 100.0, 0.0, "2023-01-01") == 0.0
    assert fee_usd_for(s, "taker", 100.0, 0.999, "2023-01-01") == pytest.approx(0.01)


def test_flat_form_ceils_the_order_total_too():
    s = _schedule()
    # 0.0025 * 3 = 0.0075 -> one cent for the whole order, not three
    assert fee_usd_for(s, "maker", 3.0, 0.5, "2025-06-01", series_ticker="KXNBA") == pytest.approx(0.01)


def test_raises_on_date_before_earliest_entry():
    s = _schedule()
    with pytest.raises(FeeScheduleGapError):
        rate_for(s, "taker", "2020-01-01T00:00:00Z")


def test_raises_on_unknown_role():
    s = _schedule()
    with pytest.raises(FeeScheduleGapError):
        rate_for(s, "unknown_role", "2023-01-01")  # type: ignore[arg-type]


def test_entry_for_exposes_the_form():
    s = _schedule()
    assert entry_for(s, "maker", "2025-06-01", series_ticker="KXNBA")["form"] == "flat_per_contract"
    assert entry_for(s, "maker", "2025-08-01", series_ticker="KXNBA")["form"] == "quadratic"


def test_fee_usd_bdw_illustration_uses_fixed_100_contracts():
    s = _schedule()
    illustration = fee_usd_bdw_illustration(s, "taker", 0.50, "2023-01-01")
    assert illustration == pytest.approx(fee_usd_for(s, "taker", 100.0, 0.50, "2023-01-01"))


def test_fee_usd_bdw_illustration_independent_of_real_order_size():
    s = _schedule()
    small_order_fee = fee_usd_for(s, "taker", 3.0, 0.50, "2023-01-01")
    illustration = fee_usd_bdw_illustration(s, "taker", 0.50, "2023-01-01")
    assert small_order_fee != pytest.approx(illustration)


def test_load_fee_schedule_missing_file_returns_empty(tmp_path):
    data = load_fee_schedule(tmp_path / "does_not_exist.yaml")
    assert data == {"version": 0, "schedule": []}


# --- the shipped artifact ----------------------------------------------------


def test_shipped_schedule_reproduces_the_archived_documents():
    """Guards data/fees.yaml against a regeneration that silently changes what
    the archived PDFs say. Every assertion here is a quantity read directly
    off a document in docs/sources/fees/."""
    data = load_fee_schedule()
    assert data["version"] == 2

    # Taker: 14% in the 2021-07-20 capture, 7% from the 2021-08-01 one on.
    assert rate_for(data, "taker", "2021-07-15") == 0.14
    assert rate_for(data, "taker", "2023-01-01") == 0.07
    assert rate_for(data, "taker", "2026-06-01") == 0.07
    # S&P/Nasdaq half rate, present in every capture from 2022-09 onward.
    assert rate_for(data, "taker", "2024-01-01", market_ticker="INXD-24JAN02-B4800") == 0.035

    # Maker: nothing before 2025-05-13, then flat, then quadratic.
    assert rate_for(data, "maker", "2025-05-12", series_ticker="KXNBA") == 0.0
    assert entry_for(data, "maker", "2025-05-13", series_ticker="KXNBA")["form"] == "flat_per_contract"
    assert entry_for(data, "maker", "2025-07-08", series_ticker="KXNBA")["form"] == "quadratic"
    assert rate_for(data, "maker", "2025-07-08", series_ticker="KXNBA") == 0.0175
    # ...and never for a series outside the list, in any era.
    assert rate_for(data, "maker", "2026-01-01", series_ticker="KXPRESPARTY") == 0.0


def test_bdw_model_is_uniform_where_the_sourced_schedule_is_not():
    """R1's primary prices with BDW's stated model, so it must be exactly that:
    one taker rate everywhere, all window, makers free. If it ever drifted
    toward the sourced schedule, R1 would stop reproducing their construction
    and the divergence log would blame their data for our fee model."""
    from kalshi_mt.fees.schedule import bdw_fee_model

    bdw = bdw_fee_model()
    for ticker in ("INXD-24JAN02-B4800", "NASDAQ100W-23JAN06", "KXNBA-25JAN03-LAL"):
        assert rate_for(bdw, "taker", "2024-01-01", market_ticker=ticker) == 0.07
    assert rate_for(bdw, "taker", "2021-07-15") == 0.07  # no 0.14 era in their model
    for as_of in ("2021-07-15", "2024-01-01", "2026-06-01"):
        assert rate_for(bdw, "maker", as_of, series_ticker="KXNBA") == 0.0


def test_bdw_model_covers_the_whole_r1_window_without_a_gap():
    """The sourced schedule starts at our data floor; BDW's model must start
    earlier still, because a FeeScheduleGapError silently drops rows from the
    net-return column while leaving the gross column intact -- a same-table
    sample mismatch that is easy to miss and hard to spot afterwards."""
    from kalshi_mt.fees.schedule import bdw_fee_model

    bdw = bdw_fee_model()
    for as_of in ("2021-07-01", "2021-09-30", "2022-06-01", "2025-04-30"):
        assert fee_usd_for(bdw, "taker", 100.0, 0.5, as_of) == pytest.approx(1.75)


def test_shipped_schedule_has_no_maker_fee_anywhere_in_r1s_window():
    """R1 reproduces BDW, whose window ends 2025-04-30. The first maker fee is
    stamped 2025-05-13, so maker returns in R1 are gross by construction --
    this test is what keeps that claim honest if the schedule is regenerated."""
    data = load_fee_schedule()
    for series in ("KXNBA", "KXCPI", "KXPRESPARTY", "INXD"):
        assert fee_usd_for(data, "maker", 100.0, 0.5, "2025-04-30", series_ticker=series) == 0.0
