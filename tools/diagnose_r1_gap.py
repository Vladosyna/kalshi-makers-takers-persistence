"""Where does the R1 shortfall actually come from? Read-only.

The gate's reason_counts are MARGINAL -- one market carries several codes, so
they cannot be read as a decomposition. This builds the conditional funnel
instead, under the CONTRACT reading of the volume filter (volume_fp >= 1000),
and then asks the two questions the volume branch cannot answer:

  - among markets that clear volume+24h, how much is lost to the spread
    filter, split structural (spread IS NULL: Kalshi has no bid/ask history)
    vs operational (no quote row at all) vs genuinely wide (> 20c)?
  - is our prices-per-contract shortfall (2.50 vs BDW's 3.39) a duration
    effect, i.e. do short-lived markets contribute contracts but almost no
    lookback depth?
"""

import sqlite3

from kalshi_mt.util import load_config

config = load_config()
conn = sqlite3.connect(config["storage"]["db_path"], timeout=240)
conn.row_factory = sqlite3.Row

BASE = "FROM markets m WHERE m.in_r1_window = 1"
STAGES = [
    ("all in_r1_window", ""),
    ("+ volume_fp >= 1000", " AND m.volume_fp >= 1000"),
    ("+ open >= 24h", " AND m.open_time_epoch IS NOT NULL"
                      " AND (m.close_time_epoch - m.open_time_epoch) >= 86400"),
    ("+ has a quote row", " AND EXISTS (SELECT 1 FROM quotes q WHERE q.ticker = m.ticker)"),
    ("+ spread computable", " AND EXISTS (SELECT 1 FROM quotes q WHERE q.ticker = m.ticker"
                            " AND q.spread IS NOT NULL)"),
    ("+ spread <= 20c", " AND EXISTS (SELECT 1 FROM quotes q WHERE q.ticker = m.ticker"
                        " AND q.spread IS NOT NULL AND q.spread <= 0.20)"),
    ("+ result in (yes,no)", " AND m.result IN ('yes','no')"),
]

print("=== conditional funnel, CONTRACT reading (each row adds one filter) ===")
where = ""
prev = None
for label, clause in STAGES:
    where += clause
    n = conn.execute(f"SELECT COUNT(*) {BASE}{where}").fetchone()[0]
    ev = conn.execute(f"SELECT COUNT(DISTINCT m.event_ticker) {BASE}{where}").fetchone()[0]
    drop = "" if prev is None else f"  (-{prev - n:,}, -{100 * (prev - n) / prev:.1f}%)"
    print(f"  {label:24s} markets {n:>8,}  events {ev:>7,}{drop}")
    prev = n

print()
print("=== spread-filter loss AMONG volume+24h-eligible markets ===")
elig = ("FROM markets m WHERE m.in_r1_window = 1 AND m.volume_fp >= 1000"
        " AND m.open_time_epoch IS NOT NULL"
        " AND (m.close_time_epoch - m.open_time_epoch) >= 86400")
total = conn.execute(f"SELECT COUNT(*) {elig}").fetchone()[0]
buckets = {
    "no quote row (operational)":
        " AND NOT EXISTS (SELECT 1 FROM quotes q WHERE q.ticker = m.ticker)",
    "spread NULL (STRUCTURAL, no bid/ask history)":
        " AND EXISTS (SELECT 1 FROM quotes q WHERE q.ticker = m.ticker AND q.spread IS NULL)",
    "spread > 20c (genuine filter)":
        " AND EXISTS (SELECT 1 FROM quotes q WHERE q.ticker = m.ticker AND q.spread > 0.20)",
    "spread <= 20c (passes)":
        " AND EXISTS (SELECT 1 FROM quotes q WHERE q.ticker = m.ticker"
        " AND q.spread IS NOT NULL AND q.spread <= 0.20)",
}
print(f"  eligible (volume+24h): {total:,}")
for label, clause in buckets.items():
    n = conn.execute(f"SELECT COUNT(*) {elig}{clause}").fetchone()[0]
    print(f"    {label:46s} {n:>8,}  ({100 * n / total:.1f}%)")

print()
print("=== panel depth vs market duration (tests the 24h / daily-series hypothesis) ===")
print("  BDW implied prices-per-contract: 3.39")
rows = conn.execute(
    """
    SELECT CASE
             WHEN (m.close_time_epoch - m.open_time_epoch) < 172800 THEN '1: 24-48h'
             WHEN (m.close_time_epoch - m.open_time_epoch) < 604800 THEN '2: 2-7d'
             WHEN (m.close_time_epoch - m.open_time_epoch) < 2592000 THEN '3: 7-30d'
             ELSE '4: 30d+'
           END AS bucket,
           COUNT(DISTINCT m.ticker) AS contracts,
           COUNT(pp.ticker) AS prices
    FROM markets m
    JOIN quotes q ON q.ticker = m.ticker
    JOIN price_panel pp ON pp.ticker = m.ticker
    WHERE m.in_r1_window = 1 AND m.volume_fp >= 1000
      AND m.open_time_epoch IS NOT NULL
      AND (m.close_time_epoch - m.open_time_epoch) >= 86400
      AND q.spread IS NOT NULL AND q.spread <= 0.20
      AND m.result IN ('yes','no')
    GROUP BY bucket ORDER BY bucket
    """
).fetchall()
tot_c = tot_p = 0
for r in rows:
    ppc = r["prices"] / r["contracts"] if r["contracts"] else 0
    print(f"  {r['bucket']:12s} contracts {r['contracts']:>7,}  prices {r['prices']:>8,}  per-contract {ppc:.2f}")
    tot_c += r["contracts"]
    tot_p += r["prices"]
if tot_c:
    print(f"  {'TOTAL':12s} contracts {tot_c:>7,}  prices {tot_p:>8,}  per-contract {tot_p / tot_c:.2f}")
conn.close()
