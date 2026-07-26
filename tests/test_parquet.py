from __future__ import annotations

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
    assert written_again == 1  # t1 already present, only t2 is new
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
    assert store.append(page) == 0          # replay: nothing new written
    assert store.trade_count_by_ticker() == {"ABC-1": 2}


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
    # The month partition still holds exactly one readable data file.
    files = sorted(p.name for p in (tmp_path / "parquet").rglob("*") if p.is_file())
    assert files == ["trades.parquet"]
