"""`kmt` CLI skeleton (Phase 0-1).

Commands are wired to their implementations phase by phase; until then each
prints a clear not-implemented notice and exits non-zero so cron jobs fail
loudly rather than silently succeeding.

Exit codes: 0 success, 1 unexpected/hard failure, 2 not implemented,
3 STOP -- operator decision required (Step Zero found a required endpoint
needs authentication).
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys

import typer

from kalshi_mt.util import keep_system_awake, load_config, setup_logging, use_stable_event_loop

use_stable_event_loop()

_log = logging.getLogger("kalshi_mt.crash")


def _log_uncaught_exception(exc_type, exc_value, exc_tb) -> None:
    """Last-resort handler: any exception gets one guaranteed line -- with
    full traceback -- in data/logs/kmt.jsonl before the process exits."""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    _log.critical("uncaught exception -- process is about to exit", exc_info=(exc_type, exc_value, exc_tb))
    sys.__excepthook__(exc_type, exc_value, exc_tb)


sys.excepthook = _log_uncaught_exception

app = typer.Typer(
    name="kmt",
    help="Kalshi Makers & Takers Replication -- read-only research instrument.",
    no_args_is_help=True,
)


def _parse_date_to_epoch(
    value: str | None, flag: str, *, end_of_day: bool = False
) -> int | None:
    """YYYY-MM-DD -> UTC epoch seconds. `end_of_day` makes an upper bound
    inclusive of the whole day, so --close-to 2025-12-31 means through
    23:59:59 rather than silently dropping that day's markets."""
    if value is None:
        return None
    from datetime import datetime, time, timezone
    try:
        d = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        typer.secho(f"{flag} must be YYYY-MM-DD, got {value!r}", fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None
    t = time(23, 59, 59) if end_of_day else time(0, 0, 0)
    return int(datetime.combine(d, t, tzinfo=timezone.utc).timestamp())


def _not_implemented(command: str, phase: str) -> None:
    typer.secho(
        f"`kmt {command}` is not implemented yet (arrives in {phase}).",
        fg=typer.colors.YELLOW,
        err=True,
    )
    raise typer.Exit(code=2)


@app.callback()
def main() -> None:
    """Initialize config and logging for every command."""
    from dotenv import load_dotenv

    load_dotenv()
    setup_logging(load_config())


@app.command(name="step-zero")
def step_zero() -> None:
    """Verify Kalshi's public API has what this replication needs -- the hard gate (spec S3)."""
    from kalshi_mt.stepzero.report import run_step_zero, write_findings

    config = load_config()

    async def _run():
        return await run_step_zero(config)

    report = asyncio.run(_run())

    for c in report.checks:
        color = {
            "PASS": typer.colors.GREEN, "PARTIAL": typer.colors.YELLOW,
            "FAIL": typer.colors.RED, "AUTH_REQUIRED": typer.colors.RED,
        }[c.status]
        typer.secho(f"Check {c.id} [{c.status}]: {c.name}", fg=color)

    md_path = write_findings(report)

    if report.verdict == "STOP":
        typer.secho("", err=True)
        typer.secho("=" * 70, fg=typer.colors.RED, bold=True, err=True)
        typer.secho("STOP -- OPERATOR DECISION REQUIRED".center(70), fg=typer.colors.RED, bold=True, err=True)
        typer.secho("=" * 70, fg=typer.colors.RED, bold=True, err=True)
        typer.secho(f"Reason: {report.stop_reason}", fg=typer.colors.RED, err=True)
        typer.secho(
            "This repository registers nothing on its own. Read "
            f"{md_path} and .env.example, then make a deliberate decision.",
            fg=typer.colors.RED, err=True,
        )
        raise typer.Exit(code=3)

    typer.secho(f"\nGO -- findings written to {md_path}", fg=typer.colors.GREEN, bold=True)
    raise typer.Exit(code=0)


@app.command()
def status() -> None:
    """Show the last Step Zero verdict and basic config sanity."""
    from pathlib import Path

    from kalshi_mt.util import PROJECT_ROOT

    findings_path = PROJECT_ROOT / "reports" / "step_zero" / "findings.json"
    if not findings_path.exists():
        typer.echo("step-zero: not yet run (no reports/step_zero/findings.json)")
        raise typer.Exit(code=0)

    data = json.loads(findings_path.read_text(encoding="utf-8"))
    typer.echo(f"step-zero: {data['verdict']} at {data['ts']} (base_url={data['base_url']})")
    for c in data["checks"]:
        typer.echo(f"  check {c['id']} [{c['status']}]: {c['name']}")
    if data.get("stop_reason"):
        typer.secho(f"  stop_reason: {data['stop_reason']}", fg=typer.colors.RED)
    raise typer.Exit(code=0)


fetch_app = typer.Typer(help="Two-pass fetch pipeline (spec S3, Phase 2).")
app.add_typer(fetch_app, name="fetch")


@fetch_app.command("pass1")
def fetch_pass1(
    max_series: int | None = typer.Option(
        None, help="Bound how many not-yet-done series the historical scan touches this run "
                    "(omit for no bound -- the full ~12k-series universe, hours-long)."
    ),
    market_limit: int | None = typer.Option(
        None, help="Bound how many markets get a price-panel/quote fetch this run."
    ),
    live_max_pages: int | None = typer.Option(
        None, help="Bound how many cursor pages the live 2023-2026 discovery sweep fetches "
                    "this run (1000 markets/page) -- omit for no bound (tens of thousands of "
                    "markets across the full window; ALWAYS set this for a quick/verification run)."
    ),
    resolve_batch_size: int = typer.Option(
        200, help="Bound how many markets get series_ticker/category resolved "
                   "(one GET /events call per distinct event_ticker, cached) this run."
    ),
    min_volume: float = typer.Option(
        1000.0, help="Skip series/category resolution AND the panel/quote fetch for markets "
                     "below this volume_fp -- matches R1/R2's own $1k filter (fetch/pass2.py's "
                     "MIN_VOLUME_FP). A full live sweep discovers hundreds of thousands of thin "
                     "markets that would never survive Phase 3 anyway (confirmed live, 2026-07: "
                     "576k+ from the live sweep alone); pass 0 to disable and process everything."
    ),
    min_open_hours: float = typer.Option(
        24.0, help="Skip series/category resolution AND the panel/quote fetch for markets open "
                   "fewer than this many hours -- matches R1/R2's own hourly-reset exclusion "
                   "(fetch/pass2.py's MIN_OPEN_SECONDS). Confirmed live, 2026-07-21: of ~2.56M "
                   "markets clearing $1k volume, only ~510k also clear 24h; the rest are "
                   "hourly-reset crypto/index sub-markets no downstream phase uses. Pass 0 to "
                   "disable and process every volume-qualifying market regardless of duration."
    ),
    resolve_max_spread: float | None = typer.Option(
        None, "--resolve-max-spread",
        help="Narrow series/category resolution to markets whose closing quote already clears "
             "this spread (e.g. 0.20). Measured 2026-07-26: the volume+24h-scoped resolve backlog "
             "was 475,845 markets across 264,596 events (~9h of GET /events), while the subset "
             "also clearing spread<=20c was 41,962 across 12,429 events (~26 min) -- same "
             "analytical coverage, since category is only consumed for in-scope markets. Needs "
             "quotes to exist already, so it is for a targeted catch-up run, not a fresh sweep.",
    ),
    max_concurrent_series: int = typer.Option(
        20, "--max-concurrent-series",
        help="Concurrent series in the historical scan. The default is unchanged; lower it for a "
             "targeted catch-up on a handful of very large series, where all of them running at "
             "once sustains a 429 storm that exhausts retries and drops the series entirely "
             "(observed 2026-07-26: the last 15 series failed identically on two consecutive "
             "passes until they were the only work left).",
    ),
    panel_quote_close_from: str | None = typer.Option(
        None, "--panel-quote-close-from",
        help="Restrict the panel/quote fetch to markets closing on/after this date (YYYY-MM-DD).",
    ),
    panel_quote_close_to: str | None = typer.Option(
        None, "--panel-quote-close-to",
        help="Restrict the panel/quote fetch to markets closing on/before this date (YYYY-MM-DD). "
             "Together with --panel-quote-close-from this prioritises the months an estimate "
             "actually needs: measured 2026-07-28, R2's full backlog is ~751k markets (weeks), "
             "but delta_fee/delta_pub are identified only by the months BRACKETING their "
             "boundaries -- 2025-05..2025-12 is ~104k markets, and without those months no delta "
             "exists at all however much of 2026 is collected. The phase orders by ticker, so "
             "months interleave arbitrarily and the ones that matter arrive last unless asked for.",
    ),
    panel_quote_window: str | None = typer.Option(
        None, "--panel-quote-window",
        help="Restrict ONLY the panel/quote fetch to one analysis window ('r1' or 'r2'); "
             "discovery stays whole-universe either way. That phase walks a keyset cursor "
             "ordered by ticker, so with a large R2 backlog R1's remainder finishes only "
             "after most of R2 -- yet R1's count-reconciliation gate is the prerequisite "
             "for every later phase (spec S1). Pass 'r1' to fetch R1's remainder first. "
             "Omit for the original both-windows behaviour.",
    ),
) -> None:
    """Universe discovery (live sweep + historical series scan) + boundary-tick
    price panel + closing quotes. Resumable -- safe to re-run; each sub-phase
    picks up where it left off (store/db.py's series_scan_state /
    pass2_progress checkpoints)."""
    from kalshi_mt.api.http import TokenBucket
    from kalshi_mt.api.kalshi import KalshiClient
    from kalshi_mt.fetch.pass1 import run_pass1
    from kalshi_mt.store import db

    from kalshi_mt.fetch.pass1 import ANALYSIS_WINDOW_COLUMNS

    config = load_config()
    min_volume_fp = None if min_volume <= 0 else min_volume
    min_open_duration_s = None if min_open_hours <= 0 else min_open_hours * 3600.0
    if panel_quote_window is not None and panel_quote_window not in ANALYSIS_WINDOW_COLUMNS:
        typer.secho(
            f"--panel-quote-window must be one of {sorted(ANALYSIS_WINDOW_COLUMNS)}, "
            f"got {panel_quote_window!r}",
            fg=typer.colors.RED, err=True,
        )
        raise typer.Exit(code=1)

    async def _run():
        bucket = TokenBucket(
            rate=config["kalshi"]["rate_limit"]["requests_per_second"],
            burst=config["kalshi"]["rate_limit"]["burst"],
        )
        client = KalshiClient(bucket, base_url=config["kalshi"]["base_url"])
        conn = db.connect(config["storage"]["db_path"])
        try:
            return await run_pass1(
                client, conn, max_series_this_run=max_series, market_processing_limit=market_limit,
                live_max_pages=live_max_pages, series_resolution_batch_size=resolve_batch_size,
                min_volume_fp=min_volume_fp, min_open_duration_s=min_open_duration_s,
                panel_quote_window=panel_quote_window,
                panel_quote_close_from=_parse_date_to_epoch(panel_quote_close_from, "--panel-quote-close-from"),
                panel_quote_close_to=_parse_date_to_epoch(panel_quote_close_to, "--panel-quote-close-to", end_of_day=True),
                resolve_max_spread=resolve_max_spread,
                max_concurrent_series=max_concurrent_series,
            )
        finally:
            await client.aclose()
            conn.close()

    # A wake lock for the duration. Without it this host's Modern Standby froze
    # a healthy-looking collector for ~22 of every 25 hours, with no error and
    # nothing but throughput to show it (util.keep_system_awake's docstring has
    # the measurement).
    with keep_system_awake("pass 1 fetch"):
        stats = asyncio.run(_run())
    typer.echo(json.dumps(stats, indent=2, default=str))


@fetch_app.command("pass2")
def fetch_pass2(
    ticker_limit: int | None = typer.Option(
        None, help="Bound how many in-scope markets get a full trade-tape fetch this run."
    ),
    max_pages: int | None = typer.Option(
        None, help="Bound pages fetched per market this run (for a resumable, incremental pass)."
    ),
    window: str | None = typer.Option(
        None, "--window",
        help="Restrict to one analysis window ('r1' or 'r2'). Without an ORDER BY, in-scope "
             "candidates come back in whatever order SQLite produces, letting the larger R2 "
             "backlog dominate a run even though R1's full tape is what the count-reconciliation "
             "gate needs first (spec S1). Pass 'r1' to fetch R1's remainder first. Omit for the "
             "original both-windows behaviour.",
    ),
    close_from: str | None = typer.Option(
        None, "--close-from",
        help="Only fetch tapes for markets closing on or after this date (YYYY-MM-DD).",
    ),
    close_to: str | None = typer.Option(
        None, "--close-to",
        help="Only fetch tapes for markets closing on or before this date (YYYY-MM-DD). "
             "Together with --close-from this restricts Pass 2 to a settled part of the "
             "window: a month's in-scope set is only final once its quotes are complete, so "
             "fetching tapes for months still being quoted means re-running later anyway.",
    ),
) -> None:
    """Full trade tape for in-scope (volume/spread/duration-filtered) contracts
    only. Resumable per-market via pass2_progress."""
    from kalshi_mt.api.http import TokenBucket
    from kalshi_mt.api.kalshi import KalshiClient
    from kalshi_mt.fetch.pass2 import ANALYSIS_WINDOW_COLUMNS, run_pass2
    from kalshi_mt.store import db
    from kalshi_mt.store.parquet import TradeStore

    config = load_config()
    if window is not None and window not in ANALYSIS_WINDOW_COLUMNS:
        typer.secho(
            f"--window must be one of {sorted(ANALYSIS_WINDOW_COLUMNS)}, got {window!r}",
            fg=typer.colors.RED, err=True,
        )
        raise typer.Exit(code=1)

    async def _run():
        bucket = TokenBucket(
            rate=config["kalshi"]["rate_limit"]["requests_per_second"],
            burst=config["kalshi"]["rate_limit"]["burst"],
        )
        client = KalshiClient(bucket, base_url=config["kalshi"]["base_url"])
        conn = db.connect(config["storage"]["db_path"])
        trade_store = TradeStore(config["storage"]["parquet_dir"])
        try:
            return await run_pass2(
                client, conn, trade_store, ticker_limit=ticker_limit,
                max_pages_per_market=max_pages, window=window,
                close_from=_parse_date_to_epoch(close_from, "--close-from"),
                close_to=_parse_date_to_epoch(close_to, "--close-to", end_of_day=True),
            )
        finally:
            await client.aclose()
            conn.close()

    with keep_system_awake("pass 2 fetch"):
        stats = asyncio.run(_run())
    typer.echo(json.dumps({k: v for k, v in stats.items() if k != "results"}, indent=2, default=str))


@app.command()
def build() -> None:
    """R1 filters, panel construction, count-reconciliation gate, and the
    frozen calendar-2024 category-mix artifact Phase 7 depends on."""
    from kalshi_mt.r1.filters import (
        DIVERGENCE_NOTES,
        DOLLAR_BRANCH_LOG_WINDOW,
        VOLUME_READING_PIN,
        apply_and_log,
    )
    from kalshi_mt.r1.panel import (
        basis_counts,
        build_doubled_panel,
        build_yes_only_panel,
        build_yes_only_panel_backfilled,
    )
    from kalshi_mt.r1.reconcile import (
        compute_calendar_2024_mix,
        coverage_gap_breakdown,
        reconcile_counts,
        write_frozen_2024_mix,
    )
    from kalshi_mt.store import db
    from kalshi_mt.store.parquet import TradeStore
    from kalshi_mt.util import PROJECT_ROOT

    config = load_config()
    conn = db.connect(config["storage"]["db_path"])
    try:
        trade_store = TradeStore(config["storage"]["parquet_dir"])

        # PRIMARY: the contract reading of BDW's volume filter
        # (dollar_volume_by_ticker=None thresholds Kalshi's own volume_fp,
        # which is a contract count). Pinned 2026-07-26 -- see
        # r1/filters.py's VOLUME_READING_PIN for the measurement that decided
        # it: at this stage our independently collected universe lands within
        # 0.1% of BDW's 12,403 events and 2.9% of their 46,282 contracts.
        filter_summary = apply_and_log(conn, window="r1", dollar_volume_by_ticker=None)
        in_scope = db.in_scope_tickers(conn, "r1")

        # PRIMARY panel: backfill on no-trade lookback days (CLAUDE.md S3,
        # amended 2026-07-26). Built from Pass 2's tape, so no refetch.
        yes_only = build_yes_only_panel_backfilled(conn, trade_store, in_scope)
        doubled = build_doubled_panel(yes_only)
        reconciliation = reconcile_counts(conn, yes_only, doubled)
        gap_breakdown = coverage_gap_breakdown(conn, window="r1")

        # SENSITIVITY panel: the skip rule, from Pass 1's stored price_panel.
        skip_yes_only = build_yes_only_panel(conn, in_scope)
        skip_doubled = build_doubled_panel(skip_yes_only)
        skip_reconciliation = reconcile_counts(conn, skip_yes_only, skip_doubled)

        # SENSITIVITY: the literal dollar-notional reading, computed from Pass
        # 2's real tape. Logged under its own window label so it stays fully
        # queryable without shrinking the primary in-scope set above (which is
        # an exact match on window='r1'). Reported, never silently dropped:
        # under it the sample roughly halves, and a sample rule that
        # differentially removes longshots is itself a result in a paper about
        # favorite-longshot bias.
        dollar_volume_by_ticker = trade_store.dollar_volume_by_ticker()
        dollar_summary = apply_and_log(
            conn, window="r1", dollar_volume_by_ticker=dollar_volume_by_ticker,
            log_window=DOLLAR_BRANCH_LOG_WINDOW,
        )
        dollar_in_scope = {
            r[0] for r in conn.execute(
                "SELECT ticker FROM markets m WHERE m.in_r1_window = 1 "
                "AND m.ticker NOT IN (SELECT ticker FROM universe_log WHERE window = ?)",
                (DOLLAR_BRANCH_LOG_WINDOW,),
            ).fetchall()
        }
        dollar_yes_only = build_yes_only_panel(conn, dollar_in_scope)
        dollar_doubled = build_doubled_panel(dollar_yes_only)
        dollar_reconciliation = reconcile_counts(conn, dollar_yes_only, dollar_doubled)

        # Frozen 2024 mix comes from the PRIMARY branch only -- R2's
        # decomposition weights must trace to one pinned construction.
        mix = compute_calendar_2024_mix(yes_only)
        mix_path = write_frozen_2024_mix(mix, PROJECT_ROOT / "data" / "frozen_2024_mix.json")

        result = {
            "construction": {
                "volume_reading": {"primary": "contract_count", "sensitivity": "dollar_notional"},
                "lookback_rule": {"primary": "backfill", "sensitivity": "skip"},
                "volume_pin": VOLUME_READING_PIN,
                "divergence_notes": DIVERGENCE_NOTES,
            },
            "filters": filter_summary,
            "panel": basis_counts(yes_only, doubled),
            "reconciliation": reconciliation["deltas"],
            "coverage_gap_breakdown": gap_breakdown,
            "frozen_2024_mix": {"path": str(mix_path), "categories": len(mix)},
            "sensitivity_dollar_notional": {
                "filters": dollar_summary,
                "panel": basis_counts(dollar_yes_only, dollar_doubled),
                "reconciliation": dollar_reconciliation["deltas"],
            },
            "sensitivity_skip_lookback": {
                "panel": basis_counts(skip_yes_only, skip_doubled),
                "reconciliation": skip_reconciliation["deltas"],
            },
        }
    finally:
        conn.close()

    typer.echo(json.dumps(result, indent=2, default=str))


@app.command()
def r1() -> None:
    """R1 MZ regression + reproduction report: by-year/by-category psi vs
    BDW Tables 8-9, win-rate curve vs Fig 3, returns-by-band vs Fig 5,
    maker/taker split vs Fig 6/Table 10, divergence log."""
    from kalshi_mt.fees.schedule import bdw_fee_model, load_fee_schedule
    from kalshi_mt.r1.field_population import (
        REQUIRED_COLUMNS as FIELD_POPULATION_COLUMNS,
    )
    from kalshi_mt.r1.field_population import field_population_by_era
    from kalshi_mt.r1.panel import build_doubled_panel, build_yes_only_panel_backfilled
    from kalshi_mt.r1.regression import verify_two_way_equals_one_way_clustering
    from kalshi_mt.r1.reproduction import (
        by_category_psi,
        by_year_psi,
        maker_taker_split,
        returns_by_band,
        win_rate_by_band,
        write_divergence_log,
    )
    from kalshi_mt.store import db
    from kalshi_mt.store.parquet import TradeStore
    from kalshi_mt.util import PROJECT_ROOT

    config = load_config()
    conn = db.connect(config["storage"]["db_path"])
    try:
        in_scope = db.in_scope_tickers(conn, "r1")
        trade_store = TradeStore(config["storage"]["parquet_dir"])
        # PRIMARY construction: backfill on no-trade lookback days
        # (CLAUDE.md S3, amended 2026-07-26). Must match `kmt build`'s
        # primary, or R1's reproduction tables would describe a different
        # sample than the gate that cleared them.
        yes_only = build_yes_only_panel_backfilled(conn, trade_store, in_scope)
        doubled = build_doubled_panel(yes_only)
        # PRIMARY fee model for R1 is BDW's own (uniform taker 0.07, makers
        # free), so a gap against their Fig 5 is theirs to explain, not ours.
        # The schedule Kalshi actually published runs as the sensitivity
        # branch -- see bdw_fee_model's docstring for what differs and why it
        # is reported rather than silently adopted.
        fee_schedule = bdw_fee_model()
        sourced_fee_schedule = load_fee_schedule()

        by_year = by_year_psi(yes_only)
        by_category = by_category_psi(yes_only)
        clustering_check = verify_two_way_equals_one_way_clustering(yes_only)

        # Maker/taker runs on the DOUBLED PANEL, not the raw fill tape: BDW's
        # Table 10 totals 313,972 observations (the doubled panel) with Makers
        # exactly 156,986, and their own text -- "because we include the same
        # contract at different points during its lifetime ... up to 11 times"
        # -- only parses if the returns are panel-based. The tape is still read
        # for field_population_by_era, which is genuinely a per-fill diagnostic.
        mt_split = maker_taker_split(doubled, fee_schedule)
        # Streamed, not read_all(): the tape is several GB compressed and
        # materialising it is the failure that killed Pass 2 on 2026-08-24.
        field_population = field_population_by_era(
            trade_store.iter_fills(columns=FIELD_POPULATION_COLUMNS)
        )

        log_path = write_divergence_log(
            {
                "by_year_psi": by_year, "by_category_psi": by_category,
                "taker_field_population_by_era": field_population,
            },
            PROJECT_ROOT / "reports" / "r1" / "divergence_log.md",
        )

        def _fit_summary(entry):
            fit = entry.get("fit")
            out = {k: v for k, v in entry.items() if k != "fit"}
            out["fit"] = None if fit is None else {
                "n": fit.n, "n_clusters": fit.n_clusters, "alpha": fit.alpha,
                "alpha_se": fit.alpha_se, "psi": fit.psi, "psi_se": fit.psi_se,
            }
            return out

        result = {
            "in_scope_markets": len(in_scope),
            "by_year_psi": {y: _fit_summary(e) for y, e in by_year.items()},
            "by_category_psi": {c: _fit_summary(e) for c, e in by_category.items()},
            "clustering_verification": clustering_check,
            "win_rate_by_band": win_rate_by_band(doubled),
            "returns_by_band": returns_by_band(yes_only, fee_schedule),
            "sensitivity_sourced_fee_schedule": {
                "note": (
                    "Same panel, priced with Kalshi's own published fee schedule "
                    "(data/fees.yaml) instead of BDW's uniform 0.07: adds the "
                    "S&P500/Nasdaq-100 half rate (18.3% of in-scope markets) and "
                    "the 0.14 rate in force until 2021-08-01."
                ),
                "returns_by_band": returns_by_band(yes_only, sourced_fee_schedule),
                "maker_taker_split": maker_taker_split(doubled, sourced_fee_schedule),
            },
            "maker_taker_split": mt_split,
            "taker_field_population_by_era": field_population,
            "divergence_log": str(log_path),
        }
    finally:
        conn.close()

    typer.echo(json.dumps(result, indent=2, default=str))


@app.command()
def r2() -> None:
    """R2 pooled category-interacted regression, composition decomposition,
    verdict binding, and horizon robustness (Phase 7, docs/analysis_plan.md
    S2). Refuses to run without R1's frozen calendar-2024 category-mix
    artifact (data/frozen_2024_mix.json) -- Phase 7's own hard dependency,
    never recomputed from R2 data (spec's pre-registration firewall)."""
    from dataclasses import asdict

    from kalshi_mt.fees.schedule import load_fee_schedule
    from kalshi_mt.r1.filters import apply_and_log
    from kalshi_mt.r1.panel import build_yes_only_panel_backfilled
    from kalshi_mt.r1.reconcile import load_frozen_2024_mix
    from kalshi_mt.r1.regression import fit_mz_regression
    from kalshi_mt.r2.decomposition import category_weights_from_panel, decompose, delta_bar_with_ci
    from kalshi_mt.r2.did import run_did_pair
    from kalshi_mt.r2.horizon import run_horizon_robustness
    from kalshi_mt.r2.regression import fit_all_categories
    from kalshi_mt.r2.report import build_r2_report, load_r2_report, write_r2_report
    from kalshi_mt.r2.verdicts import determine_verdict
    from kalshi_mt.store import db
    from kalshi_mt.store.parquet import TradeStore
    from kalshi_mt.util import PROJECT_ROOT

    config = load_config()
    mix_path = PROJECT_ROOT / "data" / "frozen_2024_mix.json"
    try:
        frozen_2024_mix = load_frozen_2024_mix(mix_path)
    except FileNotFoundError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None

    conn = db.connect(config["storage"]["db_path"])
    try:
        trade_store = TradeStore(config["storage"]["parquet_dir"])
        # R2 reuses R1's own filter thresholds (volume/spread/duration/
        # settlement-mismatch), applied to the R2 window -- apply_and_log
        # REPLACES this window's exclusions rather than appending (see
        # db.replace_universe_exclusions), so calling it here rather than
        # requiring a separate `kmt build --window r2` step keeps `kmt r2`
        # runnable on its own and re-derivable.
        # Contract reading, matching R1's pinned primary (r1/filters.py's
        # VOLUME_READING_PIN) -- analysis_plan.md S2 defines R2 as an extension
        # of R1's construction with no separate filter definition, so the two
        # windows must not sit on different readings of the volume filter.
        r2_filter_summary = apply_and_log(
            conn, window="r2", dollar_volume_by_ticker=None
        )
        r1_scope = db.in_scope_tickers(conn, "r1")
        r2_scope = db.in_scope_tickers(conn, "r2")
        # ONE construction on both sides of every boundary -- binding per
        # CLAUDE.md S3's R2 corollary. delta measures the CHANGE in psi at
        # the fee/publication boundaries within our own data, so a panel
        # rule that differed across a boundary is the one thing that would
        # actually break identification. Level fidelity to BDW is an R1
        # goal; internal consistency is R2's.
        r1_panel = build_yes_only_panel_backfilled(conn, trade_store, r1_scope)
        r2_panel = build_yes_only_panel_backfilled(conn, trade_store, r2_scope)
        # The boundary-interacted regression (r2/regression.py) needs data
        # on BOTH sides of the fee boundary to estimate delta_fee at all --
        # R2's own window STARTS exactly at 2025-05-01 (the fee boundary),
        # so an R2-only panel would make the fee dummy constant (always 1)
        # and the design matrix singular. R1 union R2 gives every category
        # a genuine pre-boundary baseline (alpha_c/psi_c, per
        # r2/decomposition.py's own docstring: "psi_bar_c is category c's
        # own baseline (pre-boundary) slope") plus both boundary shifts in
        # one fit -- this pooled scope is ONLY the regression's input;
        # category_weights_from_panel below stays R2-window-only, per spec
        # S2.3's own "R2-window weight" definition.
        pooled_panel = build_yes_only_panel_backfilled(conn, trade_store, r1_scope | r2_scope)
    finally:
        conn.close()

    r1_fit = fit_mz_regression(r1_panel)
    psi_bar_r1 = r1_fit.psi if r1_fit is not None else None

    category_fits = fit_all_categories(pooled_panel)
    r2_weights = category_weights_from_panel(r2_panel)

    decomposition = {
        "fee": decompose(category_fits, frozen_2024_mix, r2_weights, boundary="fee"),
        "publication": decompose(category_fits, frozen_2024_mix, r2_weights, boundary="publication"),
    }

    delta_bar = {
        "fee": delta_bar_with_ci(category_fits, frozen_2024_mix, boundary="fee"),
        "publication": delta_bar_with_ci(category_fits, frozen_2024_mix, boundary="publication"),
    }
    verdict = {}
    for boundary, estimate in delta_bar.items():
        if psi_bar_r1 is not None and estimate is not None:
            verdict[boundary] = determine_verdict(estimate, psi_bar_r1)
        else:
            verdict[boundary] = None

    horizon = run_horizon_robustness(pooled_panel, frozen_2024_mix)

    # PRIMARY for the fee question since analysis_plan.md Addendum 3: Kalshi's
    # maker fee was a per-series surcharge, not an exchange-wide regime change,
    # so treated and untreated series in the same months identify it far better
    # than a break at one date can. delta_bar["fee"] above is still computed and
    # still written to the locked artifact -- it is what the plan originally
    # committed to, and a specification change has to be visible, not tidy.
    did = run_did_pair(pooled_panel, load_fee_schedule())
    maker_fee_did = {
        "primary_for": "fee boundary (analysis_plan.md Addendum 3)",
        "twfe": None if did["twfe"] is None else asdict(did["twfe"]),
        "clean_controls": None if did["clean_controls"] is None else asdict(did["clean_controls"]),
        "note": (
            "delta_did is the differential change in the MZ slope while a series "
            "carries a maker fee, net of the common calendar path. None means the "
            "design is not identified on this sample (no treated rows, no controls, "
            "or a single month) -- never a null result."
        ),
    }

    report = build_r2_report(
        r2_filters=r2_filter_summary, psi_bar_r1=psi_bar_r1,
        r1_panel_n=len(r1_panel), r2_panel_n=len(r2_panel), pooled_panel_n=len(pooled_panel),
        categories_fit=sorted(category_fits.keys()), delta_bar=delta_bar, verdict=verdict,
        decomposition=decomposition, horizon=horizon, maker_fee_did=maker_fee_did,
    )
    lock_path = write_r2_report(report, PROJECT_ROOT / "reports" / "r2" / "verdict_lock.json")
    # Re-read the persisted payload (rather than re-stamping a second
    # locked_ts here) so stdout shows exactly what was written to disk --
    # the single locked_ts write_r2_report already made, not a second,
    # slightly later clock call.
    locked_report = load_r2_report(lock_path)
    locked_report["locked_artifact"] = str(lock_path)

    typer.echo(json.dumps(locked_report, indent=2, default=str))


@app.command(name="r3-check")
def r3_check() -> None:
    """R3's firewall gate (Phase 9, docs/analysis_plan.md S4): reports
    whether R3 code may proceed -- R2's verdict must already be locked to
    disk, and nothing in the rest of the repo may import kalshi_mt.r3.
    This command performs no R3 analysis itself (none exists yet); it only
    checks the gate."""
    from kalshi_mt.r3.firewall import R3FirewallError, check_no_r3_imports_outside_r3, require_r2_locked

    import_violations = check_no_r3_imports_outside_r3()
    try:
        r2_report = require_r2_locked()
        locked_ok = True
        locked_error = None
    except R3FirewallError as exc:
        r2_report = None
        locked_ok = False
        locked_error = str(exc)

    result = {
        "r2_locked": locked_ok,
        "r2_locked_ts": r2_report.get("locked_ts") if r2_report else None,
        "r2_verdict": r2_report.get("verdict") if r2_report else None,
        "import_violations": import_violations,
        "firewall_clear": locked_ok and not import_violations,
    }
    if locked_error:
        result["locked_error"] = locked_error

    typer.echo(json.dumps(result, indent=2, default=str))
    if not result["firewall_clear"]:
        raise typer.Exit(code=1)


def _charging_maker_rows(fee_schedule: dict) -> list[dict]:
    """Maker rows that actually charge something: a nonzero rate under a form
    other than `none`. Everything else is the zero-fee baseline row that has
    been in force since 2021 and stays untouched by the ribbon."""
    return [
        r for r in fee_schedule.get("schedule", [])
        if r.get("role") == "maker" and r.get("form") != "none" and float(r.get("rate", 0.0)) != 0.0
    ]


def _sourced_maker_rate(fee_schedule: dict) -> float | None:
    rows = _charging_maker_rows(fee_schedule)
    if not rows:
        return None
    return float(max(rows, key=lambda r: r["effective_from"])["rate"])


def _maker_rate_schedule(base_schedule: dict, maker_rate: float) -> dict:
    """A copy of base_schedule with every CHARGING maker row's rate replaced
    by `maker_rate` -- the fee-sensitivity ribbon's sweep (S3.3).

    Each row keeps its own `form`: Kalshi's first maker fee was flat per
    contract and only later became quadratic in price, so sweeping a single
    rate across a form-agnostic schedule would silently re-price the
    2025-05-13..2025-07-07 era under the wrong functional form. The taker
    rows (well sourced, no revision found across 16 archived schedules) and
    the zero-fee maker baseline are left alone."""
    import copy

    schedule = copy.deepcopy(base_schedule)
    for row in _charging_maker_rows(schedule):
        row["rate"] = maker_rate
    return schedule


def _compute_escalation(config: dict) -> dict:
    """Shared by `kmt escalate` and `kmt report`: loads R2's locked
    verdict, computes the maker >=50c margin and its fee-sensitivity
    ribbon on R2-window trades, and runs the S5 escalation determination.
    Returns a dict bundling everything both commands need -- callers
    should not duplicate this assembly."""
    from dataclasses import asdict

    from kalshi_mt.fees.ribbon import RibbonResult, compute_ribbon, default_fee_grid
    from kalshi_mt.fees.schedule import load_fee_schedule
    from kalshi_mt.r1.filters import apply_and_log
    from kalshi_mt.r2.maker_margin import (
        REQUIRED_COLUMNS as MAKER_MARGIN_COLUMNS,
    )
    from kalshi_mt.r2.maker_margin import MakerMarginResult, compute_maker_margin_ge_50c
    from kalshi_mt.r2.report import load_r2_report
    from kalshi_mt.r2.verdicts import DeltaBarEstimate
    from kalshi_mt.report.escalation import determine_escalation
    from kalshi_mt.store import db
    from kalshi_mt.store.parquet import TradeStore
    from kalshi_mt.util import PROJECT_ROOT

    r2_report = load_r2_report(PROJECT_ROOT / "reports" / "r2" / "verdict_lock.json")

    fee_bar = r2_report.get("delta_bar", {}).get("fee")
    pub_bar = r2_report.get("delta_bar", {}).get("publication")
    delta_bar_fee = DeltaBarEstimate(**fee_bar) if fee_bar else None
    delta_bar_pub = DeltaBarEstimate(**pub_bar) if pub_bar else None

    # CACHE THE EXPENSIVE HALF. The maker margin and its ribbon are 12 passes
    # over ~134M in-scope fills; the 2026-08-26 run took 19h16m. `kmt report`
    # calls this same function, so without a cache producing the write-up would
    # cost another nineteen hours to recompute numbers that are already on disk
    # and already committed. The cached inputs are pure functions of the tape
    # and data/fees.yaml, neither of which changes once collection is closed.
    #
    # Delete reports/r2/escalation_run.json to force a recompute -- which is
    # what to do if the tape or the fee schedule ever changes.
    cache_path = PROJECT_ROOT / "reports" / "r2" / "escalation_run.json"
    cached = None
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = None
        if cached and not ("maker_margin" in cached and "ribbon" in cached):
            cached = None

    fee_schedule = load_fee_schedule()

    if cached is not None:
        typer.secho(
            f"reusing the maker margin and ribbon from {cache_path.name} "
            "(delete it to force a recompute)",
            fg=typer.colors.YELLOW, err=True,
        )
        maker_margin = MakerMarginResult(**cached["maker_margin"])
        ribbon = RibbonResult(**cached["ribbon"]) if cached.get("ribbon") else None
    else:
        fee_schedule = load_fee_schedule()
        trade_store = TradeStore(config["storage"]["parquet_dir"])
        conn = db.connect(config["storage"]["db_path"])
        try:
            # Contract reading -- same pinned primary as R1/`kmt r2`.
            apply_and_log(conn, window="r2", dollar_volume_by_ticker=None)
            r2_scope = db.in_scope_tickers(conn, "r2")
            # series_ticker, not category: data/fees.yaml scopes the maker fee to
            # an enumerated list of SERIES, and category never determined a Kalshi
            # fee at all.
            resolutions, series_by_ticker = {}, {}
            if r2_scope:
                # TEMP-table join rather than an IN list -- r2_scope is 392,597
                # tickers and SQLite binds at most 32,766 variables per statement.
                with db.ticker_scope(conn, r2_scope) as scope:
                    for row in conn.execute(
                        f"SELECT m.ticker, m.result, m.series_ticker FROM markets m "
                        f"JOIN {scope} s ON s.ticker = m.ticker"
                    ).fetchall():
                        resolutions[row["ticker"]] = row["result"]
                        series_by_ticker[row["ticker"]] = row["series_ticker"]
        finally:
            conn.close()

        # A FRESH stream per call, deliberately, rather than one iterator reused.
        # The ribbon below re-runs this across an 11-point fee grid, and an
        # exhausted generator would hand every sweep after the first an empty tape
        # and a silently wrong ribbon. The cost is one scan per grid point, which
        # is I/O on an otherwise idle machine; the alternative -- materialising the
        # tape once -- is exactly what killed Pass 2 on 2026-08-24.
        def _fills():
            return trade_store.iter_fills(tickers=r2_scope, columns=MAKER_MARGIN_COLUMNS)

        maker_margin = compute_maker_margin_ge_50c(
            _fills(), resolutions, series_by_ticker, fee_schedule, r2_scope
        )

        ribbon = None
        sourced_rate = _sourced_maker_rate(fee_schedule)
        if sourced_rate is not None and maker_margin.n_maker_b > 0 and maker_margin.n_taker_b > 0:
            def _margin_fn(rate: float) -> float:
                synthetic = _maker_rate_schedule(fee_schedule, rate)
                swept = compute_maker_margin_ge_50c(
                    _fills(), resolutions, series_by_ticker, synthetic, r2_scope
                )
                return swept.layer_b if swept.layer_b is not None else 0.0

            ribbon = compute_ribbon(_margin_fn, default_fee_grid(sourced_rate))

        # Persist immediately, before the determination: these two objects cost
        # nineteen hours and nothing downstream should be able to lose them.
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(
            json.dumps(
                {"maker_margin": asdict(maker_margin),
                 "ribbon": asdict(ribbon) if ribbon else None},
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )

    # The fee arm reads off the DiD, in BOTH fits (analysis_plan.md Addendum 3).
    # Both come straight out of the locked artifact, so the escalation
    # determination is reproducible from it without recomputing anything.
    import math as _math

    def _did_estimate(fit: dict | None) -> DeltaBarEstimate | None:
        """None means NOT IDENTIFIED, which Addendum 3 forbids reading as a
        null. A fit with a non-finite bound is treated the same way: an
        interval that is not a real interval cannot reject anything."""
        if not fit:
            return None
        d, lo, hi = fit.get("delta_did"), fit.get("delta_did_ci_lo"), fit.get("delta_did_ci_hi")
        if any(v is None or not _math.isfinite(v) for v in (d, lo, hi)):
            return None
        return DeltaBarEstimate(delta_bar=d, ci_lo=lo, ci_hi=hi)

    did_block = r2_report.get("maker_fee_did") or {}
    did_fee_fits = {name: _did_estimate(did_block.get(name)) for name in ("twfe", "clean_controls")}

    escalation = determine_escalation(
        delta_bar_fee=delta_bar_fee, delta_bar_pub=delta_bar_pub,
        maker_margin_layer_a=maker_margin.layer_a, maker_margin_layer_c=maker_margin.layer_c,
        ribbon=ribbon, did_fee_fits=did_fee_fits,
    )
    return {
        "r2_report": r2_report, "maker_margin": maker_margin, "ribbon": ribbon, "escalation": escalation,
    }


@app.command()
def escalate() -> None:
    """S5 escalation determination: does R2 (plus the maker >=50c margin's
    fee-sensitivity ribbon) trigger escalation from a replication note to
    a standalone short paper? Refuses to run without R2's locked verdict
    artifact (same dependency `kmt r2` writes for `kmt r3-check`)."""
    from dataclasses import asdict

    config = load_config()
    try:
        ctx = _compute_escalation(config)
    except FileNotFoundError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None

    result = {
        "maker_margin": asdict(ctx["maker_margin"]),
        "ribbon": asdict(ctx["ribbon"]) if ctx["ribbon"] is not None else None,
        "escalation": asdict(ctx["escalation"]),
    }
    typer.echo(json.dumps(result, indent=2, default=str))


@app.command(name="report")
def final_report() -> None:
    """Assembles the final note-format (or standalone-short-paper, if
    escalated) draft, pulling together R1, R2, the maker-margin ribbon,
    the Polymarket control venue (if its bootstrap files have been
    downloaded), and the S5 escalation determination. Writes
    reports/final/draft.md."""
    from kalshi_mt.control.polymarket import (
        CAVEATS,
        COVERAGE_GAP_STATEMENT,
        build_polymarket_panel,
        load_category_rules,
        monthly_psi_path,
    )
    from kalshi_mt.report.final import build_final_report_markdown, write_final_report
    from kalshi_mt.util import PROJECT_ROOT

    config = load_config()
    try:
        ctx = _compute_escalation(config)
    except FileNotFoundError as exc:
        typer.secho(str(exc), fg=typer.colors.RED, err=True)
        raise typer.Exit(code=1) from None

    bootstrap_dir = PROJECT_ROOT / "data" / "bootstrap"
    quant_path, markets_path = bootstrap_dir / "quant.parquet", bootstrap_dir / "markets.parquet"
    control_monthly_psi = None
    if quant_path.exists() and markets_path.exists():
        # The strata come from the versioned text rules; without them every
        # control row is category=None and S2.4's by-category breakdown is
        # empty (which is what happened until 2026-07-28).
        panel = build_polymarket_panel(
            quant_path, markets_path, category_rules=load_category_rules()
        )
        control_monthly_psi = [
            {"month": r.month, "result": None if r.result is None else {
                "psi": r.result.psi, "n": r.result.n, "n_clusters": r.result.n_clusters,
            }}
            for r in monthly_psi_path(panel)
        ]

    divergence_log_path = PROJECT_ROOT / "reports" / "r1" / "divergence_log.md"

    markdown = build_final_report_markdown(
        r2_report=ctx["r2_report"], escalation=ctx["escalation"],
        maker_margin=ctx["maker_margin"], ribbon=ctx["ribbon"],
        control_monthly_psi=control_monthly_psi, control_caveats=CAVEATS,
        control_coverage_gap_statement=COVERAGE_GAP_STATEMENT,
        r1_divergence_log_path=str(divergence_log_path) if divergence_log_path.exists() else None,
    )
    path = write_final_report(markdown, PROJECT_ROOT / "reports" / "final" / "draft.md")
    typer.secho(f"Final report draft written to {path}", fg=typer.colors.GREEN)
    typer.echo(json.dumps({"venue": ctx["escalation"].escalate and "standalone_short_paper" or "replication_note",
                            "escalate": ctx["escalation"].escalate, "path": str(path)}, indent=2))
