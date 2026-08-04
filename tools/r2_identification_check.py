"""Is R2's design ESTIMABLE on the data collected so far -- without looking at delta.

This exists because of a sequencing problem. The boundary months are taped, so
`kmt r2` would now run; but analysis_plan Addendum 4 commits R2 to the window
2025-05-01..2026-06-30, and that window is still being collected. Computing
delta now would be an early look at outcome data on a partial window, spending
the first look before the sample the plan commits to exists.

The engineering question is separate and legitimate: does the design IDENTIFY
at all on real data? r2/did.py has only ever run on synthetic fixtures. If
fit_did returns None because of some property of the live panel -- one month
with no control markets, treatment collinear with a month dummy, series
tickers missing -- that is a bug to find now, not after the window closes.

So this reports the SAMPLE DESCRIPTION and nothing else:
  - panel rows, event clusters, months
  - treated / control arm sizes per month
  - whether fit_did returns a result or None, and if None, which guard fired

It deliberately does NOT print delta_did, its standard error, its interval, or
psi. That split is the spec's own sequential gate: counts are the sample
definition, psi is the result. Reading a count is calibration; reading the
estimate is the test.

Usage:
    python tools/r2_identification_check.py
"""

from __future__ import annotations

import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from kalshi_mt.fees.schedule import load_fee_schedule  # noqa: E402
from kalshi_mt.r1.panel import build_yes_only_panel_backfilled  # noqa: E402
from kalshi_mt.r2.did import run_did_pair, treated_flags  # noqa: E402
from kalshi_mt.store.db import connect_read_only  # noqa: E402
from kalshi_mt.store.parquet import TradeStore  # noqa: E402
from kalshi_mt.util import load_config  # noqa: E402

# Structural fields only. delta_did, its SE and its interval are deliberately
# absent -- see the module docstring.
STRUCTURAL = [
    "n", "n_clusters", "n_treated_obs", "n_control_obs",
    "n_treated_series", "months", "used_wild_bootstrap", "clean_controls",
]


def main() -> int:
    config = load_config()
    conn = connect_read_only()
    try:
        # NOT the universe_log idiom. `kmt build` has not been run for R2, so
        # that log is empty for this window and "NOT IN (empty)" excludes
        # nothing -- it returned 14,907,046 markets against a real in-scope set
        # of 126,087 (see db.UniverseLogNotBuiltError). This check has to work
        # BEFORE build has run, so it applies the filters directly and requires
        # a tape, which is exactly what "analysable" means here.
        in_scope = {
            r[0] for r in conn.execute(
                """
                SELECT m.ticker
                FROM markets m
                JOIN quotes q ON q.ticker = m.ticker
                JOIN pass2_progress p ON p.ticker = m.ticker AND p.status = 'done'
                WHERE m.in_r2_window = 1
                  AND m.volume_fp >= 1000
                  AND (m.close_time_epoch - m.open_time_epoch) >= 86400
                  AND q.spread IS NOT NULL AND q.spread <= 0.20
                """
            ).fetchall()
        }
        print(f"R2 analysable markets (filters passed AND taped): {len(in_scope):,}")
        store = TradeStore(config["storage"]["parquet_dir"])
        panel = build_yes_only_panel_backfilled(conn, store, in_scope)
    finally:
        conn.close()

    print(f"panel rows: {len(panel):,}")
    if panel.is_empty():
        print("EMPTY PANEL -- nothing to check yet.")
        return 1

    schedule = load_fee_schedule()
    now, ever = treated_flags(panel, schedule)
    months = [
        datetime.fromtimestamp(int(e), tz=timezone.utc).strftime("%Y-%m")
        for e in panel["close_time_epoch"].to_list()
    ]
    treated_by_month: Counter[str] = Counter()
    total_by_month: Counter[str] = Counter()
    for month, flag in zip(months, now):
        total_by_month[month] += 1
        if flag:
            treated_by_month[month] += 1

    print()
    print("arm sizes by month (a month needs BOTH arms to contribute):")
    print(f"  {'month':<9} {'rows':>9} {'treated':>9} {'control':>9}  both?")
    usable = 0
    for month in sorted(total_by_month):
        tot = total_by_month[month]
        tre = treated_by_month[month]
        ctl = tot - tre
        both = tre > 0 and ctl > 0
        if both:
            usable += 1
        print(f"  {month:<9} {tot:>9,} {tre:>9,} {ctl:>9,}  {'yes' if both else 'NO'}")
    print(f"  months with both arms: {usable}")

    print()
    print("identification (structural fields only -- delta is NOT read here):")
    pair = run_did_pair(panel, schedule)
    for name, result in pair.items():
        if result is None:
            print(f"  {name:<16} NOT IDENTIFIED -- fit_did returned None")
            continue
        fields = ", ".join(f"{k}={getattr(result, k)}" for k in STRUCTURAL)
        print(f"  {name:<16} identified: {fields}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
