"""Event-study check on the maker-fee DiD's identifying assumption.

WHY THIS IS A SEPARATE STEP AND NOT PART OF `kmt r2`
----------------------------------------------------
`kmt r2` writes reports/r2/verdict_lock.json, which is committed and which
`kmt r3-check` refuses to proceed without. Re-running it to add a diagnostic
would rewrite the locked verdict, and a locked artifact that gets rewritten
whenever someone wants another statistic is not locked. This writes its own
artifact, reports/r2/event_study.json, and touches nothing else.

STATUS: POST-HOC, AND THE TWO HALVES DIFFER
-------------------------------------------
This analysis was NOT pre-specified. It was added on 2026-08-27, after the
static delta_did had already returned its null, in response to a critique that
the parallel-trends assumption was never stated or checked. See
docs/analysis_plan.md Addendum 6.

The pre-period test is a validity check: it can only undermine the design, never
manufacture a finding, so adding it late costs nothing but a date. The
post-period joint test is a hypothesis test run after a pre-specified test
returned zero, and anything it finds is EXPLORATORY -- the paper labels it so
wherever it is reported. Do not let a future caller quote the post-period result
without that label.

WHAT IT TESTS
-------------
delta_did assumes treated and untreated series would have moved in parallel
absent the maker fee. That assumption is not directly testable, but its
observable implication is: if the favorite-longshot slopes were already
diverging BEFORE Kalshi charged anybody, the pre-treatment coefficients will
show it.

The concern is specific rather than ritual here. Assignment is visibly
non-random -- Kalshi charged 8-14% of markets carrying 61-66% of volume, i.e.
the series where market-making is most profitable -- and maker profitability is
economically linked to the very slope being measured. `Ever*P` absorbs a
permanent level and slope difference between those groups; it does not absorb a
differential TREND. Selection of this kind raises the bar for parallel trends
rather than lowering it, so the check is load-bearing.

THE PANEL CACHE
---------------
Building the pooled panel is the expensive part (an ASOF join over a 376.8M-fill
tape, roughly two hours). It is written to data/pooled_panel.parquet on first
build and reused after, because a diagnostic that costs two hours to re-run is a
diagnostic nobody re-runs.

Usage:
    python tools/run_event_study.py            # build or reuse the cache
    python tools/run_event_study.py --rebuild  # force a fresh panel
"""

from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import polars as pl  # noqa: E402

from kalshi_mt.fees.schedule import load_fee_schedule  # noqa: E402
from kalshi_mt.r1.panel import build_yes_only_panel_backfilled  # noqa: E402
from kalshi_mt.r2.did import fit_event_study  # noqa: E402
from kalshi_mt.store import db  # noqa: E402
from kalshi_mt.store.parquet import TradeStore  # noqa: E402
from kalshi_mt.util import PROJECT_ROOT, load_config  # noqa: E402

PANEL_CACHE = PROJECT_ROOT / "data" / "pooled_panel.parquet"
OUT = PROJECT_ROOT / "reports" / "r2" / "event_study.json"


def pooled_panel(*, rebuild: bool = False) -> pl.DataFrame:
    if PANEL_CACHE.exists() and not rebuild:
        print(f"reusing cached panel {PANEL_CACHE.name} "
              f"({PANEL_CACHE.stat().st_size / 2**20:.0f} MB)")
        return pl.read_parquet(PANEL_CACHE)

    config = load_config()
    conn = db.connect(config["storage"]["db_path"])
    try:
        store = TradeStore(config["storage"]["parquet_dir"])
        # Exactly the pooled scope kmt r2 uses: R1 union R2, so every category
        # has a genuine pre-boundary baseline and the boundary dummies are not
        # constant.
        scope = db.in_scope_tickers(conn, "r1") | db.in_scope_tickers(conn, "r2")
        print(f"building the pooled panel over {len(scope):,} markets -- this is the slow part")
        t0 = time.time()
        panel = build_yes_only_panel_backfilled(conn, store, scope)
        print(f"  built {len(panel):,} rows in {time.time() - t0:.0f}s")
    finally:
        conn.close()

    PANEL_CACHE.parent.mkdir(parents=True, exist_ok=True)
    panel.write_parquet(PANEL_CACHE)
    print(f"  cached to {PANEL_CACHE.name}")
    return panel


def main() -> int:
    rebuild = "--rebuild" in sys.argv
    panel = pooled_panel(rebuild=rebuild)

    schedule = load_fee_schedule()
    t0 = time.time()
    result = fit_event_study(panel, schedule)
    if result is None:
        print("NOT IDENTIFIED -- reported as such, never as a null")
        OUT.write_text(json.dumps({"identified": False}, indent=2) + "\n", encoding="utf-8")
        return 1

    print(f"fitted in {time.time() - t0:.0f}s on {result.n:,} rows, "
          f"{result.n_clusters:,} clusters, {result.n_treated_series} treated series, "
          f"{result.n_cohorts} cohorts")
    print()
    print(f"  {'event time k':>12} {'delta_k':>10} {'se':>9}  95% CI")
    for k in sorted(result.coefficients):
        marker = "  <- reference is k=-1" if k == result.reference + 1 else ""
        pre = "pre " if k < result.reference else "post"
        print(f"  {pre} k={k:>+3}  {result.coefficients[k]:>+10.5f} {result.std_errors[k]:>9.5f}  "
              f"[{result.ci_lo[k]:>+8.5f}, {result.ci_hi[k]:>+8.5f}]{marker}")
    print()
    print(f"  joint pre-trend test: chi2({result.pretrend_df}) = {result.pretrend_chi2:.3f}, "
          f"p = {result.pretrend_p:.4f}")
    print("  -> " + ("PRE-TRENDS DETECTED; parallel trends is not supported"
                     if result.pretrend_p < 0.05 else
                     "no detectable pre-trend; consistent with parallel trends"))
    print()
    print(f"  joint POST-treatment test: chi2({result.posttrend_df}) = "
          f"{result.posttrend_chi2:.3f}, p = {result.posttrend_p:.4f}")
    print("  -> " + ("dynamics present: the static average hides them"
                     if result.posttrend_p < 0.05 else
                     "no joint post-treatment effect; individual stars are "
                     "consistent with multiple testing"))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(result)
    payload["identified"] = True
    # JSON object keys must be strings, and an int-keyed dict round-trips to
    # string keys anyway -- make that explicit rather than discovering it on read.
    for field in ("coefficients", "std_errors", "ci_lo", "ci_hi"):
        payload[field] = {str(k): v for k, v in payload[field].items()}
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"\nwritten to {OUT.relative_to(PROJECT_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
