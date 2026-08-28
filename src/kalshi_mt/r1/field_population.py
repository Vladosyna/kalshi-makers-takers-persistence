"""Full-tape taker-field population by era, over Pass 2's real trade tape.

Step Zero's Check 3 (stepzero/checks.py) samples ONE representative market
per era via a live API probe to answer "is taker_outcome_side/
taker_book_side populated" -- a fast, cheap, necessarily-thin diagnostic
that must run before any fetch. Three of its four eras (2023, 2024,
2025-jan-apr) returned zero trades for their sampled candidate in practice,
so its reported PASS verdict rests on population rates measured from a
single 2021 weather market's 152 trades, not one sample per era as the
verdict's own wording implies.

This module recomputes the identical three population rates over EVERY
trade Pass 2 has actually fetched into the Parquet tape (store/parquet.py),
bucketed by the same era boundaries -- at zero extra API cost, since the
tape already exists once Pass 2 has run. It turns Check 3's single-market
probe into full-sample evidence for the same era labels, so the two can be
compared directly rather than the probe standing in for eras it never
actually sampled.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from typing import Any

import polars as pl

from kalshi_mt.util import iso_to_epoch

POPULATION_COLUMNS = ("taker_outcome_side", "taker_book_side", "taker_side")
# The columns this module actually reads. Passed to TradeStore.iter_fills so a
# streamed pass carries four columns per row instead of eleven.
REQUIRED_COLUMNS = ("created_time", *POPULATION_COLUMNS)

# Same boundaries as stepzero/checks.py's check_taker_field_population,
# plus a fifth R2-window bucket -- Pass 2 also fetches R2-era trades, and
# there is no reason to leave them out of a full-sample report just because
# Check 3 (a pre-fetch diagnostic) never had R2 data to sample from.
ERA_BOUNDARIES: list[tuple[str, int, int]] = [
    ("2021-2022", int(datetime(2021, 1, 1, tzinfo=UTC).timestamp()),
     int(datetime(2023, 1, 1, tzinfo=UTC).timestamp())),
    ("2023", int(datetime(2023, 1, 1, tzinfo=UTC).timestamp()),
     int(datetime(2024, 1, 1, tzinfo=UTC).timestamp())),
    ("2024", int(datetime(2024, 1, 1, tzinfo=UTC).timestamp()),
     int(datetime(2025, 1, 1, tzinfo=UTC).timestamp())),
    ("2025-jan-apr", int(datetime(2025, 1, 1, tzinfo=UTC).timestamp()),
     int(datetime(2025, 5, 1, tzinfo=UTC).timestamp())),
    ("2025-may-onward", int(datetime(2025, 5, 1, tzinfo=UTC).timestamp()),
     int(datetime(2027, 1, 1, tzinfo=UTC).timestamp())),
]


def _era_label(created_time: str | None) -> str | None:
    epoch = iso_to_epoch(created_time)
    if epoch is None:
        return None
    for label, start, end in ERA_BOUNDARIES:
        if start <= epoch < end:
            return label
    return None


UNASSIGNED_KEY = "_unassigned"


def _chunks(trades: pl.DataFrame | Iterable[pl.DataFrame]) -> Iterator[pl.DataFrame]:
    """One frame or a stream of them, so the caller chooses whether the tape
    is materialised. See field_population_by_era's docstring for why."""
    if isinstance(trades, pl.DataFrame):
        yield trades
    else:
        yield from trades


def field_population_by_era(
    trades: pl.DataFrame | Iterable[pl.DataFrame],
) -> dict[str, dict[str, Any]]:
    """`trades` is Pass 2's raw tape -- every column it needs (created_time,
    taker_outcome_side, taker_book_side, taker_side) is already part of
    fetch/pass2.py's own row shape, so this is a pure aggregation with no
    new fetch required. Eras with zero trades in the tape still appear in
    the result (trade_count=0) rather than being omitted, so a reader can
    see which eras Pass 2 simply hasn't reached yet.

    Accepts EITHER one DataFrame or an iterable of them, and accumulates
    counts rather than filtering a whole frame per era. Small callers and the
    tests pass a frame; `kmt r1` passes TradeStore.iter_fills(...), because
    the tape it would otherwise materialise is several GB compressed and
    read_all() on it is the same failure that killed Pass 2 on 2026-08-24
    (`memory allocation of 635487952 bytes failed`). Counting per chunk makes
    peak memory a property of the batch size, not of how much has been
    collected -- and the result is identical either way, which
    test_field_population.py pins directly.

    Also always reports a reserved `_unassigned` bucket -- trades whose
    created_time is unparseable, or whose epoch falls outside every span in
    ERA_BOUNDARIES (today: before 2021-01-01 or at/after 2027-01-01) -- so a
    reader can tell "this era genuinely has zero trades" apart from "some
    trades exist but couldn't be placed," rather than both looking like the
    same silent zero."""
    keys = [label for label, _, _ in ERA_BOUNDARIES] + [UNASSIGNED_KEY]
    totals: dict[str, dict[str, int]] = {
        k: {"trade_count": 0, **dict.fromkeys(POPULATION_COLUMNS, 0)} for k in keys
    }

    for chunk in _chunks(trades):
        if chunk.is_empty():
            continue
        df = chunk.with_columns(
            pl.col("created_time").map_elements(_era_label, return_dtype=pl.String).alias("era")
        )
        for key in keys:
            bucket = (
                df.filter(pl.col("era").is_null())
                if key == UNASSIGNED_KEY
                else df.filter(pl.col("era") == key)
            )
            if bucket.is_empty():
                continue
            totals[key]["trade_count"] += len(bucket)
            for col in POPULATION_COLUMNS:
                totals[key][col] += int(bucket[col].is_not_null().sum())

    results: dict[str, dict[str, Any]] = {}
    for key in keys:
        n = totals[key]["trade_count"]
        if n == 0:
            results[key] = {"trade_count": 0}
            continue
        results[key] = {
            "trade_count": n,
            "taker_outcome_side_population": round(totals[key]["taker_outcome_side"] / n, 4),
            "taker_book_side_population": round(totals[key]["taker_book_side"] / n, 4),
            "taker_side_legacy_population": round(totals[key]["taker_side"] / n, 4),
        }
    return results
