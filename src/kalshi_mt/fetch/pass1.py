"""Pass 1: whole-universe metadata discovery + boundary-tick price panel +
closing quotes for the spread filter (spec S3).

Two independently resumable discovery sub-phases, since they need
fundamentally different Kalshi endpoint families (Phase 1's own empirical
findings -- see api/kalshi.py's module docstring):

  - Live sweep (2023-01-01..R2 end): cheap, cursor-paginated
    min_close_ts/max_close_ts range queries against /markets. No `status`
    filter -- proven unreliable this far back (a real live probe found
    status="settled" returns nothing at all for a 2023 window, while the
    same window with no status filter returns real markets). Every market
    in range is upserted regardless of its live status/result fields, which
    are frequently stale for older markets; Phase 3's construction re-derives
    "did this actually resolve" from trade/settlement evidence, not from
    trusting these fields.
  - Historical series scan (2021-01-01..R2_END): live /markets returns
    NOTHING for the early era and, as measured 2026-07-25, very little for
    anything not in its recent trailing window either -- so this scan spans
    the WHOLE R1+R2 range rather than stopping at 2023-01-01 as it first
    did. That original cap, plus the false assumption that the live sweep
    covered everything after it, is what produced the 2023-2025 coverage
    hole (59 R1 markets closing in 2023, 561 in 2024, against 13,302 for
    2022); discover_historical_series' own docstring has the measurements.
    The only path for that era is paging every series' /historical/markets
    by cursor until reaching the window or exhausting that series' history,
    checkpointed per series in series_scan_state so a multi-hour scan
    (spec's own "1-3 day polite fetch" estimate, run across the full
    ~12k-series universe) survives a restart and can be driven forward a
    bounded amount per invocation. It overlaps the live sweep on purpose;
    upsert_market dedups on ticker, and two independent paths covering the
    same range is what would have caught the hole sooner.

Then, for every discovered market: resolve series_ticker (GET
/events/{event_ticker} -- not a Market field) and category, fetch the ~11
boundary-tick price-panel rows, and fetch one closing candlestick for the
spread filter.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from kalshi_mt.api.kalshi import KalshiClient, KalshiMarket, KalshiTrade
from kalshi_mt.store import db
from kalshi_mt.util import (
    epoch_to_et,
    et_day_start,
    et_to_epoch,
    iso_to_epoch,
    shift_et_calendar_days,
)

log = logging.getLogger(__name__)

R1_START = int(datetime(2021, 1, 1, tzinfo=UTC).timestamp())
R1_END = int(datetime(2025, 4, 30, 23, 59, 59, tzinfo=UTC).timestamp())
R2_START = int(datetime(2025, 5, 1, tzinfo=UTC).timestamp())
R2_END = int(datetime(2026, 6, 30, 23, 59, 59, tzinfo=UTC).timestamp())
# Empirically confirmed during Phase 1: live /markets returns real metadata
# for close_time ranges from roughly 2023 onward, but genuinely nothing for
# 2021-2022 -- a different (longer) retention window than /historical/cutoff's
# own ~60-day live/historical trades-and-candlesticks boundary.
LIVE_METADATA_FLOOR = int(datetime(2023, 1, 1, tzinfo=UTC).timestamp())

# Analysis-window name -> markets column. A fixed map, so a window name can
# only ever become one of these two literals in SQL (the column can't be a
# bound parameter), matching r1/filters.py's own window_column dispatch.
ANALYSIS_WINDOW_COLUMNS = {"r1": "in_r1_window", "r2": "in_r2_window"}

PANEL_LOOKBACK_DAYS = 10


def _window_flags(close_time_epoch: int | None) -> tuple[int, int]:
    if close_time_epoch is None:
        return 0, 0
    in_r1 = int(R1_START <= close_time_epoch <= R1_END)
    in_r2 = int(R2_START <= close_time_epoch <= R2_END)
    return in_r1, in_r2


def _market_to_row(
    m: KalshiMarket, source: str,
    series_ticker: str | None = None, category: str | None = None,
) -> dict[str, Any]:
    """`series_ticker`/`category` are optional because only ONE discovery path
    can know them: the historical series scan pages a specific series, so its
    loop key IS the series of every market on those pages, and the /series
    catalog it already holds gives that series' category. The live sweep
    genuinely cannot -- series_ticker is not a Market field (see the module
    docstring), which is why resolve_series_and_category exists at all.
    Passing them here makes resolution FREE for historically-discovered
    markets instead of costing one GET /events per event; upsert_market
    COALESCEs, so leaving them None never erases an already-resolved value."""
    close_epoch = iso_to_epoch(m.close_time)
    open_epoch = iso_to_epoch(m.open_time)
    in_r1, in_r2 = _window_flags(close_epoch)
    return {
        "ticker": m.ticker, "event_ticker": m.event_ticker, "status": m.status,
        "series_ticker": series_ticker, "category": category,
        "result": m.result, "open_time": m.open_time, "open_time_epoch": open_epoch,
        "close_time": m.close_time, "close_time_epoch": close_epoch,
        "settlement_ts": m.settlement_ts, "volume_fp": m.volume_fp, "metadata_source": source,
        "in_r1_window": in_r1, "in_r2_window": in_r2,
        # Captured 2026-07-21 as groundwork; consumed since 2026-07-28.
        # settlement_value_dollars drives r1/filters.py's
        # settlement-consistency check, last_price_dollars backs its
        # tape-validation statistic. Capturing them during discovery is what
        # made both possible without re-fetching metadata for the whole
        # universe once the pin was finally made.
        "settlement_value_dollars": m.settlement_value_dollars,
        "last_price_dollars": m.last_price_dollars,
    }


# -- Sub-phase A: live sweep (2023-01-01 .. R2_END) --------------------------

async def discover_live_window(
    client: KalshiClient, conn, start_ts: int = LIVE_METADATA_FLOOR, end_ts: int = R2_END,
    page_limit: int = 1000, max_pages: int | None = None, n_concurrent_windows: int = 8,
) -> dict[str, int]:
    """Splits [start_ts, end_ts] into `n_concurrent_windows` non-overlapping
    sub-windows and walks each sub-window's cursor pagination CONCURRENTLY
    (all sharing the same TokenBucket via `client`, so the aggregate
    request rate still respects the configured ceiling -- concurrency
    changes how many requests are IN FLIGHT, not the per-second budget).

    This exists because of a real, measured bottleneck: a single sequential
    cursor walk is LATENCY-bound, not rate-bound -- confirmed live,
    2026-07-16, a run configured for 10 req/s sustained only ~3 req/s
    because each request waited for the previous one's full round trip
    before the next could even be attempted. Cursor pagination is
    inherently sequential WITHIN one sub-window (page N+1 needs page N's
    cursor), so the concurrency here comes from running several
    INDEPENDENT sub-window walks side by side, not from parallelizing pages
    within a single walk.

    Each sub-window's cursor is checkpointed in live_window_scan_state
    (store/db.py) after every page, keyed on its own (window_start,
    window_end) -- deterministic across runs as long as start_ts/end_ts/
    n_concurrent_windows don't change. A restarted process resumes each
    sub-window from its last-saved cursor instead of re-walking from page
    1, and a sub-window already marked 'done' is skipped entirely. Without
    this, a real multi-hour run confirmed the failure mode directly: a
    process restart (e.g. to pick up a code change) re-walked the densest
    sub-window (the sports-heavy tail near R2_END) from scratch every time,
    making zero net forward progress across several restarts."""
    log_id = db.log_fetch(conn, "pass1_discovery_live", f"{start_ts}-{end_ts}", "in_progress")

    span = end_ts - start_ts
    step = max(span // n_concurrent_windows, 1)
    boundaries = [start_ts + i * step for i in range(n_concurrent_windows)] + [end_ts]
    sub_windows = [(boundaries[i], boundaries[i + 1]) for i in range(n_concurrent_windows)]

    async def _walk_subwindow(sub_start: int, sub_end: int) -> tuple[int, int]:
        checkpoint = db.get_live_window_scan_state(conn, sub_start, sub_end)
        if checkpoint is not None and checkpoint["status"] == "done":
            return 0, 0  # already fully walked in a prior run -- nothing new this call

        cursor: str | None = checkpoint["cursor"] if checkpoint is not None else None
        fetched_before = checkpoint["fetched_count"] if checkpoint is not None else 0
        pages_before = checkpoint["pages_fetched"] if checkpoint is not None else 0
        fetched = 0
        pages = 0
        while True:
            markets, next_cursor = await client.list_markets(
                min_close_ts=sub_start, max_close_ts=sub_end, cursor=cursor, limit=page_limit
            )
            for m in markets:
                db.upsert_market(conn, _market_to_row(m, "live"))
            fetched += len(markets)
            pages += 1
            done = not next_cursor or not markets
            cursor = next_cursor
            db.upsert_live_window_scan_state(conn, {
                "window_start": sub_start, "window_end": sub_end,
                "status": "done" if done else "in_progress",
                "cursor": cursor,
                "fetched_count": fetched_before + fetched,
                "pages_fetched": pages_before + pages,
            })
            conn.commit()
            if done:
                break
            if max_pages is not None and pages >= max_pages:
                break
        return fetched, pages

    results = await asyncio.gather(*[_walk_subwindow(s, e) for s, e in sub_windows])
    fetched = sum(r[0] for r in results)
    pages = sum(r[1] for r in results)

    db.finish_fetch_log(
        conn, log_id, "done", fetched_count=fetched,
        notes=f"{pages} pages across {n_concurrent_windows} concurrent sub-windows this call",
    )
    conn.commit()
    return {"fetched": fetched, "pages": pages}


# -- Sub-phase B: historical series scan (2021-01-01 .. 2023-01-01) ---------

async def discover_historical_series(
    client: KalshiClient, conn, start_ts: int = R1_START, end_ts: int = R2_END,
    max_series_this_run: int | None = None, max_pages_per_series: int = 20,
    max_concurrent_series: int = 20, series_catalog: list[Any] | None = None,
) -> dict[str, int]:
    """Different series are fully independent -- their cursor walks run
    CONCURRENTLY, bounded by `max_concurrent_series` (same latency-bound
    finding as discover_live_window and resolve_series_and_category: a
    sequential per-series loop sat well below the configured rate
    ceiling). Pagination WITHIN one series stays sequential (page N+1
    needs page N's cursor).

    `end_ts` spans the WHOLE R1+R2 window (through R2_END), not just up to
    LIVE_METADATA_FLOOR as it originally did. That original split assumed the
    live /markets sweep fully covered 2023-01-01 onward, so this scan only
    had to serve 2021-2022. Measured 2026-07-25, that assumption is FALSE:
    the live endpoint does not serve long-closed markets, and its own
    completed sub-window checkpoints prove it -- 2023-01-01..2023-06-09
    returned 0 markets, 2023-06-09..2023-11-16 returned 14,
    2024-04-23..2024-09-30 returned 29, and 2025-08-15..2026-01-22 returned
    375, versus 9.48M for 2026-01-22..2026-06-30. It only reliably serves a
    recent trailing window. The result was a coverage hole from ~2023 through
    ~2025 that left just 59 R1 markets closing in 2023 and 561 in 2024
    (against 13,302 for 2022, via this scan) -- fatal for BDW's by-year psi
    (their Table 9 reports 2023 and 2024) and for R2, whose fee (2025-05-01)
    and publication (2025-09-08) boundaries both sit inside the hole.

    /historical/markets DOES serve that era (probe: KXHIGHNY page 1 returned
    864 markets closing in 2026 and 136 in 2025), and because pages come
    newest-first this scan was ALREADY paging through them and discarding
    every one via the window guard below -- so widening the window recovers
    the data at nearly no extra API cost. Overlap with the live sweep is
    harmless: upsert_market dedups on ticker.

    A series whose checkpoint was written under a NARROWER end_ts is
    re-scanned from page 1 rather than trusted as 'done', since its earlier
    pages dropped in-window markets. `scan_window_end` on series_scan_state
    is what makes that detectable instead of silent -- the whole point being
    that a stale 'done' is exactly how the original hole stayed invisible."""
    # `series_catalog` lets run_pass1 fetch the ~12k-row /series catalog ONCE
    # and share it with resolve_series_and_category, which needs the same
    # data; each fetching its own was one redundant full-catalog GET per
    # invocation. Standalone callers (tests, a targeted re-scan) still just
    # get it themselves.
    all_series = (
        series_catalog if series_catalog is not None
        else await client.list_series(limit=100_000)  # /series has no real limit param; client-truncates
    )
    # This scan pages ONE series at a time, so its loop key is the series of
    # every market it finds -- persisting that (plus the catalog's category)
    # makes resolve_series_and_category's GET /events unnecessary for
    # historically-discovered markets, which after the window widening is most
    # of the universe.
    category_by_series = {s.ticker: s.category for s in all_series}
    for s in all_series:
        if db.get_series_scan_state(conn, s.ticker) is None:
            db.upsert_series_scan_state(conn, {
                "series_ticker": s.ticker, "status": "pending", "pages_fetched": 0,
                "markets_found_in_window": 0, "reached_before_window": 0, "last_cursor": None,
                "scan_window_end": None,
            })
    conn.commit()

    # Re-open any series last scanned under a narrower window (or before
    # scan_window_end existed at all -- NULL). Reset to page 1: the discarded
    # markets are only recoverable by re-walking the cursor from the start,
    # and a resumed mid-history cursor would silently keep the gap.
    reopened = conn.execute(
        "UPDATE series_scan_state SET status='pending', last_cursor=NULL, pages_fetched=0, "
        "markets_found_in_window=0, reached_before_window=0 "
        "WHERE (scan_window_end IS NULL OR scan_window_end < ?)",
        (end_ts,),
    ).rowcount
    conn.commit()
    if reopened:
        log.info(
            "re-opened %d series whose checkpoint predates the current scan window end %d",
            reopened, end_ts,
        )

    pending = conn.execute(
        "SELECT series_ticker, last_cursor, pages_fetched, markets_found_in_window "
        "FROM series_scan_state "
        "WHERE status IN ('pending', 'in_progress') ORDER BY series_ticker"
    ).fetchall()
    if max_series_this_run is not None:
        pending = pending[:max_series_this_run]

    semaphore = asyncio.Semaphore(max_concurrent_series)

    async def _scan_series(row) -> int:
        async with semaphore:
            ticker, cursor, pages_so_far = row["series_ticker"], row["last_cursor"], row["pages_fetched"]
            # Seeded from the checkpoint like pages_so_far, not reset to 0:
            # markets_found_in_window is written back on every checkpoint, so
            # resetting made a series resumed across runs report only its LAST
            # segment's finds while pages_fetched kept accumulating -- two
            # counters in the same row disagreeing about the same scan.
            found_in_series = row["markets_found_in_window"] or 0
            reached_before = False
            # Checkpointed every page (not just once at the end) -- a
            # request failure partway through a 20-page scan used to lose
            # every page already fetched for this series, since the only
            # upsert_series_scan_state call was after the loop. Confirmed
            # live: with 20 concurrent series and a real, persistent 429
            # rate, this was the actual bottleneck behind repeated
            # kmt fetch pass1 restarts making only slow progress -- most of
            # each restart's in-flight work for THIS series was thrown away
            # on any single failed request, not just the failing one.
            for _ in range(max_pages_per_series):
                markets, next_cursor = await client.list_historical_markets(
                    series_ticker=ticker, cursor=cursor, limit=1000
                )
                pages_so_far += 1
                stop = not markets
                if markets:
                    close_epochs: list[int] = []
                    for m in markets:
                        row_dict = _market_to_row(
                            m, "historical",
                            series_ticker=ticker, category=category_by_series.get(ticker),
                        )
                        ce = row_dict["close_time_epoch"]
                        if ce is not None:
                            close_epochs.append(ce)
                        # Inclusive on both ends, matching _window_flags'
                        # own R1_START<=ce<=R1_END / R2_START<=ce<=R2_END --
                        # an exclusive upper bound would drop a market
                        # closing exactly at R2_END (23:59:59) that the
                        # window flags themselves count as in-window.
                        if ce is not None and start_ts <= ce <= end_ts:
                            db.upsert_market(conn, row_dict)
                            found_in_series += 1
                    # Pages are reverse-chronological (empirically confirmed,
                    # Phase 1): once a page's newest row already predates the
                    # window, every later page for this series is even older.
                    if close_epochs and max(close_epochs) < start_ts:
                        reached_before = True
                        stop = True
                    elif not next_cursor:
                        stop = True
                    else:
                        cursor = next_cursor
                db.upsert_series_scan_state(conn, {
                    "series_ticker": ticker, "status": "done" if stop else "in_progress",
                    "pages_fetched": pages_so_far, "markets_found_in_window": found_in_series,
                    "reached_before_window": int(reached_before), "last_cursor": cursor,
                    # Stamped on EVERY checkpoint, not just the terminal one:
                    # the pages fetched so far were filtered against this
                    # end_ts, so a series left 'in_progress' must resume
                    # rather than be re-opened from page 1 next run.
                    "scan_window_end": end_ts,
                })
                conn.commit()
                if stop:
                    return found_in_series
            # max_pages_per_series exhausted without a natural stop -- the
            # last iteration's checkpoint already left status='in_progress',
            # resuming from `cursor` on a later call.
            return found_in_series

    # return_exceptions=True is the actual fix for the observed failure
    # mode: without it, ANY one series hitting an exhausted-retry error
    # (429/504/etc, all real and observed live) cancels every other
    # in-flight sibling task in this asyncio.gather batch too -- losing
    # their progress even though each already checkpoints per-page above,
    # since a cancelled coroutine never reaches its own next checkpoint
    # write. With this, one bad series degrades to "stays in_progress,
    # retried on the next call" instead of taking the whole batch down.
    results = await asyncio.gather(*[_scan_series(row) for row in pending], return_exceptions=True)
    series_processed = len(pending)
    # Log WHICH series failed, not just how many. Confirmed live 2026-07-25:
    # a full re-scan silently left 391 series 'pending' (each having raised on
    # its first page, before any checkpoint write), and the only trace was a
    # count in the returned stats -- the log itself was clean INFO throughout,
    # so nothing pointed at what to retry or investigate.
    series_failed = 0
    markets_found_total = 0
    for row, r in zip(pending, results, strict=True):
        if isinstance(r, BaseException):
            series_failed += 1
            log.warning("historical scan failed for series %s: %r", row["series_ticker"], r)
        else:
            markets_found_total += r

    remaining = conn.execute(
        "SELECT COUNT(*) FROM series_scan_state WHERE status IN ('pending', 'in_progress')"
    ).fetchone()[0]
    return {
        "series_processed_this_run": series_processed,
        "series_failed_this_run": series_failed,
        "markets_found_this_run": markets_found_total,
        "series_remaining": remaining,
    }


# -- Sub-phase C: series_ticker + category resolution ------------------------

def _scope_predicate(
    min_volume_fp: float | None, min_open_duration_s: float | None,
) -> tuple[str, list[Any]]:
    """The shared "$1k volume + >=24h open" scoping predicate for the two
    EXPENSIVE per-market Pass-1 phases (category resolution and the
    panel/quote fetch). Kept in ONE place so the two phases can never drift
    apart -- exactly the bug the 2026-07-21 pipeline audit found when only
    the panel/quote loop carried the 24h guard. Mirrors fetch/pass2.py's
    select_in_scope_tickers and r1/filters.py: volume_fp >= threshold, then
    both timestamps present and (close - open) >= threshold. A NULL
    open_time_epoch fails the guard and is skipped, matching pass2 -- the 24h
    check is unverifiable without an open time, so such a market is out of
    scope. Each filter is independently optional (pass None to disable, e.g.
    a verification run that wants every discovered market)."""
    sql = ""
    params: list[Any] = []
    if min_volume_fp is not None:
        sql += " AND volume_fp >= ?"
        params.append(min_volume_fp)
    if min_open_duration_s is not None:
        sql += " AND open_time_epoch IS NOT NULL AND (close_time_epoch - open_time_epoch) >= ?"
        params.append(min_open_duration_s)
    return sql, params


async def resolve_series_and_category(
    client: KalshiClient, conn, batch_size: int | None = 500,
    min_volume_fp: float | None = None, min_open_duration_s: float | None = None,
    max_concurrent: int = 20, series_catalog: list[Any] | None = None,
    max_spread: float | None = None,
) -> dict[str, int]:
    """`min_volume_fp` and `min_open_duration_s` restrict resolution to
    markets that could plausibly clear R1/R2's own $1k volume and >=24h open
    filters (fetch/pass2.py's MIN_VOLUME_FP / MIN_OPEN_SECONDS) -- a live
    sweep across the full R1+R2 window can discover many hundreds of
    thousands of markets (most of them thin, hourly-reset sports/crypto
    sub-markets that will never survive Phase 3's filters), and every
    resolution is one GET /events call. Filtering here, not just at Pass 2's
    in-scope selection, is what keeps a real collection run from spending
    days resolving series/category for markets no downstream phase will ever
    use. Both filters must be applied together for the same reason the
    panel/quote loop applies both: category is consumed only for in-scope
    markets, and every in-scope market must clear BOTH $1k volume and >=24h
    open, so scoping resolution to that set still resolves a strict superset
    of what R2's category-composition analysis needs. The 24h guard reads
    only discovery-metadata epochs, so it has no dependency on resolution
    having run.

    The GET /events calls for distinct event_tickers run CONCURRENTLY
    (bounded by `max_concurrent`, sharing the client's TokenBucket) -- one
    sequential await-per-call loop was confirmed live to be latency-bound
    well below the configured rate ceiling (fetch/pass1.py's
    discover_live_window docstring has the same finding). The dedup-by-
    event_ticker caching happens in a first pass (collect the unique set,
    resolve it concurrently) so no event is ever fetched twice even though
    many tickers can share one event_ticker."""
    all_series = (
        series_catalog if series_catalog is not None
        else await client.list_series(limit=100_000)
    )
    category_by_series = {s.ticker: s.category for s in all_series}

    scope_sql, scope_params = _scope_predicate(min_volume_fp, min_open_duration_s)
    # `max_spread` narrows resolution to markets whose closing quote ALREADY
    # clears the spread filter, i.e. the ones that can really reach the
    # analysis. Measured 2026-07-26: the volume+24h-scoped backlog was 475,845
    # markets across 264,596 distinct events (~9h of GET /events at 8 req/s),
    # while the subset that also clears spread<=20c was 41,962 markets across
    # just 12,429 events (~26 min) -- a 21x reduction for the same analytical
    # coverage, since category is only ever consumed for in-scope markets.
    #
    # OPT-IN, not the default: it makes resolution depend on quotes existing,
    # and run_pass1 resolves BEFORE its panel/quote phase, so on a fresh
    # universe a spread-scoped resolve would find nothing on the first
    # invocation. Fine for a targeted catch-up run (where quotes are already
    # collected), wrong as a pipeline default.
    join_sql = ""
    if max_spread is not None:
        join_sql = " JOIN quotes q ON q.ticker = markets.ticker"
        scope_sql += " AND q.spread IS NOT NULL AND q.spread <= ?"
        scope_params = [*scope_params, max_spread]
    query = (
        "SELECT markets.ticker AS ticker, markets.event_ticker AS event_ticker "
        "FROM markets" + join_sql + " "
        "WHERE markets.series_ticker IS NULL AND markets.event_ticker IS NOT NULL "
        "AND COALESCE(markets.series_resolution_terminal, 0) = 0" + scope_sql
    )
    rows = conn.execute(query, scope_params).fetchall()
    if batch_size is not None:
        rows = rows[:batch_size]

    unique_events = list({row["event_ticker"] for row in rows})
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _fetch_event(event_ticker: str) -> tuple[str, str | None, bool]:
        """Third element separates the two ways this can yield no series:
        `answered=True` means /events really returned this event and it simply
        has no series_ticker (terminal -- retrying can only get the same
        answer), while `answered=False` means the lookup itself failed
        (client.get_event swallows request errors into None), which must stay
        retryable. Collapsing them is what made resolution re-issue the same
        doomed GET /events every run forever."""
        async with semaphore:
            event = await client.get_event(event_ticker)
            if event is None:
                return event_ticker, None, False
            return event_ticker, event.series_ticker, True

    resolved_events = await asyncio.gather(*[_fetch_event(e) for e in unique_events])
    event_cache: dict[str, str | None] = {e: s for e, s, _ in resolved_events}
    event_answered: dict[str, bool] = {e: a for e, _, a in resolved_events}

    resolved = 0
    terminal = 0
    for row in rows:
        ticker, event_ticker = row["ticker"], row["event_ticker"]
        series_ticker = event_cache.get(event_ticker)
        if series_ticker is None:
            if event_answered.get(event_ticker):
                conn.execute(
                    "UPDATE markets SET series_resolution_terminal = 1 WHERE ticker = ?",
                    (ticker,),
                )
                terminal += 1
            continue
        conn.execute(
            "UPDATE markets SET series_ticker = ?, category = ? WHERE ticker = ?",
            (series_ticker, category_by_series.get(series_ticker), ticker),
        )
        resolved += 1
    conn.commit()
    # Same join/scope as the selection above -- scope_sql may reference q.spread.
    remaining_query = (
        "SELECT COUNT(*) FROM markets" + join_sql + " "
        "WHERE markets.series_ticker IS NULL AND markets.event_ticker IS NOT NULL "
        "AND COALESCE(markets.series_resolution_terminal, 0) = 0" + scope_sql
    )
    remaining = conn.execute(remaining_query, scope_params).fetchone()[0]
    return {
        "resolved_this_run": resolved,
        "terminal_no_series_this_run": terminal,
        "remaining": remaining,
    }


# -- Sub-phase D: boundary-tick price panel -----------------------------------

async def _last_trade_before(
    client: KalshiClient, ticker: str, max_ts: int, prefer: str = "live",
) -> tuple[KalshiTrade, str] | tuple[None, None]:
    """The single most recent trade at/before max_ts, trying the `prefer`
    endpoint family first and the other as fallback. Assumes (confirmed
    empirically, Phase 1) both /markets/trades and /historical/trades return
    results newest-first by default, so limit=1 with max_ts set gives exactly
    this trade directly -- no need to fetch a whole day's tape just to find
    its last row.

    `prefer` exists because the live /markets/trades endpoint only serves the
    most recent ~60 days; for a market whose trades predate that window every
    live probe returns empty and pays a wasted round-trip before the
    historical fallback. fetch_price_panel therefore determines the family once
    on the closing-day trade and passes it as `prefer` for all 10 lookback
    days. Same family-once idea pass2.fetch_full_tape_for_market already uses.

    MEASURED 2026-07-30, correcting this docstring's earlier claim that a single
    market's 10-day panel "never" straddles the cutoff: **1,922 of 171,548
    markets (1.1%) have panel rows from BOTH families**, so within one market a
    family that answers for one day returns nothing for another. Those are the
    markets whose 10-day window brackets the retention boundary. THE FALLBACK IS
    WHAT MAKES THEM WHOLE -- it is not a rare-case nicety, and any future
    optimization that caches one family per market must keep it or silently
    lose ~1% of panel rows.

    The family is otherwise near-deterministic in market age, which is why the
    once-per-market choice is cheap and safe: across every month closing
    2025-12 or earlier, live answered ZERO times in 141,000+ panel rows, while
    2026-06 is 99.9% live. An available follow-up (not taken while a multi-day
    fetch is in flight) is to seed `prefer` from the close date instead of
    paying a live probe that always misses for old markets -- worth ~1 request
    per market."""
    families = ("live", "historical") if prefer == "live" else ("historical", "live")
    for family in families:
        fetch = client.get_trades if family == "live" else client.get_historical_trades
        trades, _ = await fetch(ticker=ticker, max_ts=max_ts, limit=1)
        if trades:
            return trades[0], family
    return None, None


async def fetch_price_panel(
    client: KalshiClient, conn, ticker: str, close_time_epoch: int,
) -> dict[str, int]:
    """spec S1: "last trade on closing day plus last trade before the same
    time on each of up to 10 prior days." lookback_day=0's own trade
    timestamp is the reference clock time for every subsequent day (not
    close_time itself) -- construction pin from the plan: skip a lookback
    day with no trade STRICTLY within that ET calendar day, never backfill
    from an earlier day just because a bracketed query happened to return
    one.

    That same "closing day" = calendar ET date of the close timestamp
    (construction pin, spec S3) applies to day 0 too: a trade found via
    max_ts=close_time_epoch is not automatically ON the closing ET day --
    for a market with no trade on that day, `_last_trade_before` happily
    returns an earlier one. Days 1-10 already guard against exactly this
    (trade_epoch < day_start_epoch => skip); day 0 must use the SAME guard
    against close_time_epoch's own ET day, not skip it just because it's the
    anchor. Skipping the whole panel (not just day 0) on failure is correct:
    every lookback day is walked back from t0, so an invalid t0 would
    silently re-anchor the entire 10-day window onto the wrong calendar
    (2026-07-21 audit)."""
    trade0, source0 = await _last_trade_before(client, ticker, close_time_epoch)
    if trade0 is None:
        return {"rows_written": 0}
    t0_epoch = iso_to_epoch(trade0.created_time)
    if t0_epoch is None:
        return {"rows_written": 0}
    close_day_start_epoch = et_to_epoch(et_day_start(epoch_to_et(close_time_epoch)))
    if t0_epoch < close_day_start_epoch:
        return {"rows_written": 0}  # no qualifying trade strictly within the closing ET day -- skip, no backfill
    db.upsert_price_panel_row(conn, {
        "ticker": ticker, "lookback_day": 0, "trade_id": trade0.trade_id,
        "yes_price_dollars": trade0.yes_price_dollars, "created_time": trade0.created_time,
        "source": source0,
    })
    written = 1
    t0_et = epoch_to_et(t0_epoch)

    for day in range(1, PANEL_LOOKBACK_DAYS + 1):
        ref_et = shift_et_calendar_days(t0_et, day)
        ref_epoch = et_to_epoch(ref_et)
        day_start_epoch = et_to_epoch(et_day_start(ref_et))
        # Closing-day trade already revealed which family answers for this
        # market; try it first, the other stays a fallback for the rare
        # ~60-day live/historical straddle.
        trade, source = await _last_trade_before(client, ticker, ref_epoch, prefer=source0)
        if trade is None:
            continue
        trade_epoch = iso_to_epoch(trade.created_time)
        if trade_epoch is None or trade_epoch < day_start_epoch:
            continue  # no qualifying trade strictly within this ET calendar day -- skip, no backfill
        db.upsert_price_panel_row(conn, {
            "ticker": ticker, "lookback_day": day, "trade_id": trade.trade_id,
            "yes_price_dollars": trade.yes_price_dollars, "created_time": trade.created_time,
            "source": source,
        })
        written += 1
    conn.commit()
    return {"rows_written": written}


# -- Sub-phase E: closing quote for the spread filter -------------------------

async def fetch_closing_quote(
    client: KalshiClient, conn, ticker: str, event_ticker: str | None, close_time_epoch: int,
    series_ticker: str | None = None,
) -> dict[str, bool]:
    """One closing candlestick per market -- the input to spec S1's final
    spread<=20c filter (Phase 3). Live then historical fallback.

    The live-candlestick endpoint is keyed on series_ticker. When the caller
    already has it (resolve_series_and_category persists markets.series_ticker
    before this phase runs), it is passed in and the redundant GET
    /events/{event_ticker} round-trip is skipped -- that lookup is only a
    fallback for markets not yet resolved (series_ticker still NULL).

    ALWAYS writes a `quotes` row, even when neither endpoint family has a
    quote -- previously this returned early and wrote nothing, which made
    "Pass 1 hasn't reached this ticker yet" and "Pass 1 tried and Kalshi
    genuinely has no bid/ask history here" both look like an absent row,
    indistinguishable to r1/filters.py. Step Zero's Check 5 already found
    the second case is real for most of 2023/2024/2025-jan-apr -- the R1
    count-reconciliation gate needs "a row exists with spread IS NULL"
    (attempted, not found) as a distinct, queryable state from "no row at
    all" (not yet attempted) to separate a structural coverage gap from an
    incomplete fetch in its own delta reporting (r1/reconcile.py's
    coverage_gap_breakdown)."""
    start_ts, end_ts = close_time_epoch - 86_400, close_time_epoch
    candles = []
    source = "live"
    resolved_series = series_ticker
    if resolved_series is None and event_ticker:
        event = await client.get_event(event_ticker)
        resolved_series = event.series_ticker if event else None
    if resolved_series:
        try:
            candles = await client.get_candlesticks(
                resolved_series, ticker, start_ts, end_ts, period_interval=60
            )
        except Exception:
            candles = []
    if not candles:
        source = "historical"
        try:
            candles = await client.get_historical_candlesticks(
                ticker, start_ts, end_ts, period_interval=60
            )
        except Exception:
            candles = []

    quoted = [c for c in candles if c.has_quote]
    if not quoted:
        db.upsert_quote(conn, {
            "ticker": ticker, "end_period_ts": None, "yes_bid_close": None,
            "yes_ask_close": None, "spread": None, "source": source,
        })
        conn.commit()
        return {"has_quote": False}
    last = max(quoted, key=lambda c: c.end_period_ts or 0)
    spread = None
    if last.yes_ask.close_dollars is not None and last.yes_bid.close_dollars is not None:
        spread = round(last.yes_ask.close_dollars - last.yes_bid.close_dollars, 4)
    db.upsert_quote(conn, {
        "ticker": ticker, "end_period_ts": last.end_period_ts,
        "yes_bid_close": last.yes_bid.close_dollars, "yes_ask_close": last.yes_ask.close_dollars,
        "spread": spread, "source": source,
    })
    conn.commit()
    return {"has_quote": True}


# -- Orchestration -------------------------------------------------------------

async def run_pass1(
    client: KalshiClient, conn,
    max_series_this_run: int | None = None,
    market_processing_limit: int | None = None,
    live_max_pages: int | None = None,
    series_resolution_batch_size: int | None = 500,
    min_volume_fp: float | None = 1000.0,
    min_open_duration_s: float | None = 86_400.0,
    panel_quote_window: str | None = None,
    panel_quote_close_from: int | None = None,
    panel_quote_close_to: int | None = None,
    panel_quote_concurrency: int = 20,
    resolve_max_spread: float | None = None,
    max_concurrent_series: int = 20,
) -> dict[str, Any]:
    """Discovery (live sweep + historical series scan) -> series/category
    resolution -> price-panel + closing-quote fetch for every discovered
    market missing them. Every sub-phase is independently resumable; pass
    small `max_series_this_run`/`market_processing_limit`/`live_max_pages`
    values to bound a single invocation (verification, a scheduled
    incremental run) rather than the full multi-hour sweep. The live sweep
    alone can touch HUNDREDS of thousands of markets across the full R1+R2
    window (confirmed live, 2026-07: 576k+ from the live sweep phase alone,
    well past the spec's own ~50-80k planning estimate) -- `live_max_pages`
    is what keeps a verification run from silently turning into a
    near-production one; omit it only when you actually intend the full
    sweep.

    `min_volume_fp` defaults to fetch/pass2.py's own $1k R1/R2 volume
    filter and restricts BOTH series/category resolution and the
    panel+quote fetch to markets that could plausibly clear it -- the
    great majority of a full live sweep is thin sports/crypto sub-markets
    that will never survive Phase 3's filters, and each is ~1-13 extra API
    calls (one /events lookup, up to 11 boundary-tick trade lookups, one
    candlestick lookup) if not filtered here. Metadata discovery itself
    (this function's first two sub-phases) is NEVER volume-filtered --
    every market's basic record lands in `markets` regardless, so
    universe_log/reconciliation coverage stays complete; only the
    EXPENSIVE per-market detail work is scoped down. Pass None to disable
    (process every discovered market) if a specific verification run
    genuinely needs that.

    `min_open_duration_s` (default 24h, mirroring fetch/pass2.py's
    MIN_OPEN_SECONDS) applies BDW's "market open >= 24 hours" construction
    filter (spec S1/S3: excludes the hourly-reset crypto/index series) to
    the same expensive panel+quote fetch, with the identical two-guard SQL
    pass2 uses (open_time_epoch IS NOT NULL AND close-open >= threshold).
    Confirmed live 2026-07-21: of ~2.56M markets clearing the $1k volume
    filter, only ~510k also clear the 24h filter -- the other ~2.05M are
    hourly-reset sub-markets (KXBTC-<hour>, index resets) that Pass 2's
    in-scope selection and r1/filters.py both discard anyway, so fetching
    their price panel and closing quote is pure wasted API budget. Like
    the volume filter this scopes ONLY the expensive per-market work, not
    metadata discovery, so reconciliation coverage against BDW's 46,282
    stays complete. Pass None to disable (e.g. to deliberately fetch a
    short-duration market for a verification run).

    `panel_quote_window` ('r1' | 'r2' | None) restricts ONLY the panel/quote
    phase to one analysis window. That phase walks a keyset cursor ordered by
    ticker, which interleaves both windows arbitrarily, so with a large R2
    backlog R1's own remainder only finishes after most of R2 -- while R1's
    count-reconciliation gate is the spec's hard prerequisite for every later
    phase (S1: count deltas before estimate deltas). Passing 'r1' fetches R1's
    remainder first. Discovery is deliberately NOT scoped by it and stays
    whole-universe, so reconciliation coverage is never narrowed. None keeps
    the original both-windows behaviour."""
    live_stats = await discover_live_window(client, conn, max_pages=live_max_pages)
    # One /series fetch shared by both phases that need it -- each fetching
    # its own was a redundant full ~12k-row catalog GET per invocation.
    series_catalog = await client.list_series(limit=100_000)
    hist_stats = await discover_historical_series(
        client, conn, max_series_this_run=max_series_this_run, series_catalog=series_catalog,
        max_concurrent_series=max_concurrent_series,
    )
    resolve_stats = await resolve_series_and_category(
        client, conn, batch_size=series_resolution_batch_size,
        min_volume_fp=min_volume_fp, min_open_duration_s=min_open_duration_s,
        series_catalog=series_catalog, max_spread=resolve_max_spread,
    )

    scope_sql, extra_params = _scope_predicate(min_volume_fp, min_open_duration_s)
    if panel_quote_window is not None:
        # Column name, not a bound parameter -- validated against a fixed map
        # so it can never carry caller-supplied SQL.
        scope_sql += f" AND {ANALYSIS_WINDOW_COLUMNS[panel_quote_window]} = 1"
    # Close-time range, for prioritising the months an estimate actually needs.
    # Confirmed live 2026-07-28: R2's full panel/quote backlog is ~751k markets
    # (~weeks), but delta_fee and delta_pub are only identified by the months
    # BRACKETING their boundaries -- 2025-05..2025-12 is ~104k markets, and
    # without those months no delta exists at all no matter how much of 2026 is
    # collected. Ordering by ticker interleaves months arbitrarily, so without
    # this the boundary months arrive last.
    if panel_quote_close_from is not None:
        scope_sql += " AND close_time_epoch >= ?"
        extra_params.append(panel_quote_close_from)
    if panel_quote_close_to is not None:
        scope_sql += " AND close_time_epoch <= ?"
        extra_params.append(panel_quote_close_to)
    base_query = (
        "SELECT ticker, event_ticker, series_ticker, close_time_epoch FROM markets "
        "WHERE close_time_epoch IS NOT NULL "
        "AND ticker NOT IN (SELECT ticker FROM quotes)" + scope_sql
    )

    # Concurrent, bounded panel+quote fetch -- each market's ~12-13 calls
    # (up to 11 boundary-tick trade lookups + one candlestick lookup) were
    # confirmed live to be latency-bound in a sequential loop, same finding
    # as discover_live_window's own docstring. Different markets are fully
    # independent, so this is safe to parallelize (unlike cursor pagination
    # within one market, which stays sequential inside fetch_price_panel).
    panel_quote_semaphore = asyncio.Semaphore(panel_quote_concurrency)

    async def _process_market(row) -> tuple[int, int]:
        async with panel_quote_semaphore:
            panel_result = await fetch_price_panel(client, conn, row["ticker"], row["close_time_epoch"])
            quote_result = await fetch_closing_quote(
                client, conn, row["ticker"], row["event_ticker"], row["close_time_epoch"],
                series_ticker=row["series_ticker"],
            )
            return panel_result["rows_written"], int(quote_result["has_quote"])

    # Chunked, keyset-paginated (ticker > last-seen, not OFFSET) rather than
    # one `fetchall()` -- confirmed live (2026-07-19): with the R1+R2
    # universe's real scale, ~2.5 MILLION markets pass this WHERE clause at
    # once, and one `fetchall()` plus one `asyncio.gather()` over all of
    # them (millions of Row objects and Task objects materialized before
    # any work starts) drove a single collector process to ~4.75GB RSS --
    # a real, confirmed risk on a machine that has already hit OOM twice
    # this project.
    #
    # The resume predicate is `NOT IN quotes`, NOT `NOT IN price_panel`:
    # fetch_closing_quote writes a `quotes` row LAST and ALWAYS (even when no
    # quote is found), whereas fetch_price_panel writes NOTHING for a
    # zero-trade market and commits in a SEPARATE transaction first. Keying
    # on price_panel therefore (a) permanently orphaned any market crashed
    # between the two commits -- it had price_panel rows but no quote, so
    # `NOT IN price_panel` excluded it forever and its closing quote was
    # never fetched (a real, silent coverage loss: 97 such orphans existed
    # by 2026-07-21) -- and (b) re-fetched every zero-trade market on every
    # restart (never in price_panel). Keying on `quotes`, the last+always
    # write, fixes both: an interrupted market still lacks its quote row so
    # it is re-selected, and upsert_price_panel_row is idempotent so the
    # panel replay is harmless. The keyset cursor on `ticker` (not the
    # subquery) is still what guarantees forward progress within a run: it
    # advances every chunk regardless of whether a row landed in quotes.
    _PANEL_QUOTE_CHUNK_SIZE = 2000
    panel_written = 0
    quotes_written = 0
    markets_processed = 0
    markets_failed = 0
    last_ticker = ""
    while market_processing_limit is None or markets_processed < market_processing_limit:
        budget = _PANEL_QUOTE_CHUNK_SIZE
        if market_processing_limit is not None:
            budget = min(budget, market_processing_limit - markets_processed)
        chunk_query = base_query + " AND ticker > ? ORDER BY ticker LIMIT ?"
        rows = conn.execute(chunk_query, [*extra_params, last_ticker, budget]).fetchall()
        if not rows:
            break
        # return_exceptions=True: an upstream 5xx that exhausts tenacity's
        # retries on ONE market must not crash the whole collector and lose
        # every other in-flight market's progress this chunk -- confirmed
        # live (2026-07-24), a single historical-trades 500 propagated
        # uncaught through gather and killed the process. A failed market
        # simply has no quotes row, so it stays selectable by the `NOT IN
        # quotes` resume predicate and is retried on the next run/chunk --
        # no special bookkeeping needed beyond logging it and not crediting
        # its (nonexistent) panel/quote counts. Same fix already applied to
        # discover_historical_series for the identical failure class.
        per_market_results = await asyncio.gather(
            *[_process_market(row) for row in rows], return_exceptions=True
        )
        for row, result in zip(rows, per_market_results, strict=True):
            if isinstance(result, BaseException):
                markets_failed += 1
                log.warning("panel/quote fetch failed for %s: %r", row["ticker"], result)
                continue
            panel_written += result[0]
            quotes_written += result[1]
        markets_processed += len(rows)
        last_ticker = rows[-1]["ticker"]

    return {
        "live_discovery": live_stats,
        "historical_discovery": hist_stats,
        "series_resolution": resolve_stats,
        "markets_processed": markets_processed,
        "markets_failed": markets_failed,
        "panel_rows_written": panel_written,
        "quotes_written": quotes_written,
    }
