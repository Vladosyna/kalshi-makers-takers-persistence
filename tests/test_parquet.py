from __future__ import annotations

import polars as pl
import pytest

from kalshi_mt.store.parquet import TradeStore, month_str


def _trade(trade_id, ticker="ABC-1", created_time="2022-12-30T17:15:45Z", **kw):
    return {
        "trade_id": trade_id, "ticker": ticker, "count_fp": 1.0,
        "yes_price_dollars": 0.49, "no_price_dollars": 0.51,
        "taker_outcome_side": "no", "taker_book_side": "ask", "taker_side": "no",
        "created_time": created_time, "is_block_trade": False, "source": "historical",
        **kw,
    }


def test_month_str():
    assert month_str("2022-12-30T17:15:45Z") == "2022-12"
    assert month_str("2026-01-05T00:00:00Z") == "2026-01"


def test_append_and_read(tmp_path):
    store = TradeStore(tmp_path / "parquet")
    written = store.append([_trade("t1"), _trade("t2")])
    assert written == 2
    df = store.read_for_ticker("ABC-1")
    assert len(df) == 2
    assert set(df["trade_id"]) == {"t1", "t2"}


def test_append_dedups_on_trade_id(tmp_path):
    store = TradeStore(tmp_path / "parquet")
    store.append([_trade("t1")])
    written_again = store.append([_trade("t1"), _trade("t2")])
    # append() is append-only now: it reports ROWS WRITTEN, not rows that were
    # new to the store. Deduplication moved to read time (2026-07-27) because
    # reading the partition on every append was O(partition) and collapsed Pass
    # 2's throughput once a month reached 371MB. What must still hold is that
    # readers never see the duplicate -- asserted below.
    assert written_again == 2
    df = store.read_for_ticker("ABC-1")
    assert len(df) == 2


def test_append_partitions_by_month(tmp_path):
    store = TradeStore(tmp_path / "parquet")
    store.append([
        _trade("t1", created_time="2022-12-30T17:15:45Z"),
        _trade("t2", created_time="2023-01-02T00:00:00Z"),
    ])
    assert set(store.months_on_disk()) == {"2022-12", "2023-01"}


def test_read_for_ticker_filters_correctly(tmp_path):
    store = TradeStore(tmp_path / "parquet")
    store.append([_trade("t1", ticker="ABC-1"), _trade("t2", ticker="XYZ-1")])
    df = store.read_for_ticker("ABC-1")
    assert len(df) == 1
    assert df["ticker"][0] == "ABC-1"


def test_append_empty_list_is_noop(tmp_path):
    store = TradeStore(tmp_path / "parquet")
    assert store.append([]) == 0
    assert store.months_on_disk() == []


def test_read_range_missing_month_is_empty(tmp_path):
    store = TradeStore(tmp_path / "parquet")
    df = store.read_range(["2099-01"])
    assert df.is_empty()


def test_dollar_volume_by_ticker_empty_store(tmp_path):
    store = TradeStore(tmp_path / "parquet")
    assert store.dollar_volume_by_ticker() == {}


def test_dollar_volume_by_ticker_sums_count_times_price(tmp_path):
    """The TRUE $-notional gate r1/filters.py's volume check needs
    (2026-07-21 audit) -- Sigma(count_fp * yes_price_dollars) per ticker,
    not Kalshi's own volume_fp contract count."""
    store = TradeStore(tmp_path / "parquet")
    store.append([
        _trade("t1", ticker="ABC-1", count_fp=100.0, yes_price_dollars=0.5),   # $50
        _trade("t2", ticker="ABC-1", count_fp=200.0, yes_price_dollars=0.25),  # $50
        _trade("t3", ticker="XYZ-1", count_fp=10.0, yes_price_dollars=0.9),    # $9
    ])
    volumes = store.dollar_volume_by_ticker()
    assert abs(volumes["ABC-1"] - 100.0) < 1e-9
    assert abs(volumes["XYZ-1"] - 9.0) < 1e-9


def test_dollar_volume_by_ticker_across_month_partitions(tmp_path):
    """Trades for one ticker spread across multiple month partitions must
    still sum to one total -- the aggregate reads every partition, not
    just the most recent one."""
    store = TradeStore(tmp_path / "parquet")
    store.append([_trade("t1", ticker="ABC-1", count_fp=1000.0, yes_price_dollars=0.5,
                          created_time="2022-12-30T17:15:45Z")])
    store.append([_trade("t2", ticker="ABC-1", count_fp=1000.0, yes_price_dollars=0.5,
                          created_time="2023-01-02T00:00:00Z")])
    volumes = store.dollar_volume_by_ticker()
    assert abs(volumes["ABC-1"] - 1000.0) < 1e-9


def test_trade_count_by_ticker_empty_store(tmp_path):
    store = TradeStore(tmp_path / "parquet")
    assert store.trade_count_by_ticker() == {}


def test_trade_count_by_ticker_counts_fills_from_the_tape(tmp_path):
    """The authoritative side of spec S3's recorded-vs-fetched contract:
    pass2_progress.trade_count is a running sum committed AFTER the Parquet
    write, so a crash in that window leaves trades on disk uncredited and the
    counter drifts low for good. Counting the tape has no such failure mode."""
    store = TradeStore(tmp_path / "parquet")
    store.append([
        _trade("t1", ticker="ABC-1"),
        _trade("t2", ticker="ABC-1"),
        _trade("t3", ticker="XYZ-1"),
    ])
    assert store.trade_count_by_ticker() == {"ABC-1": 2, "XYZ-1": 1}


def test_trade_count_by_ticker_is_unaffected_by_a_replayed_page(tmp_path):
    """The exact drift scenario: the same page re-fetched on resume is deduped
    to zero NEW rows (so the running counter never gets credited), but the
    tape-derived count still reports the true total."""
    store = TradeStore(tmp_path / "parquet")
    page = [_trade("t1", ticker="ABC-1"), _trade("t2", ticker="ABC-1")]
    assert store.append(page) == 2
    assert store.append(page) == 2          # replay is written again...
    # ...and every reader must still see exactly the two distinct trades.
    assert store.trade_count_by_ticker() == {"ABC-1": 2}
    assert len(store.read_for_ticker("ABC-1")) == 2
    assert len(store.read_all()) == 2
    vol = store.dollar_volume_by_ticker()
    assert abs(vol["ABC-1"] - 2 * 1.0 * 0.49) < 1e-9   # not double-counted


def test_trade_count_by_ticker_across_month_partitions(tmp_path):
    store = TradeStore(tmp_path / "parquet")
    store.append([_trade("t1", ticker="ABC-1", created_time="2022-12-30T17:15:45Z")])
    store.append([_trade("t2", ticker="ABC-1", created_time="2023-01-02T00:00:00Z")])
    assert store.trade_count_by_ticker() == {"ABC-1": 2}


def test_append_read_modify_write_leaves_no_temp_file_and_survives_repeat(tmp_path):
    """append() is a read-modify-write of ONE path. On Windows a
    memory-mapped read keeps a mapping open on it, so replacing that same file
    fails with ERROR_USER_MAPPED_FILE (os error 1224) -- confirmed live
    2026-07-26, a 29,285-ticker Pass 2 run lost exactly one ticker to it. The
    write also goes through a temp file and an atomic replace, so a crash
    partway cannot leave a truncated partition; nothing temporary may survive.
    """
    store = TradeStore(tmp_path / "parquet")
    store.append([_trade("t1", ticker="ABC-1")])
    # Second append must re-read and rewrite the SAME partition.
    assert store.append([_trade("t2", ticker="ABC-1")]) == 1
    assert store.trade_count_by_ticker() == {"ABC-1": 2}

    leftovers = list((tmp_path / "parquet").rglob("*.tmp"))
    assert leftovers == []
    # Append-only: each call leaves its own part file, none half-written.
    files = [p for p in (tmp_path / "parquet").rglob("*") if p.is_file()]
    assert len(files) == 2
    assert all(f.name.startswith("part-") and f.suffix == ".parquet" for f in files)


def test_append_compacts_once_a_month_accumulates_enough_parts(tmp_path):
    """Append-only writes would otherwise leave one file per call -- ~100k of
    them across Pass 2 -- which slows every read and strains the filesystem.
    Compaction merges them once the threshold is reached, paying the
    O(partition) rewrite once per COMPACT_AT_PARTS appends instead of on every
    append (the behaviour that collapsed throughput before 2026-07-27)."""
    from kalshi_mt.store.parquet import COMPACT_AT_PARTS

    store = TradeStore(tmp_path / "parquet")
    for i in range(COMPACT_AT_PARTS + 2):
        store.append([_trade(f"t{i}", ticker="ABC-1")])

    parts = list((tmp_path / "parquet").rglob("*.parquet"))
    assert len(parts) < COMPACT_AT_PARTS, "compaction did not fire"
    # Compaction must not lose or duplicate anything.
    assert store.trade_count_by_ticker() == {"ABC-1": COMPACT_AT_PARTS + 2}
    assert list((tmp_path / "parquet").rglob("*.tmp")) == []


def _epoch(iso: str) -> int:
    from datetime import datetime, timezone

    return int(datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())


def test_last_trade_at_or_before_picks_the_latest_fill(tmp_path):
    store = TradeStore(tmp_path / "parquet")
    store.append([
        _trade("t1", created_time="2022-12-30T10:00:00Z", yes_price_dollars=0.10),
        _trade("t2", created_time="2022-12-30T11:00:00Z", yes_price_dollars=0.20),
        _trade("t3", created_time="2022-12-30T12:00:00Z", yes_price_dollars=0.30),
    ])
    got = store.last_trade_at_or_before([("ABC-1", 0, _epoch("2022-12-30T11:30:00Z"))])
    assert got[("ABC-1", 0)][0] == 0.20


def test_last_trade_at_or_before_is_deterministic_when_fills_share_an_instant(tmp_path):
    """A sweeping order fills against several resting orders at ONE timestamp,
    across several price levels, so "the last trade at or before T" has no
    unique answer unless the tie is broken explicitly. Left to the query
    planner it was answered from parallel-scan order: measured on the real
    tape, two runs put ~60 panel rows in different price bands. The rule is
    smallest trade_id -- arbitrary, but fixed."""
    store = TradeStore(tmp_path / "parquet")
    store.append([
        _trade("t_c", created_time="2022-12-30T11:00:00Z", yes_price_dollars=0.30),
        _trade("t_a", created_time="2022-12-30T11:00:00Z", yes_price_dollars=0.10),
        _trade("t_b", created_time="2022-12-30T11:00:00Z", yes_price_dollars=0.20),
    ])
    ref = [("ABC-1", 0, _epoch("2022-12-30T12:00:00Z"))]
    answers = {store.last_trade_at_or_before(ref)[("ABC-1", 0)][0] for _ in range(5)}
    assert answers == {0.10}, f"tie broken inconsistently: {answers}"


def test_last_trade_at_or_before_returns_nothing_before_the_first_fill(tmp_path):
    store = TradeStore(tmp_path / "parquet")
    store.append([_trade("t1", created_time="2022-12-30T10:00:00Z")])
    assert store.last_trade_at_or_before([("ABC-1", 0, _epoch("2022-12-30T09:00:00Z"))]) == {}


def test_last_trade_at_or_before_batches_without_changing_the_answer(tmp_path, monkeypatch):
    """Batching is a memory fix, not a semantic one: the same refs must give the
    same answer whether they fit in one batch or are split across several. R2's
    panel (126,087 markets, 61.7M fills) is what forced the split -- a single
    ASOF join died with "Allocation failure" even with spilling configured."""
    from kalshi_mt.store import parquet as parquet_mod

    store = TradeStore(tmp_path / "parquet")
    rows = []
    for i in range(7):
        rows.append(_trade(f"t{i}", ticker=f"M-{i}", created_time="2022-12-30T10:00:00Z",
                           yes_price_dollars=0.10 + 0.05 * i))
        rows.append(_trade(f"u{i}", ticker=f"M-{i}", created_time="2022-12-30T12:00:00Z",
                           yes_price_dollars=0.60 + 0.05 * i))
    store.append(rows)

    refs = [(f"M-{i}", 0, _epoch("2022-12-30T11:00:00Z")) for i in range(7)]
    monkeypatch.setattr(parquet_mod, "ASOF_TICKER_BATCH", 100)
    single = store.last_trade_at_or_before(refs)
    monkeypatch.setattr(parquet_mod, "ASOF_TICKER_BATCH", 2)
    batched = store.last_trade_at_or_before(refs)

    assert single == batched
    assert len(single) == 7
    # 11:00 sits between the two fills, so the 10:00 one is the answer.
    assert single[("M-3", 0)][0] == pytest.approx(0.25)


def test_last_trade_at_or_before_batches_keep_a_market_whole(tmp_path, monkeypatch):
    """A market's lookback refs must never be split across batches -- each
    batch filters the tape by its own ticker set, so a market answered from a
    partial view would silently lose fills."""
    from kalshi_mt.store import parquet as parquet_mod

    store = TradeStore(tmp_path / "parquet")
    store.append([
        _trade("a", ticker="M-1", created_time="2022-12-30T09:00:00Z", yes_price_dollars=0.11),
        _trade("b", ticker="M-1", created_time="2022-12-30T11:00:00Z", yes_price_dollars=0.22),
        _trade("c", ticker="M-2", created_time="2022-12-30T09:00:00Z", yes_price_dollars=0.33),
    ])
    refs = [
        ("M-1", 0, _epoch("2022-12-30T12:00:00Z")),
        ("M-1", 1, _epoch("2022-12-30T10:00:00Z")),
        ("M-2", 0, _epoch("2022-12-30T12:00:00Z")),
    ]
    monkeypatch.setattr(parquet_mod, "ASOF_TICKER_BATCH", 1)
    got = store.last_trade_at_or_before(refs)
    assert got[("M-1", 0)][0] == pytest.approx(0.22)
    assert got[("M-1", 1)][0] == pytest.approx(0.11)
    assert got[("M-2", 0)][0] == pytest.approx(0.33)


def test_iter_fills_streams_the_same_rows_as_read_all(tmp_path):
    """iter_fills is the memory-bounded replacement for read_all(). If the two
    ever disagree, every consumer moved onto the stream silently changes its
    answer -- so pin them equal rather than trusting the refactor."""
    store = TradeStore(tmp_path)
    rows = []
    for i in range(50):
        month = "2026-05" if i % 2 else "2026-06"
        rows.append({
            "trade_id": f"t{i}", "ticker": f"KX-{i % 7}", "count_fp": float(i),
            "yes_price_dollars": 0.5, "no_price_dollars": 0.5,
            "taker_outcome_side": "yes" if i % 3 else None,
            "taker_book_side": "no", "taker_side": None,
            "created_time": f"{month}-1{i % 9}T12:00:00Z",
            "is_block_trade": False, "source": "live",
        })
    store.append(rows)

    eager = store.read_all().sort("trade_id")
    streamed = pl.concat(list(store.iter_fills(batch_rows=7)), how="diagonal").sort("trade_id")
    assert streamed.select(sorted(eager.columns)).equals(eager.select(sorted(eager.columns)))


def test_iter_fills_pushes_the_ticker_and_column_filters_down(tmp_path):
    store = TradeStore(tmp_path)
    store.append([
        {"trade_id": f"t{i}", "ticker": f"KX-{i}", "count_fp": 1.0,
         "yes_price_dollars": 0.5, "no_price_dollars": 0.5,
         "taker_outcome_side": "yes", "taker_book_side": "no", "taker_side": None,
         "created_time": "2026-05-01T12:00:00Z", "is_block_trade": False, "source": "live"}
        for i in range(5)
    ])
    got = pl.concat(list(store.iter_fills(tickers=["KX-1", "KX-3"], columns=["ticker", "count_fp"])))
    assert got.columns == ["ticker", "count_fp"]
    assert sorted(got["ticker"].to_list()) == ["KX-1", "KX-3"]
    # an empty scope must yield nothing rather than everything
    assert list(store.iter_fills(tickers=[])) == []
