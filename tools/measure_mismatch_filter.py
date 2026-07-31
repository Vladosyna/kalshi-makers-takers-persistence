"""Which reading of BDW's "63 contracts dropped for mismatch" is the right one?

BDW drop "63 Yes contracts for mismatch vs Kalshi's separately-reported final
prices" -- 63 of 46,282, or 0.14%. The spec left the field behind
"separately-reported" as an explicit implementation pin ("settlement price vs
last price"), and the filter has been running on a PROXY in the meantime:
Kalshi's categorical `result` against the side implied by the closing-day last
trade (>=50c implies yes). This script measures that proxy against the two
price-vs-price readings the pin actually offers, now that both fields are
persisted for the whole universe.

The proxy is not merely approximate -- it asks a different question. "The last
trade was below 50c and the contract settled yes" is an UPSET, not a data
error, and upsets are the raw material of a favorite-longshot-bias paper.
A filter that drops them would remove exactly the observations that create the
effect under study. The measurement below is what settles whether that is
happening.

Usage:
    python tools/measure_mismatch_filter.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kalshi_mt.store.db import connect_read_only  # noqa: E402
from kalshi_mt.store.parquet import TradeStore  # noqa: E402
from kalshi_mt.util import load_config  # noqa: E402

# Half a cent: both sides are cent-granular, so anything above this is a real
# disagreement rather than float representation noise.
TOLERANCE = 0.005
BDW_DROPPED = 63
BDW_CONTRACTS = 46282


def main() -> int:
    config = load_config()
    conn = connect_read_only()
    try:
        rows = conn.execute(
            """
            SELECT m.ticker, m.result, m.last_price_dollars, m.settlement_value_dollars,
                   m.close_time_epoch,
                   p.yes_price_dollars AS day0_price
            FROM markets m
            LEFT JOIN price_panel p ON p.ticker = m.ticker AND p.lookback_day = 0
            WHERE m.in_r1_window = 1
              AND m.ticker NOT IN (SELECT ticker FROM universe_log WHERE window = 'r1')
            """
        ).fetchall()
        rows = [dict(r) for r in rows]
        # The PRIMARY construction reads day 0 off Pass 2's full tape, not off
        # Pass 1's stored price_panel -- the stored panel carries a same-ET-day
        # guard the backfill amendment removed, so it can hold a staler price.
        # Comparing the wrong panel to Kalshi's own final price would measure
        # our own construction gap and call it a mismatch.
        store = TradeStore(config["storage"]["parquet_dir"])
        refs = [
            (r["ticker"], 0, r["close_time_epoch"])
            for r in rows if r["close_time_epoch"] is not None
        ]
        tape = store.last_trade_at_or_before(refs) if refs else {}
        for r in rows:
            hit = tape.get((r["ticker"], 0))
            r["tape_price"] = hit[0] if hit else None
    finally:
        conn.close()

    n = len(rows)
    print(f"R1 in-scope markets with a day-0 panel price: {n:,}")
    print(f"BDW's own drop rate: {BDW_DROPPED}/{BDW_CONTRACTS:,} = {100.0*BDW_DROPPED/BDW_CONTRACTS:.3f}%")
    print()

    counters: dict[str, list[int]] = {}
    diffs: list[float] = []

    def count(label: str, hit: bool | None) -> None:
        acc = counters.setdefault(label, [0, 0])
        if hit is None:
            return
        acc[1] += 1
        if hit:
            acc[0] += 1

    for r in rows:
        stored = r["day0_price"]
        tape_price = r["tape_price"]
        last = r["last_price_dollars"]
        settle = r["settlement_value_dollars"]

        count(
            "proxy: result vs side implied by last trade",
            None if stored is None or r["result"] not in ("yes", "no")
            else r["result"] != ("yes" if stored >= 0.5 else "no"),
        )
        count(
            "STORED panel price vs Kalshi last_price",
            None if stored is None or last is None else abs(float(last) - float(stored)) > TOLERANCE,
        )
        count(
            "TAPE day-0 price vs Kalshi last_price",
            None if tape_price is None or last is None
            else abs(float(last) - float(tape_price)) > TOLERANCE,
        )
        count(
            "TAPE day-0 price vs settlement value",
            None if tape_price is None or settle is None
            else abs(float(settle) - float(tape_price)) > TOLERANCE,
        )
        if tape_price is not None and last is not None:
            diffs.append(abs(float(last) - float(tape_price)))

    print("drop counts by reading:")
    for label, (dropped, have) in counters.items():
        rate = 100.0 * dropped / have if have else 0.0
        ratio = rate / (100.0 * BDW_DROPPED / BDW_CONTRACTS)
        print(f"  {label:<44} {dropped:>7,} / {have:>7,} = {rate:6.3f}%   {ratio:>7.1f}x BDW")

    if diffs:
        diffs.sort()
        print()
        print("|tape day-0 price - Kalshi last_price|, distribution over "
              f"{len(diffs):,} markets that have both:")
        for pct in (50, 90, 95, 99, 99.5, 99.9):
            idx = min(len(diffs) - 1, int(len(diffs) * pct / 100))
            print(f"  p{pct:<5} {diffs[idx]:.4f}")
        print(f"  max    {diffs[-1]:.4f}")
        for thresh in (0.005, 0.01, 0.02, 0.05, 0.10, 0.25, 0.50):
            over = sum(1 for d in diffs if d > thresh)
            print(f"  > {thresh:<5} : {over:>6,} ({100.0*over/len(diffs):5.2f}%)"
                  f"   {(100.0*over/len(diffs)) / (100.0*BDW_DROPPED/BDW_CONTRACTS):>6.1f}x BDW")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
