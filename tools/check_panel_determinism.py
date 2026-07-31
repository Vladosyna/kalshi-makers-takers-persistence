"""Does the R1 panel come back identical on a re-run over an unchanged tape?

Kalshi records every fill of a sweeping order at the same timestamp, and those
fills can sit at different price levels, so "the last trade at or before T" is
ambiguous unless the tie is broken explicitly. Before it was
(store/parquet.py's ASOF subquery now pins it to the smallest trade_id), two
runs over the same tape returned the same 121,803 panel rows with ~60 of them
in different price bands -- every R1 figure was one draw from that.

This script builds the panel twice in one process and compares. Determinism is
a spec S4 test requirement; the unit tests cover the rule on fixtures, this
covers it at real scale, where the ties actually occur.

Usage:
    python tools/check_panel_determinism.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import polars as pl  # noqa: E402

from kalshi_mt.r1.panel import build_yes_only_panel_backfilled, price_band  # noqa: E402
from kalshi_mt.store.db import connect_read_only  # noqa: E402
from kalshi_mt.store.parquet import TradeStore  # noqa: E402
from kalshi_mt.util import load_config  # noqa: E402


def _band_counts(panel: pl.DataFrame) -> dict[str, int]:
    bands = [price_band(p) for p in panel["p"].to_list()]
    out: dict[str, int] = {}
    for b in bands:
        out[b] = out.get(b, 0) + 1
    return out


def main() -> int:
    config = load_config()
    conn = connect_read_only()
    try:
        in_scope = {
            r[0] for r in conn.execute(
                "SELECT ticker FROM markets m WHERE m.in_r1_window = 1 "
                "AND m.ticker NOT IN (SELECT ticker FROM universe_log WHERE window = 'r1')"
            ).fetchall()
        }
        store = TradeStore(config["storage"]["parquet_dir"])
        first = build_yes_only_panel_backfilled(conn, store, in_scope)
        second = build_yes_only_panel_backfilled(conn, store, in_scope)
    finally:
        conn.close()

    print(f"run 1: {len(first):,} rows    run 2: {len(second):,} rows")
    key = ["ticker", "lookback_day"]
    a = first.sort(key).select([*key, "p", "count_fp", "taker_outcome_side"])
    b = second.sort(key).select([*key, "p", "count_fp", "taker_outcome_side"])

    if a.equals(b):
        print("IDENTICAL: same rows, same prices, same order sizes, same taker sides")
        return 0

    print("DIFFERENT -- panel construction is not deterministic")
    joined = a.join(b, on=key, how="inner", suffix="_2")
    drift = joined.filter(pl.col("p") != pl.col("p_2"))
    print(f"  rows present in both but priced differently: {len(drift):,}")
    bands_a, bands_b = _band_counts(first), _band_counts(second)
    for band in sorted(set(bands_a) | set(bands_b)):
        if bands_a.get(band, 0) != bands_b.get(band, 0):
            print(f"    {band:<10} {bands_a.get(band, 0):>8,} vs {bands_b.get(band, 0):>8,}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
