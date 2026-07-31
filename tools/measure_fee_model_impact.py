"""How much does BDW's uniform 0.07 differ from Kalshi's published schedule?

R1 prices its primary net-return figures with BDW's own stated fee model so
that a gap against their Fig 5 is theirs to explain rather than ours (see
fees/schedule.py's bdw_fee_model). This script measures what that choice
costs: the same R1 panel, priced both ways, band by band.

Two documented differences drive it, both read off the archived schedules in
docs/sources/fees/:
  * S&P500 (INX*) and Nasdaq-100 (NASDAQ100*) markets pay HALF the general
    taker rate -- 18.3% of R1's in-scope universe;
  * the general rate was 0.14, not 0.07, until 2021-08-01.

Usage:
    python tools/measure_fee_model_impact.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kalshi_mt.fees.schedule import bdw_fee_model, load_fee_schedule  # noqa: E402
from kalshi_mt.r1.panel import build_yes_only_panel_backfilled  # noqa: E402
from kalshi_mt.r1.reproduction import returns_by_band  # noqa: E402
from kalshi_mt.store.db import connect_read_only  # noqa: E402
from kalshi_mt.store.parquet import TradeStore  # noqa: E402
from kalshi_mt.util import load_config  # noqa: E402

BAND_ORDER = [
    "1-10c", "11-20c", "21-30c", "31-40c", "41-50c",
    "51-60c", "61-70c", "71-80c", "81-90c", "90-99c",
]


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
        print(f"R1 in-scope markets: {len(in_scope):,}")
        trade_store = TradeStore(config["storage"]["parquet_dir"])
        panel = build_yes_only_panel_backfilled(conn, trade_store, in_scope)
    finally:
        conn.close()
    print(f"panel rows: {len(panel):,}")

    bdw = returns_by_band(panel, bdw_fee_model())
    sourced = returns_by_band(panel, load_fee_schedule())

    print()
    print(f"{'band':<10} {'n':>9} {'gross':>10} {'net (BDW)':>11} {'net (sourced)':>14} {'diff bp':>9}")
    print("-" * 68)
    bands = [b for b in BAND_ORDER if b in bdw] + [b for b in sorted(bdw) if b not in BAND_ORDER]
    for band in bands:
        a, b = bdw[band], sourced.get(band, {})
        net_a, net_b = a.get("mean_net_return"), b.get("mean_net_return")
        diff = "" if net_a is None or net_b is None else f"{(net_b - net_a) * 10000:9.2f}"
        print(
            f"{band:<10} {a['n']:>9,} {a['mean_gross_return'] or float('nan'):>10.4f} "
            f"{net_a if net_a is not None else float('nan'):>11.4f} "
            f"{net_b if net_b is not None else float('nan'):>14.4f} {diff:>9}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
