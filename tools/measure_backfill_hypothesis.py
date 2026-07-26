"""Does the skip-vs-backfill rule explain the panel-depth gap? Read-only.

Our pinned rule: on a lookback day with no trade STRICTLY inside that ET
calendar day, skip -- never carry an earlier price forward. Under a backfill
rule, day d would instead get a row whenever ANY trade exists at or before its
reference time, i.e. for every d back to the contract's first trade.

Both sides are computable from what is already on disk -- no API calls:
  t0            price_panel's lookback_day=0 created_time (the anchor)
  first_trade   min(created_time) per ticker from Pass 2's full tape
  rows_backfill 1 + |{d in 1..10 : ref_time(d) >= first_trade}|

Uses the SAME ET helpers as fetch/pass1.py so the day arithmetic matches
production rather than approximating with 86400*d.
"""

import sqlite3

import duckdb

from kalshi_mt.util import (
    PROJECT_ROOT,
    epoch_to_et,
    et_to_epoch,
    iso_to_epoch,
    load_config,
    shift_et_calendar_days,
)

PANEL_LOOKBACK_DAYS = 10
BDW_PRICES, BDW_CONTRACTS = 156_986, 46_282

config = load_config()
conn = sqlite3.connect(config["storage"]["db_path"], timeout=240)
conn.row_factory = sqlite3.Row

# Primary (contract-reading) universe, exactly as cli.py build derives it.
in_scope = {
    r[0] for r in conn.execute(
        "SELECT ticker FROM markets WHERE in_r1_window = 1 "
        "AND ticker NOT IN (SELECT ticker FROM universe_log WHERE window = 'r1')"
    ).fetchall()
}
print(f"primary in-scope tickers: {len(in_scope):,}")

# Day-0 anchor per ticker, plus the rows we ACTUALLY have.
day0 = {}
actual_rows = {}
for r in conn.execute(
    "SELECT ticker, lookback_day, created_time FROM price_panel"
).fetchall():
    t = r["ticker"]
    if t not in in_scope:
        continue
    actual_rows[t] = actual_rows.get(t, 0) + 1
    if r["lookback_day"] == 0:
        day0[t] = r["created_time"]

parquet_glob = str(PROJECT_ROOT / config["storage"]["parquet_dir"] / "month=*" / "trades.parquet")
first_trade_rows = duckdb.connect().execute(
    "SELECT ticker, MIN(created_time) AS first_ct FROM read_parquet(?) GROUP BY ticker",
    [parquet_glob],
).fetchall()
first_trade = {t: iso_to_epoch(ct) for t, ct in first_trade_rows if ct}
print(f"tickers with a tape: {len(first_trade):,}")

contracts = 0
actual_total = 0
backfill_total = 0
missing_tape = 0
for ticker, t0_iso in day0.items():
    t0 = iso_to_epoch(t0_iso)
    if t0 is None:
        continue
    ft = first_trade.get(ticker)
    if ft is None:
        missing_tape += 1
        continue
    contracts += 1
    actual_total += actual_rows.get(ticker, 0)

    t0_et = epoch_to_et(t0)
    rows = 1  # day 0 itself
    for d in range(1, PANEL_LOOKBACK_DAYS + 1):
        ref_epoch = et_to_epoch(shift_et_calendar_days(t0_et, d))
        if ref_epoch >= ft:
            rows += 1
    backfill_total += rows

print()
print(f"contracts measured: {contracts:,}   (skipped, no tape: {missing_tape:,})")
print(f"  ACTUAL  (skip rule)  prices {actual_total:>9,}   per-contract {actual_total / contracts:.2f}")
print(f"  BACKFILL (projected) prices {backfill_total:>9,}   per-contract {backfill_total / contracts:.2f}")
print(f"  BDW                  prices {BDW_PRICES:>9,}   per-contract {BDW_PRICES / BDW_CONTRACTS:.2f}")
conn.close()
