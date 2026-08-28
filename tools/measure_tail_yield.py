"""What the 2026-05/06 quote tail yields, and whether the 2026-08-08 forecast held.

The spread filter can only be evaluated AFTER a market is quoted, so the tail
fetch is unavoidably speculative: some fraction of what it pulls is discarded.
This measures that fraction as it accumulates, against a forecast recorded
before the evidence existed.

WHAT WAS FORECAST, 2026-08-08, and which parts are actually testable
--------------------------------------------------------------------
Two of the three numbers behind the "collect 2026-05, stop before 2026-06"
recommendation are NOT predictions and cannot be refuted by more collection:

  * 2026-05 treated share  2.2%  (2,765 of 125,571)
  * 2026-06 treated share  0.2%  (810 of 405,252)

Both are computed over EVERY eligible market in the month, quoted or not --
treatment is a property of the market's series, which is known without
fetching anything. They are population values already.

The 2026-05 figure was first reported as 1.8% of 133,330, and that was an
arithmetic error rather than a revised estimate: the month boundary was taken
as epoch 1777939200, which is 2026-05-05, not 2026-05-01. The same wrong
constant produced three different "2026-05 eligible" counts in one session
(133,330, 125,571, 115,891) before it was caught by their disagreement. The
collection itself was never affected -- fetch commands take date strings, which
parse correctly -- only the measurement did. Correct boundaries: 2026-05-01 is
1777593600 and 2026-07-01 is 1782864000.

The genuinely predicted quantity is the spread-filter pass rate among the
markets still unquoted at that date, extrapolated from those already quoted:

  * 2026-05  69.5%  ->  ~55,400 of 79,737 remaining would enter the panel
  * 2026-06  51.3%  -> ~173,200 of 337,585 remaining would enter the panel

That extrapolation assumes the already-quoted subset is representative. It may
not be: the panel/quote phase walks markets in ticker order, which is arbitrary
with respect to spread but not guaranteed to be unrelated to it. If the pass
rate among NEWLY quoted markets diverges materially from these, the yield
estimate was wrong and the recommendation built on it should be revisited.

Usage:
    python tools/measure_tail_yield.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kalshi_mt.fees.schedule import FeeScheduleGapError, entry_for, load_fee_schedule  # noqa: E402
from kalshi_mt.store.db import connect_read_only  # noqa: E402

SCOPE = "volume_fp >= 1000 AND (close_time_epoch - open_time_epoch) >= 86400"
TAIL_START = 1777593600  # 2026-05-01 00:00 UTC

# Recorded 2026-08-08, before the tail fetch had added anything. The comparison
# below is against these, not against a remembered impression.
FORECAST_PASS_RATE = {"2026-05": 0.695, "2026-06": 0.513}
# Population values, corrected for the date-boundary error described above --
# not forecasts, so restating them is fixing arithmetic, not moving a target.
FORECAST_TREATED_SHARE = {"2026-05": 0.022, "2026-06": 0.002}


def main() -> int:
    conn = connect_read_only()
    try:
        print("=== spread-filter pass rate, quoted markets in the tail months ===")
        print(f"  {'month':<9} {'quoted':>9} {'passed':>9} {'rate':>8} {'forecast':>9} {'delta':>8}")
        for r in conn.execute(f"""
            SELECT strftime('%Y-%m', m.close_time_epoch, 'unixepoch') AS month,
                   COUNT(*) AS quoted,
                   SUM(CASE WHEN q.spread IS NOT NULL AND q.spread <= 0.20 THEN 1 ELSE 0 END) AS passed
            FROM markets m JOIN quotes q ON q.ticker = m.ticker
            WHERE {SCOPE} AND m.in_r2_window = 1 AND m.close_time_epoch >= {TAIL_START}
            GROUP BY month ORDER BY month
        """):
            rate = r["passed"] / max(r["quoted"], 1)
            fc = FORECAST_PASS_RATE.get(r["month"])
            fc_txt = f"{100*fc:.1f}%" if fc else "   --"
            delta = f"{100*(rate-fc):+.1f}pp" if fc else "     --"
            print(f"  {r['month']:<9} {r['quoted']:>9,} {r['passed']:>9,} {100*rate:>7.1f}% {fc_txt:>9} {delta:>8}")

        print()
        print("=== remaining work and projected yield at the CURRENT observed rate ===")
        for r in conn.execute(f"""
            SELECT strftime('%Y-%m', close_time_epoch, 'unixepoch') AS month,
                   COUNT(*) AS eligible,
                   SUM(CASE WHEN EXISTS (SELECT 1 FROM quotes q WHERE q.ticker = markets.ticker)
                            THEN 0 ELSE 1 END) AS unquoted
            FROM markets
            WHERE {SCOPE} AND in_r2_window = 1 AND close_time_epoch >= {TAIL_START}
            GROUP BY month ORDER BY month
        """):
            print(f"  {r['month']:<9} eligible {r['eligible']:>8,}  still unquoted {r['unquoted']:>8,}")

        print()
        print("=== treated share -- POPULATION values, not projections ===")
        print("  (treatment is a property of the series, known without fetching)")
        schedule = load_fee_schedule()
        cache: dict[tuple, bool] = {}

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

        rows = conn.execute(f"""
            SELECT series_ticker, close_time_epoch FROM markets
            WHERE {SCOPE} AND in_r2_window = 1 AND close_time_epoch >= {TAIL_START}
        """).fetchall()
        by_month: dict[str, list[int]] = {}
        for series, epoch in rows:
            dt = datetime.fromtimestamp(epoch, tz=UTC)
            acc = by_month.setdefault(dt.strftime("%Y-%m"), [0, 0])
            acc[0] += 1
            if charged(series, dt.strftime("%Y-%m-%d")):
                acc[1] += 1
        for month in sorted(by_month):
            total, treated = by_month[month]
            share = treated / max(total, 1)
            fc = FORECAST_TREATED_SHARE.get(month)
            fc_txt = f" (recorded {100*fc:.1f}%)" if fc else ""
            print(f"  {month}  {total:>8,} eligible, {treated:>6,} treated = {100*share:.1f}%{fc_txt}")
        print()
        print("  delta_fee is identified treated-vs-control WITHIN a month, so a month")
        print("  at 0.2% treated contributes almost nothing to it however many markets")
        print("  it adds.")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
