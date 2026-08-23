"""Parquet trade-tape store, partitioned data/parquet/month=YYYY-MM/*.parquet.

Dedup key is trade_id -- appends drop rows whose key already exists in the
partition, restart-safe by construction (same anti-join pattern as the
sibling lab's store/snapshots.py, month granularity here per spec S3 rather
than that lab's daily partitions -- the two repos partition at different
grain by design, not by accident). This holds Pass 2's full trade tape,
which can run to many millions of rows across the R1+R2 universe -- SQLite
(store/db.py) holds only the small bookkeeping tables, never the trades
themselves.
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

import duckdb
import polars as pl

from kalshi_mt.util import PROJECT_ROOT

log = logging.getLogger(__name__)

COMPACT_AT_PARTS = 64

# Deliberately well under the machine's RAM: this runs alongside a collector,
# and DuckDB's default (80% of TOTAL RAM) is a budget the machine does not
# actually have free. See _duckdb_connect.
DUCKDB_MEMORY_LIMIT_GB = 6
# Markets per ASOF-join batch in last_trade_at_or_before. Chunking by TICKER
# (not by ref row) keeps all 11 of a market's lookback refs in the same batch,
# so the parquet scan's ticker filter stays selective; chunking by ref would
# smear one market across batches and re-read the tape for each.
#
# 5,000 rather than 20,000: at 20k the batch still blew the budget ("failed to
# pin block of size 256.0 KiB (5.5 GiB/5.5 GiB used)", 2026-08-04). A batch
# holds roughly batch_size x mean-fills-per-market rows before the dedup --
# ~600 fills/market measured, so 5k markets is ~3M rows, comfortably inside the
# limit. The cost is more passes over the tape, which is I/O the machine has.
ASOF_TICKER_BATCH = 5_000
# DuckDB sizes several buffers PER THREAD, so on a many-core machine the real
# peak is a multiple of what one thread suggests. Capping threads trades some
# speed for a peak that actually fits the budget above.
DUCKDB_THREADS = 4


def _duckdb_connect() -> duckdb.DuckDBPyConnection:
    """An in-memory DuckDB connection that can SPILL TO DISK.

    Without a temp_directory an in-memory database has nowhere to put
    intermediates and raises OutOfMemoryError instead of spilling. That is not
    hypothetical: once Pass 2's R2 tape landed, the whole-tape DISTINCT ON
    feeding last_trade_at_or_before stopped fitting in RAM and R1's panel build
    -- which had run fine for weeks -- died with "Allocation failure"
    (2026-07-28, ~22.4M fills). Spilling turns that into a slower query rather
    than a failed pipeline, which is the right trade for a batch job.

    The spill directory sits under the parquet root rather than the OS temp
    dir so it lands on the same (large) volume as the data itself.

    An explicit memory_limit is set too, and it matters more than it looks.
    DuckDB's default budget is 80% of TOTAL system RAM, which is the wrong
    number whenever anything else is running -- on 2026-08-04, with a collector
    holding memory and a 61.7M-fill tape, the panel build died with "Allocation
    failure" despite having a spill directory: DuckDB thought it had far more
    headroom than the machine actually had free, so it committed to an
    in-memory plan instead of choosing to spill. A conservative fixed budget
    makes spilling the planner's choice rather than a rescue that comes too
    late.
    """
    con = duckdb.connect()
    spill = PROJECT_ROOT / "data" / "duckdb_spill"
    spill.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory = '{spill.as_posix()}'")
    con.execute(f"SET memory_limit = '{DUCKDB_MEMORY_LIMIT_GB}GB'")
    con.execute(f"SET threads = {DUCKDB_THREADS}")
    return con


TRADE_SCHEMA = {
    "trade_id": pl.String,
    "ticker": pl.String,
    "count_fp": pl.Float64,
    "yes_price_dollars": pl.Float64,
    "no_price_dollars": pl.Float64,
    "taker_outcome_side": pl.String,
    "taker_book_side": pl.String,
    "taker_side": pl.String,
    "created_time": pl.String,
    "is_block_trade": pl.Boolean,
    "source": pl.String,  # 'live' | 'historical'
}


def month_str(created_time: str) -> str:
    """YYYY-MM from an ISO-8601 timestamp string ('2022-12-30T17:15:45Z' -> '2022-12')."""
    return created_time[:7]


class TradeStore:
    def __init__(self, parquet_dir: str | Path) -> None:
        base = Path(parquet_dir)
        self.base = base if base.is_absolute() else PROJECT_ROOT / base
        self.base.mkdir(parents=True, exist_ok=True)

    def _partition(self, month: str) -> Path:
        return self.base / f"month={month}" / "trades.parquet"

    def _part_files(self, month: str) -> list[Path]:
        d = self.base / f"month={month}"
        return sorted(d.glob("*.parquet")) if d.is_dir() else []

    def append(self, rows: list[dict]) -> int:
        """Append trade rows as a NEW part file per call. Returns rows written.

        Deliberately does NOT read the existing partition. It used to: read the
        whole month, anti-join on trade_id, concat, rewrite. That is O(partition
        size) per append, so cost grows with everything already collected --
        measured live 2026-07-27, Pass 2 over the R2 window decayed from ~6.8
        req/s to ~0.5 req/s once month=2026-06 reached 371MB, because every
        page of every market paid a ~750MB read+write. Remaining ETA had gone
        from ~4h to 17.5h and was still worsening.

        Dedup therefore moves to READ time (see _read_month / the DuckDB
        aggregates, which all dedup on trade_id). Writes stay append-only and
        O(batch); a page re-fetched on resume simply lands as a duplicate row
        that every reader drops. Within a single batch dedup still happens here,
        since that is free.

        Part files are compacted once a month accumulates COMPACT_AT_PARTS of
        them, which bounds both file count and read-side fragmentation while
        keeping the rewrite cost amortised over many appends rather than paid
        on every one."""
        if not rows:
            return 0
        clean = [{col: r.get(col) for col in TRADE_SCHEMA} for r in rows]
        df = pl.DataFrame(clean, schema=TRADE_SCHEMA)
        df = df.filter(pl.col("created_time").is_not_null() & pl.col("trade_id").is_not_null())
        df = df.unique(subset=["trade_id"], keep="first")
        if df.is_empty():
            return 0
        written = 0
        df = df.with_columns(pl.col("created_time").str.slice(0, 7).alias("_month"))
        for (month,), part in df.partition_by("_month", as_dict=True).items():
            part = part.drop("_month")
            d = self.base / f"month={month}"
            d.mkdir(parents=True, exist_ok=True)
            # uuid4, not a counter: concurrent tickers share the month directory
            # and a counter would collide. Written to .tmp then moved, so a
            # reader never sees a half-written part.
            name = f"part-{uuid.uuid4().hex}.parquet"
            tmp = d / (name + ".tmp")
            part.write_parquet(tmp)
            os.replace(tmp, d / name)
            written += len(part)
            self._maybe_compact(month)
        return written

    def _maybe_compact(self, month: str) -> None:
        """Merge a month's part files once there are enough to be worth it.

        Runs through DuckDB, which SPILLS TO DISK, rather than materialising
        the month in RAM. The amortisation argument in the append() docstring
        is about TIME -- paying O(partition) once per COMPACT_AT_PARTS appends
        instead of on every one -- and it quietly assumed the partition would
        fit in memory. It stopped fitting on 2026-08-24: Pass 2 was killed by
        `memory allocation of 635487952 bytes failed` at the exact moment
        month=2026-06 reached its 64th part file, 1.5GB of ZSTD-compressed
        tape holding 39.7M fills. Decompressed into Polars, concatenated, then
        deduplicated, that wants tens of gigabytes on a 27.7GB host, and the
        Windows commit limit refused it.

        Streaming Polars (scan_parquet -> unique -> sink_parquet) was tried on
        the same partition and died the same way, because the dedup is not
        streamable and falls back to an in-memory hash. DuckDB's GROUP BY is a
        spillable hash aggregate, and _duckdb_connect already pins a memory
        limit and a spill directory on the data volume: measured on that exact
        partition, 31.8s at a 4GB cap, output verified row-for-row against
        COUNT(DISTINCT trade_id).

        Dedup keeps one arbitrary row per trade_id rather than Polars'
        "first". The two agree here: a duplicate only exists because a page
        was re-fetched on resume, so the rows are byte-identical -- and every
        reader dedups on trade_id anyway, which is what actually guarantees
        correctness."""
        parts = self._part_files(month)
        if len(parts) < COMPACT_AT_PARTS:
            return
        d = self.base / f"month={month}"
        name = f"part-{uuid.uuid4().hex}.parquet"
        tmp = d / (name + ".tmp")
        cols = ", ".join(
            f'any_value("{c}") AS "{c}"' for c in TRADE_SCHEMA if c != "trade_id"
        )
        con = _duckdb_connect()
        try:
            con.execute(
                f"COPY (SELECT trade_id, {cols} "
                f"FROM read_parquet($paths, union_by_name=true) GROUP BY trade_id) "
                f"TO '{tmp.as_posix()}' (FORMAT PARQUET, COMPRESSION ZSTD)",
                {"paths": [str(p) for p in parts]},
            )
        finally:
            con.close()
        os.replace(tmp, d / name)
        for f in parts:
            try:
                f.unlink()
            except OSError:
                # A reader may hold it briefly on Windows; it is now redundant
                # (its rows are in the merged file and readers dedup), so a
                # failed unlink costs disk space, never correctness.
                log.warning("could not remove compacted part %s", f)

    def _read_month(self, month: str) -> pl.DataFrame:
        parts = self._part_files(month)
        if not parts:
            return pl.DataFrame(schema=TRADE_SCHEMA)
        return pl.concat(
            [pl.read_parquet(f, memory_map=False) for f in parts], how="diagonal"
        ).unique(subset=["trade_id"], keep="first")

    def months_on_disk(self) -> list[str]:
        return sorted(p.name.split("=", 1)[1] for p in self.base.glob("month=*") if p.is_dir())

    def read_range(self, months: list[str]) -> pl.DataFrame:
        frames = [df for m in months if not (df := self._read_month(m)).is_empty()]
        if not frames:
            return pl.DataFrame(schema=TRADE_SCHEMA)
        # Dedup again across months: a trade_id is unique tape-wide, and a
        # re-fetched page could in principle straddle a month boundary.
        return pl.concat(frames, how="diagonal").unique(subset=["trade_id"], keep="first")

    def read_all(self) -> pl.DataFrame:
        return self.read_range(self.months_on_disk())

    def read_for_ticker(self, ticker: str, months: list[str] | None = None) -> pl.DataFrame:
        """All trades for one ticker. Scans the given months (or every
        partition on disk if not given) -- fine for R1/R2 analysis reads.

        Pass 2's RESUME state (cursor, endpoint family) lives in SQLite's
        pass2_progress, since that is what a restart needs. Its trade_count
        there is only a progress indicator and can drift low after a crash
        between the Parquet write and the SQLite commit -- use
        trade_count_by_ticker() for the completeness contract's fetched
        counts, which reads the tape itself."""
        df = self.read_range(months if months is not None else self.months_on_disk())
        if df.is_empty():
            return df
        return df.filter(pl.col("ticker") == ticker)

    def dollar_volume_by_ticker(self) -> dict[str, float]:
        """Total dollar notional traded per ticker -- Sigma(count_fp *
        yes_price_dollars) across every fill -- the input to r1/filters.py's
        TRUE $1k volume gate (spec S1: "total traded volume at closure >=
        $1,000", a dollar figure; Kalshi's own volume_fp field Pass 1/2 use
        as a cheap SCOPING proxy is a CONTRACT COUNT, not notional, and
        2026-07-21's audit confirmed count>=1000 admits markets with real
        notional under $1000 whenever price<$1 -- exactly the tail bins the
        FLB headline depends on).

        Computed via DuckDB, not a polars .collect() (even with
        engine="streaming"): this repo's own control/polymarket.py rewrite
        found polars streaming memory-unsafe on a large parquet
        aggregate/join on this machine (RSS climbed past 11GB and was still
        growing when killed; DuckDB's equivalent query finished in ~13s) --
        a plain groupby-sum is cheaper than that join, but DuckDB is the
        proven-safe path for any whole-tape aggregate over Pass 2's
        multi-million-row dataset, so it stays the default here too."""
        if not self.months_on_disk():
            return {}
        query = (
            "SELECT ticker, SUM(count_fp * yes_price_dollars) AS dollar_volume FROM ("
            "  SELECT DISTINCT ON (trade_id) trade_id, ticker, count_fp, yes_price_dollars "
            "  FROM read_parquet(?)"
            ") GROUP BY ticker"
        )
        result = _duckdb_connect().execute(query, [str(self.base / "month=*" / "*.parquet")]).pl()
        return dict(zip(result["ticker"].to_list(), result["dollar_volume"].to_list()))

    def last_trade_at_or_before(
        self, refs: list[tuple[str, int, int]],
    ) -> dict[tuple[str, int], tuple[float, int, float, str]]:
        """For each (ticker, key, ref_epoch), the last fill at or before
        ref_epoch: {(ticker, key): (yes_price, created_epoch, count_fp, taker_outcome_side)}.

        count_fp comes back because the fee model is defined on the ORDER
        TOTAL with ceil-to-cent rounding, so the actual order size is required
        to compute a fee correctly -- assuming 1 contract inflates the
        effective rate up to 14x on the cheapest strikes (spec S1: "compute
        fees on actual per-order contract counts").

        taker_outcome_side comes back because BDW attribute each panel
        observation to a Maker or a Taker by the side of the trade that SET
        that price -- their Table 10 totals 313,972 (the doubled panel) with
        Makers exactly 156,986, i.e. one role per side of every observation.

        This is the exact primitive BDW's "last trade before the same time"
        describes, evaluated against Pass 2's full tape rather than by
        re-querying the API -- so the backfilled panel (r1/panel.py) costs no
        refetch and is exact rather than an approximation carried forward from
        whichever days Pass 1 happened to capture.

        Uses DuckDB's ASOF JOIN, which is precisely "the latest row not after
        this timestamp" -- doing it per (ticker, ref) in Python would be ~365k
        scans over a multi-million-row tape. Same DuckDB-not-polars reasoning
        as the aggregates above.

        BATCHED BY TICKER, because one query stopped fitting. R1's panel (33k
        markets against a 22M-fill tape) ran fine as a single ASOF join; R2's
        (126,087 markets against 61.7M fills) died with "Allocation failure"
        even with a spill directory configured. Batching bounds the working set
        regardless of how large the tape grows, which a single query cannot do
        -- the same lesson as pass1's keyset pagination, in a different place.

        Batches are cut on TICKER boundaries so a market's 11 lookback refs
        always resolve together: the tape scan's `ticker IN (...)` filter stays
        selective, and no market can be answered from a partial view of its own
        fills."""
        if not refs or not self.months_on_disk():
            return {}
        by_ticker: dict[str, list[tuple[str, int, int]]] = {}
        for ref in refs:
            by_ticker.setdefault(ref[0], []).append(ref)
        tickers = sorted(by_ticker)
        out: dict[tuple[str, int], tuple[float, int, float, str]] = {}
        for start in range(0, len(tickers), ASOF_TICKER_BATCH):
            batch_refs = [
                ref for ticker in tickers[start:start + ASOF_TICKER_BATCH]
                for ref in by_ticker[ticker]
            ]
            out.update(self._last_trade_batch(batch_refs))
        return out

    def _last_trade_batch(
        self, refs: list[tuple[str, int, int]],
    ) -> dict[tuple[str, int], tuple[float, int, float, str]]:
        """One ASOF-join batch. See last_trade_at_or_before for the contract."""
        con = _duckdb_connect()
        con.execute("CREATE TEMP TABLE refs(ticker VARCHAR, key BIGINT, ref_epoch BIGINT)")
        con.executemany("INSERT INTO refs VALUES (?, ?, ?)", refs)
        # created_time is an ISO-8601 string in the tape; epoch() on a cast
        # TIMESTAMPTZ keeps the comparison in UTC instants, matching the
        # epochs callers compute with util.py's ET helpers.
        rows = con.execute(
            """
            SELECT r.ticker, r.key, t.yes_price_dollars, t.created_epoch,
                   t.count_fp, t.taker_outcome_side
            FROM refs r
            ASOF JOIN (
                -- One row per (ticker, INSTANT), not per fill. Kalshi records
                -- every fill of a sweeping order at the same timestamp, and
                -- those fills can cross several price levels, so "the last
                -- trade at or before T" is genuinely ambiguous whenever an
                -- instant carries more than one fill. Left ambiguous, the ASOF
                -- join answered it from whatever order the parallel scan
                -- happened to produce: measured 2026-07-28, two runs over an
                -- unchanged tape returned the same 121,803 panel rows with
                -- ~60 of them in DIFFERENT price bands. Every R1 number was
                -- one draw from that. Smallest trade_id wins -- arbitrary but
                -- FIXED, which is what determinism requires; a construction
                -- pin, recorded in docs/r1_reproduction_findings.md.
                --
                -- Expressed as GROUP BY + arg_min rather than DISTINCT ON, and
                -- that is a memory decision, not a style one. DISTINCT ON sorts
                -- the whole filtered set; at 61.7M fills that sort hit the
                -- memory limit and did NOT spill (three separate failures on
                -- 2026-08-04, the last one still at the ceiling after the batch
                -- was cut 4x -- proof the cost was not proportional to batch
                -- size). A hash aggregate spills, and arg_min(value, trade_id)
                -- expresses exactly the same tie-break.
                --
                -- The former inner `DISTINCT ON (trade_id)` is gone as
                -- redundant: two rows sharing a trade_id necessarily share the
                -- ticker and the instant, so this aggregate already collapses
                -- them. It was a second full sort buying nothing.
                SELECT ticker, created_epoch,
                       arg_min(yes_price_dollars, trade_id) AS yes_price_dollars,
                       arg_min(count_fp, trade_id) AS count_fp,
                       arg_min(taker_outcome_side, trade_id) AS taker_outcome_side
                FROM (
                    SELECT trade_id, ticker, yes_price_dollars, count_fp, taker_outcome_side,
                           CAST(epoch(CAST(created_time AS TIMESTAMPTZ)) AS BIGINT) AS created_epoch
                    FROM read_parquet(?)
                    -- Restrict to the tickers actually asked about BEFORE the
                    -- dedup. R1's panel needs ~33k of the ~92k markets on the
                    -- tape, and deduping all 22M+ fills to answer for a third
                    -- of them is what pushed this query out of memory once
                    -- Pass 2's R2 tape landed.
                    WHERE ticker IN (SELECT ticker FROM refs)
                      AND yes_price_dollars IS NOT NULL AND created_time IS NOT NULL
                )
                GROUP BY ticker, created_epoch
            ) t
              ON r.ticker = t.ticker AND r.ref_epoch >= t.created_epoch
            """,
            [str(self.base / "month=*" / "*.parquet")],
        ).fetchall()
        con.close()
        return {(t, k): (p, ce, c, tk) for t, k, p, ce, c, tk in rows}

    def trade_count_by_ticker(self) -> dict[str, int]:
        """Fills per ticker, counted from the tape itself -- the authoritative
        side of spec S3's recorded-vs-fetched completeness contract.

        pass2_progress.trade_count cannot serve that role on its own: it is a
        running sum of append()'s newly-written-rows return value, committed to
        SQLite AFTER the Parquet write. A crash in between leaves the trades
        durably on disk while the committed counter still points at the
        previous page; on resume the stale cursor re-fetches that page,
        append()'s trade_id anti-join correctly drops the duplicates and
        returns 0, and the counter is never credited for them. The tape stays
        duplicate-free (that part is genuinely safe) but the counter drifts
        LOW, which would read as an incomplete fetch that no amount of
        re-running can fix. Deriving the count here removes that failure mode
        from the contract entirely.

        Same DuckDB-not-polars reasoning as dollar_volume_by_ticker above."""
        if not self.months_on_disk():
            return {}
        query = (
            "SELECT ticker, COUNT(DISTINCT trade_id) AS n FROM read_parquet(?) GROUP BY ticker"
        )
        result = _duckdb_connect().execute(query, [str(self.base / "month=*" / "*.parquet")]).pl()
        return dict(zip(result["ticker"].to_list(), result["n"].to_list()))
