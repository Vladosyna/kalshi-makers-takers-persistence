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
        O(partition) but amortised over COMPACT_AT_PARTS appends, versus the
        old code paying it on every single one."""
        parts = self._part_files(month)
        if len(parts) < COMPACT_AT_PARTS:
            return
        merged = pl.concat(
            [pl.read_parquet(f, memory_map=False) for f in parts], how="diagonal"
        ).unique(subset=["trade_id"], keep="first")
        d = self.base / f"month={month}"
        name = f"part-{uuid.uuid4().hex}.parquet"
        tmp = d / (name + ".tmp")
        merged.write_parquet(tmp)
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
        result = duckdb.connect().execute(query, [str(self.base / "month=*" / "*.parquet")]).pl()
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
        as the aggregates above."""
        if not refs or not self.months_on_disk():
            return {}
        con = duckdb.connect()
        con.execute("CREATE TEMP TABLE refs(ticker VARCHAR, key BIGINT, ref_epoch BIGINT)")
        con.executemany("INSERT INTO refs VALUES (?, ?, ?)", refs)
        # created_time is an ISO-8601 string in the tape; epoch() on a cast
        # TIMESTAMPTZ keeps the comparison in UTC instants, matching the
        # epochs callers compute with util.py's ET helpers.
        rows = con.execute(
            """
            SELECT r.ticker, r.key, t.yes_price_dollars,
                   CAST(epoch(CAST(t.created_time AS TIMESTAMPTZ)) AS BIGINT) AS created_epoch,
                   t.count_fp, t.taker_outcome_side
            FROM refs r
            ASOF JOIN (
                SELECT ticker, yes_price_dollars, created_time, count_fp, taker_outcome_side,
                       CAST(epoch(CAST(created_time AS TIMESTAMPTZ)) AS BIGINT) AS created_epoch
                FROM (SELECT DISTINCT ON (trade_id) * FROM read_parquet(?))
                WHERE yes_price_dollars IS NOT NULL AND created_time IS NOT NULL
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
        result = duckdb.connect().execute(query, [str(self.base / "month=*" / "*.parquet")]).pl()
        return dict(zip(result["ticker"].to_list(), result["n"].to_list()))
