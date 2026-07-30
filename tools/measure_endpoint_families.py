"""Which endpoint family answers, and can a market answer differently later?

Both questions matter for the panel's completeness, and both are answerable
from what is already stored rather than by re-probing the API.

`_last_trade_before` picks a family once per market (from the closing-day
trade) and falls back to the other on a miss. That is cheap because the family
is near-deterministic in market age -- the live /markets/trades endpoint serves
only about the last 60 days. But "near" is doing work in that sentence: a
market whose 10-day lookback window brackets the retention boundary needs BOTH
families, and this script measures how many do. Any future optimization that
caches one family per market has to keep the fallback or lose those rows.

It also checks whether markets that failed outright have since succeeded, which
distinguishes a transient failure (retried, recovered) from a permanent absence
on Kalshi's side (retried forever, never recovers).

Usage:
    python tools/measure_endpoint_families.py
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kalshi_mt.store import db  # noqa: E402
from kalshi_mt.util import load_config  # noqa: E402


def main() -> int:
    config = load_config()
    conn = db.connect(config["storage"]["db_path"])
    try:
        mixed = conn.execute(
            """
            SELECT COUNT(*) AS n FROM (
                SELECT ticker FROM price_panel WHERE source IN ('live', 'historical')
                GROUP BY ticker HAVING COUNT(DISTINCT source) > 1
            )
            """
        ).fetchone()["n"]
        total = conn.execute(
            "SELECT COUNT(DISTINCT ticker) AS n FROM price_panel WHERE source IN ('live','historical')"
        ).fetchone()["n"]
        print("markets needing BOTH endpoint families for one 10-day panel:")
        share = 100.0 * mixed / total if total else 0.0
        print(f"  {mixed:,} of {total:,} ({share:.1f}%)")
        print("  These are the markets whose lookback window brackets the ~60-day")
        print("  live retention boundary. The fallback is what makes them whole.")

        print()
        print("family by market close month (live share shows the retention boundary):")
        by_month: dict[str, Counter] = {}
        for r in conn.execute(
            """
            SELECT strftime('%Y-%m', m.close_time_epoch, 'unixepoch') AS month,
                   p.source, COUNT(*) AS n
            FROM price_panel p JOIN markets m ON m.ticker = p.ticker
            WHERE p.source IN ('live','historical') AND m.close_time_epoch IS NOT NULL
            GROUP BY month, p.source ORDER BY month
            """
        ):
            by_month.setdefault(r["month"], Counter())[r["source"]] = r["n"]
        for month in sorted(by_month):
            c = by_month[month]
            tot = sum(c.values())
            print(
                f"  {month}  live {c.get('live', 0):>8,}  historical {c.get('historical', 0):>8,}"
                f"  live={100.0 * c.get('live', 0) / tot if tot else 0:5.1f}%"
            )

        print()
        print("markets that were reached but produced no quote row at all:")
        print("  (a permanent absence on Kalshi's side keeps being retried forever,")
        print("   because the resume predicate is `ticker NOT IN quotes`)")
        stuck = conn.execute(
            """
            SELECT COUNT(*) AS n FROM markets m
            WHERE m.in_r2_window = 1 AND m.volume_fp >= 1000
              AND (m.close_time_epoch - m.open_time_epoch) >= 86400
              AND EXISTS (SELECT 1 FROM price_panel p WHERE p.ticker = m.ticker)
              AND NOT EXISTS (SELECT 1 FROM quotes q WHERE q.ticker = m.ticker)
            """
        ).fetchone()["n"]
        print(f"  panel rows but no quote row: {stuck:,}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
