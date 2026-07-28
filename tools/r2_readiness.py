"""Which R2 months are ANALYSABLE, not merely quoted.

The distinction is the point. A market contributes to a delta only if it is
quoted (so the spread filter can be evaluated), passes that filter, AND has
Pass 2's trade tape (so the panel has prices). On 2026-07-28 the boundary
months were 28.7% quoted and 0% analysable -- every collected, analysable
market sat after both boundaries, so neither delta existed. Reporting quote
percentage as progress hid that completely.

Run this before believing any statement about R2 being ready.

Usage:
    python tools/r2_readiness.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kalshi_mt.store import db  # noqa: E402
from kalshi_mt.util import load_config  # noqa: E402

SCOPE = "volume_fp >= 1000 AND (close_time_epoch - open_time_epoch) >= 86400"
# The two boundaries a delta is measured at (analysis_plan.md S2.1, Addendum 3).
BOUNDARIES = {"2025-05": "fee (2025-05-13)", "2025-09": "publication (2025-09-08)"}


def main() -> int:
    config = load_config()
    conn = db.connect(config["storage"]["db_path"])
    try:
        rows = conn.execute(
            f"""
            SELECT strftime('%Y-%m', m.close_time_epoch, 'unixepoch') AS month,
                   COUNT(*) AS eligible,
                   SUM(CASE WHEN q.ticker IS NOT NULL THEN 1 ELSE 0 END) AS quoted,
                   SUM(CASE WHEN q.spread IS NOT NULL AND q.spread <= 0.20 THEN 1 ELSE 0 END) AS in_scope,
                   SUM(CASE WHEN q.spread IS NOT NULL AND q.spread <= 0.20
                             AND p.status = 'done' THEN 1 ELSE 0 END) AS analysable
            FROM markets m
            LEFT JOIN quotes q ON q.ticker = m.ticker
            LEFT JOIN pass2_progress p ON p.ticker = m.ticker
            WHERE {SCOPE} AND m.in_r2_window = 1
            GROUP BY month ORDER BY month
            """
        ).fetchall()
    finally:
        conn.close()

    print(f"{'month':<9} {'eligible':>9} {'quoted':>9} {'in scope':>9} {'ANALYSABLE':>11}  boundary")
    print("-" * 68)
    totals = [0, 0, 0, 0]
    for r in rows:
        marker = f"  <-- {BOUNDARIES[r['month']]}" if r["month"] in BOUNDARIES else ""
        print(
            f"{r['month']:<9} {r['eligible']:>9,} {r['quoted']:>9,} "
            f"{r['in_scope']:>9,} {r['analysable']:>11,}{marker}"
        )
        totals[0] += r["eligible"]; totals[1] += r["quoted"]
        totals[2] += r["in_scope"]; totals[3] += r["analysable"]
    print("-" * 68)
    print(f"{'TOTAL':<9} {totals[0]:>9,} {totals[1]:>9,} {totals[2]:>9,} {totals[3]:>11,}")

    print()
    need_tape = totals[2] - totals[3]
    print(f"markets in scope but with no tape (Pass 2 backlog): {need_tape:,}")
    months_ready = sum(1 for r in rows if r["analysable"] > 0)
    print(f"months with any analysable market: {months_ready} of {len(rows)}")
    for month, label in BOUNDARIES.items():
        row = next((r for r in rows if r["month"] == month), None)
        state = "READY" if row and row["analysable"] > 0 else "NOT READY"
        print(f"  {label:<26} {state}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
