"""Snapshot Kalshi's per-series fee attributes from the API into a dated artifact.

Why
---
Kalshi's maker fee is NOT a market-wide regime: it is a per-series surcharge
that applies only to an enumerated list of series (see docs/sources/fees/ for
the dated PDF evidence). From the "Oct 1, 2025" version onward the PDF stopped
listing those series and deferred to the live web page, which is client-
rendered and whose Wayback captures are empty app shells -- so the archived
PDFs pin series membership only through 2025-09-18.

The API closes part of that gap: GET /series/{ticker} returns `fee_type` and
`fee_multiplier` per series. That is TODAY's state, not history -- it cannot
date a change -- but combined with the dated PDFs it brackets membership:
PDF lists give the lower bound up to 2025-09-18, this catalog gives the
current upper bound. Anything in between is reported as a bound, never as a
point estimate (spec S4's fee-sensitivity ribbon is exactly the mechanism for
carrying that uncertainty into the results).

The freeze timestamp is recorded in the artifact, same completeness contract
as the fetch passes.

Usage
-----
    python tools/fetch_series_fee_catalog.py            # refresh the catalog
    python tools/fetch_series_fee_catalog.py --summary  # report on the stored one
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import httpx

BASE = "https://external-api.kalshi.com/trade-api/v2"
OUT = Path(__file__).resolve().parent.parent / "data" / "series_fee_catalog.json"
# Well under the collector's own sustained rate -- this runs alongside it.
SPACING_S = 0.35


def fetch() -> dict:
    frozen_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    series: dict[str, dict] = {}
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        resp = client.get(f"{BASE}/series")
        resp.raise_for_status()
        listing = resp.json().get("series", [])
        print(f"GET /series -> {len(listing)} series")
        for i, entry in enumerate(listing, 1):
            ticker = entry.get("ticker")
            if not ticker:
                continue
            record = {
                "category": entry.get("category"),
                "fee_type": entry.get("fee_type"),
                "fee_multiplier": entry.get("fee_multiplier"),
            }
            # The listing endpoint does not always carry the fee fields; fall
            # back to the per-series detail call only for those that lack them,
            # so a complete listing costs exactly one request.
            if record["fee_type"] is None:
                try:
                    detail = client.get(f"{BASE}/series/{ticker}")
                    if detail.status_code == 200:
                        d = detail.json().get("series", {})
                        record["fee_type"] = d.get("fee_type")
                        record["fee_multiplier"] = d.get("fee_multiplier")
                        record["category"] = record["category"] or d.get("category")
                except Exception as exc:  # noqa: BLE001 - report, keep going
                    record["error"] = repr(exc)
                time.sleep(SPACING_S)
                if i % 100 == 0:
                    print(f"  {i}/{len(listing)} detail-filled")
            series[ticker] = record
    return {"frozen_at": frozen_at, "source": f"{BASE}/series", "series": series}


def summarise(doc: dict) -> None:
    series = doc["series"]
    print(f"frozen_at: {doc['frozen_at']}   series: {len(series)}")
    print()
    print("fee_type distribution:")
    for value, n in Counter(s.get("fee_type") for s in series.values()).most_common():
        print(f"  {str(value):<32} {n:5d}")
    print()
    print("fee_multiplier distribution:")
    for value, n in Counter(s.get("fee_multiplier") for s in series.values()).most_common():
        print(f"  {str(value):<32} {n:5d}")
    maker = sorted(t for t, s in series.items() if "maker" in str(s.get("fee_type", "")).lower())
    print()
    print(f"series carrying maker fees: {len(maker)}")
    print("  " + ", ".join(maker[:40]) + (" ..." if len(maker) > 40 else ""))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", action="store_true", help="report on the stored catalog instead of refetching")
    args = parser.parse_args()
    if args.summary:
        doc = json.loads(OUT.read_text(encoding="utf-8"))
    else:
        doc = fetch()
        OUT.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")
        print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
        print()
    summarise(doc)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
