"""Coverage and spot-check for the Polymarket -> Kalshi category mapping.

The SII-WANGZJ archive carries no category column, so S2.4's by-category
breakdown has to be recovered from free text (`event_slug`, `event_title`,
`question`). data/category_map_polymarket_kalshi.yaml v2 holds the rules; this
script reports what fraction of the control window they classify, how the
strata are distributed, and -- the part that actually matters -- a sample of
real questions per stratum so the rules can be judged rather than trusted.

Coverage is a number to REPORT alongside any figure built on this mapping, not
a target to maximise: forcing an unmatched market into a bucket would be worse
than leaving it NULL, which is what the classifier does.

Usage:
    python tools/measure_polymarket_categories.py [--samples N]
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import duckdb  # noqa: E402

from kalshi_mt.control.polymarket import classify_category, load_category_rules  # noqa: E402

MARKETS = Path(__file__).resolve().parent.parent / "data" / "bootstrap" / "markets.parquet"
WINDOW = ("2025-05-01", "2025-12-31 23:59:59")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=3)
    args = parser.parse_args()

    if not MARKETS.exists():
        print(f"{MARKETS} not downloaded -- run the control overlay once to fetch it.")
        return 1

    rules = load_category_rules()
    con = duckdb.connect()
    rows = con.execute(
        f"""
        SELECT event_slug, event_title, question, volume
        FROM read_parquet('{MARKETS.as_posix()}')
        WHERE end_date >= TIMESTAMPTZ '{WINDOW[0]}' AND end_date <= TIMESTAMPTZ '{WINDOW[1]}'
        """
    ).fetchall()

    counts: Counter[str] = Counter()
    volume: defaultdict[str, float] = defaultdict(float)
    samples: defaultdict[str, list[str]] = defaultdict(list)
    for slug, title, question, vol in rows:
        category = classify_category(rules, slug, title, question) or "(unclassified)"
        counts[category] += 1
        volume[category] += float(vol or 0.0)
        if len(samples[category]) < args.samples:
            samples[category].append(f"{str(slug)[:44]:<46} | {str(question)[:52]}")

    total = sum(counts.values())
    classified = total - counts.get("(unclassified)", 0)
    print(f"markets resolving in the control window: {total:,}")
    print(f"classified: {classified:,} ({100.0 * classified / total:.1f}%)")
    total_vol = sum(volume.values()) or 1.0
    classified_vol = total_vol - volume.get("(unclassified)", 0.0)
    print(f"classified by volume: {100.0 * classified_vol / total_vol:.1f}%")
    print()
    print(f"{'stratum':<24} {'markets':>9} {'share':>7} {'vol share':>10}")
    print("-" * 54)
    for category, n in counts.most_common():
        print(f"{category:<24} {n:>9,} {100.0*n/total:>6.1f}% {100.0*volume[category]/total_vol:>9.1f}%")

    print()
    print("samples per stratum (judge the rules on these, do not trust the counts alone):")
    for category, _ in counts.most_common():
        print(f"\n  [{category}]")
        for line in samples[category]:
            print(f"    {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
