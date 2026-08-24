"""Maker/taker return gap and the maker >=50c margin (docs/analysis_plan.md
S2.5, S3.2), in the three fee layers, and the escalation-relevant number
S5's third trigger condition needs (S5: "the maker >=50c margin changes
sign between layers (a) and (c) AND survives the entire fee-sensitivity
ribbon").

WHY "margin" means the maker-vs-taker SPREAD, not the maker's own return:
this repo's fee history (data/fees.yaml) has the general taker rate constant
at 0.07 from 2021-08 onward, and NO maker fee anywhere before 2025-05-13.
Layer (a) is gross/zero-fee for any trade; layer (c) is the pre-maker-fee
schedule held constant and applied to later trades (fees/returns.py's
COUNTERFACTUAL_AS_OF). For a MAKER's own trade, layer (c) looks up the maker
rate as of 2025-05-12 -- 0.0 -- which is IDENTICAL to layer (a)'s zero fee.
So a maker's own average return can
never differ between layers (a) and (c): "the maker's own return" cannot
change sign between them, which would make S5's trigger vacuous. The only
reading under which the trigger is meaningful is margin = mean(maker
return) - mean(taker return), restricted to the >=50c side-price band
(mirroring r1/reproduction.py's maker_taker_split, but layer-aware and
threshold-restricted instead of gross-only/10c-banded). Under layer (c)
the taker side now pays a nonzero fee while the maker side still pays
zero, which mechanically pushes margin_c more maker-favorable than
margin_a -- and CAN cross zero if the underlying gross gap was already
small or negative for makers at the >=50c band.

Per-trade role/payout logic (which side is maker vs taker, what the
payout is) mirrors r1/reproduction.py's maker_taker_split exactly; the
>=50c band check here is a simple `side_price >= 0.5` per side, not the
10c-bucketing price_band() helper used elsewhere.

The maker fee is scoped to an enumerated list of SERIES, so this module is
handed a {ticker: series_ticker} map rather than the {ticker: category} map
it used to take -- category never determined a Kalshi fee. A ticker absent
from the map still gets a correct answer (zero maker fee, general taker
rate); it simply cannot match a series-scoped entry.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

import polars as pl

from kalshi_mt.fees.returns import counterfactual_return, gross_return, net_return


@dataclass
class MakerMarginResult:
    """margin_X = mean(maker_return_X) - mean(taker_return_X) for the
    >=50c side-price band, layer X in {a: gross, b: net-of-own-era-fees,
    c: pre-2025-05-schedule-held-constant counterfactual}. None if either
    side had zero valid observations for that layer (an empty mean is
    undefined, not zero).

    n_maker_a / n_taker_a are always the full >=50c-band observation
    counts (layer a is defined for every in-band side). n_maker_b /
    n_taker_b and n_maker_c / n_taker_c are the counts actually
    contributing to that layer's mean, i.e. excluding fee-schedule-gap
    observations for that layer specifically -- gap_excluded_b /
    gap_excluded_c report how many in-band observations were dropped for
    that reason (per side, summed across maker+taker).
    """

    layer_a: float | None
    layer_b: float | None
    layer_c: float | None
    n_maker_a: int
    n_taker_a: int
    n_maker_b: int
    n_taker_b: int
    n_maker_c: int
    n_taker_c: int
    gap_excluded_b: int
    gap_excluded_c: int



class _Mean:
    """Running mean with Neumaier compensation.

    The accumulators here used to be Python lists handed to np.mean. That is
    accurate -- NumPy sums pairwise -- but it holds one float per in-band
    side, and the whole point of streaming the tape is not to hold O(fills)
    of anything. Naive running addition over tens of millions of values
    drifts; compensated addition does not, and costs one extra float."""

    __slots__ = ("_total", "_comp", "n")

    def __init__(self) -> None:
        self._total = 0.0
        self._comp = 0.0
        self.n = 0

    def add(self, x: float) -> None:
        total = self._total + x
        if abs(self._total) >= abs(x):
            self._comp += (self._total - total) + x
        else:
            self._comp += (x - total) + self._total
        self._total = total
        self.n += 1

    @property
    def mean(self) -> float | None:
        return None if self.n == 0 else (self._total + self._comp) / self.n


def _margin(maker: _Mean, taker: _Mean) -> float | None:
    if maker.mean is None or taker.mean is None:
        return None
    return maker.mean - taker.mean


def _chunks(trades: pl.DataFrame | Iterable[pl.DataFrame]) -> Iterator[pl.DataFrame]:
    """One frame or a stream of them, so the caller decides whether the tape
    gets materialised. See compute_maker_margin_ge_50c."""
    if isinstance(trades, pl.DataFrame):
        yield trades
    else:
        yield from trades


# What this module actually reads off each fill. Handed to
# TradeStore.iter_fills so a streamed pass carries five columns, not eleven.
REQUIRED_COLUMNS = (
    "ticker",
    "count_fp",
    "yes_price_dollars",
    "taker_outcome_side",
    "created_time",
)

_EMPTY_RESULT = MakerMarginResult(
    layer_a=None, layer_b=None, layer_c=None,
    n_maker_a=0, n_taker_a=0, n_maker_b=0, n_taker_b=0, n_maker_c=0, n_taker_c=0,
    gap_excluded_b=0, gap_excluded_c=0,
)


def compute_maker_margin_ge_50c(
    trades: pl.DataFrame | Iterable[pl.DataFrame],
    resolutions: dict[str, str],
    series_by_ticker: dict[str, str | None],
    fee_schedule: dict[str, Any],
    in_scope_tickers: set[str],
) -> MakerMarginResult:
    """Main entry point. Iterates every trade in `trades` restricted to
    `in_scope_tickers`; for each of its two sides (yes-side and the
    complementary no-side, same doubled-basis shape as
    r1/reproduction.py's maker_taker_split), includes that side only if
    its own price is >= 0.50, determines maker/taker role from
    taker_outcome_side, and accumulates gross/net/counterfactual returns
    per role. `resolutions` is {ticker: 'yes'|'no'}, `series_by_ticker` is
    {ticker: series_ticker-or-None} (looked up by the caller, e.g. from the
    markets table), `fee_schedule` is fees/schedule.py's loaded dict.

    Accepts EITHER one DataFrame or an iterable of them, and keeps running
    means rather than lists of every return. Both changes are the same fix:
    the tape this runs over is several GB compressed, TradeStore.read_all()
    on it is what killed Pass 2 on 2026-08-24 with `memory allocation of
    635487952 bytes failed`, and six lists holding one float per in-band side
    would not have fitted either even if the frame had. Callers with a real
    tape should pass
    TradeStore.iter_fills(tickers=in_scope_tickers, columns=REQUIRED_COLUMNS);
    tests pass a frame, and test_maker_margin.py pins that the two agree to
    the bit."""
    if not in_scope_tickers:
        return _EMPTY_RESULT

    # A plain list, not a Series: polars deprecated is_in against a
    # same-dtype collection as ambiguous (pola-rs/polars#22149).
    scope = sorted(in_scope_tickers)
    maker_a, taker_a = _Mean(), _Mean()
    maker_b, taker_b = _Mean(), _Mean()
    maker_c, taker_c = _Mean(), _Mean()
    gap_excluded_b = 0
    gap_excluded_c = 0

    for chunk in _chunks(trades):
        if chunk.is_empty():
            continue
        chunk = chunk.filter(pl.col("ticker").is_in(scope))
        if chunk.is_empty():
            continue

        for row in chunk.iter_rows(named=True):
            ticker = row["ticker"]
            result = resolutions.get(ticker)
            taker_side = row["taker_outcome_side"]
            yes_price = row["yes_price_dollars"]
            count_fp = row["count_fp"]
            created_time = row["created_time"]
            if result not in ("yes", "no") or taker_side not in ("yes", "no") or yes_price is None:
                continue
            if not (0.0 < yes_price < 1.0):
                continue
            if count_fp is None or count_fp <= 0:
                continue
            if created_time is None:
                continue
            series_ticker = series_by_ticker.get(ticker)

            payout_yes = 1.0 if result == "yes" else 0.0
            yes_role = "taker" if taker_side == "yes" else "maker"
            no_role = "taker" if taker_side == "no" else "maker"

            for side_price, side_role, side_payout in (
                (yes_price, yes_role, payout_yes),
                (1.0 - yes_price, no_role, 1.0 - payout_yes),
            ):
                if side_price < 0.5:
                    continue

                gross = gross_return(side_payout, side_price)
                net = net_return(
                    fee_schedule, side_role, count_fp, side_payout, side_price, created_time,
                    market_ticker=ticker, series_ticker=series_ticker,
                )
                cf = counterfactual_return(
                    fee_schedule, side_role, count_fp, side_payout, side_price,
                    market_ticker=ticker, series_ticker=series_ticker,
                )

                a, b, c = (
                    (maker_a, maker_b, maker_c) if side_role == "maker"
                    else (taker_a, taker_b, taker_c)
                )
                a.add(gross)
                if net is not None:
                    b.add(net)
                else:
                    gap_excluded_b += 1
                if cf is not None:
                    c.add(cf)
                else:
                    gap_excluded_c += 1

    return MakerMarginResult(
        layer_a=_margin(maker_a, taker_a),
        layer_b=_margin(maker_b, taker_b),
        layer_c=_margin(maker_c, taker_c),
        n_maker_a=maker_a.n,
        n_taker_a=taker_a.n,
        n_maker_b=maker_b.n,
        n_taker_b=taker_b.n,
        n_maker_c=maker_c.n,
        n_taker_c=taker_c.n,
        gap_excluded_b=gap_excluded_b,
        gap_excluded_c=gap_excluded_c,
    )
