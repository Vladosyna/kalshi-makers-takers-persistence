"""How much of R2's universe is actually under the maker fee, month by month?

The DiD in r2/did.py is only as good as its treatment assignment, and that
assignment is a join between two independently produced name spaces: the series
tickers Kalshi prints in its fee schedule, and the `series_ticker` values our
collector stored. A silent mismatch there would not error -- it would return
zero treated rows and a "not identified" result that looks like a data problem
rather than a name problem.

This script measures the join directly, against the markets table rather than
the panel, so it runs in seconds and does not wait on quote collection. It also
produces a number the paper needs on its own: the treated share of markets and
of volume, by month, which is what makes the case that a break at one
exchange-wide date had almost no treatment behind it.

Usage:
    python tools/measure_maker_fee_treatment.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kalshi_mt.fees.schedule import FeeScheduleGapError, entry_for, load_fee_schedule  # noqa: E402
from kalshi_mt.store import db  # noqa: E402
from kalshi_mt.util import load_config  # noqa: E402

SCOPE = "volume_fp >= 1000 AND (close_time_epoch - open_time_epoch) >= 86400"


def main() -> int:
    schedule = load_fee_schedule()
    config = load_config()
    conn = db.connect(config["storage"]["db_path"])
    try:
        rows = conn.execute(
            f"SELECT series_ticker, close_time_epoch, volume_fp FROM markets "
            f"WHERE {SCOPE} AND in_r2_window = 1 AND close_time_epoch IS NOT NULL"
        ).fetchall()
    finally:
        conn.close()

    cache: dict[tuple[str | None, str], bool] = {}

    def charged(series: str | None, as_of: str) -> bool:
        if series is None:
            return False
        key = (series, as_of)
        if key not in cache:
            try:
                entry = entry_for(schedule, "maker", as_of, series_ticker=series)
                cache[key] = entry.get("form") != "none" and float(entry.get("rate", 0.0)) != 0.0
            except FeeScheduleGapError:
                cache[key] = False
        return cache[key]

    by_month: dict[str, list[float]] = {}
    treated_series: set[str] = set()
    for series, epoch, volume in rows:
        dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
        month = dt.strftime("%Y-%m")
        hit = charged(series, dt.strftime("%Y-%m-%d"))
        if hit:
            treated_series.add(series)
        acc = by_month.setdefault(month, [0.0, 0.0, 0.0, 0.0])
        acc[0] += 1
        acc[1] += float(volume or 0.0)
        if hit:
            acc[2] += 1
            acc[3] += float(volume or 0.0)

    print(f"R2 in-scope markets: {len(rows):,}")
    print(f"distinct series matched to a maker-fee entry: {len(treated_series)}")
    if not treated_series:
        print("  WARNING: zero matches -- check that fee-schedule series names")
        print("  line up with markets.series_ticker before trusting any DiD result.")
    print()
    print(f"{'month':<9} {'markets':>9} {'treated':>9} {'share':>7} {'vol share':>10}")
    print("-" * 48)
    for month in sorted(by_month):
        n, vol, tn, tvol = by_month[month]
        print(
            f"{month:<9} {int(n):>9,} {int(tn):>9,} {100.0 * tn / n:>6.1f}% "
            f"{(100.0 * tvol / vol if vol else 0.0):>9.1f}%"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
