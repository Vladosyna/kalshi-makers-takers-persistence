"""Archive Kalshi's published fee-schedule PDF and reconstruct its version history.

Why this exists
---------------
`data/fees.yaml` is the single most error-prone input in this replication
(spec S7): every net-of-fee return, the three fee layers of spec S4, and the
fee-sensitivity ribbon that gates escalation all read off it. The spec
therefore requires the schedule to be sourced from primary artifacts with
archived copies stored in the repo -- not inferred from secondary write-ups.

Kalshi's live fee page (kalshi.com/fee-schedule) is a client-rendered Next.js
app behind bot protection, so neither its HTML nor its Wayback snapshots carry
the numbers. The PDF it links, kalshi.com/docs/kalshi-fee-schedule.pdf, is a
static file that the Wayback Machine HAS captured repeatedly since 2021 -- and
each version carries its own "Last Updated" stamp. That makes the CDX index of
that one URL a dated, primary-source version history.

What it does
------------
1. Queries the Wayback CDX API for every distinct capture of the PDF.
2. Downloads each HTTP-200 capture into docs/sources/fees/ (idempotent --
   existing files are left alone, so re-running costs nothing).
3. If pypdf is importable, extracts the text next to each PDF and prints a
   version table: capture date, the document's own "Last Updated" stamp, the
   taker formula, the maker formula, and the series the maker fee names.

pypdf is deliberately an OPTIONAL import, not a project dependency: the
archiving half needs only the stdlib, and adding a dependency would force a
`uv sync` that cannot run while a collector process holds .venv/Scripts/kmt.exe
open. Install it however you like (`pip install --user pypdf`) to get the
version table.

Usage
-----
    python tools/fetch_fee_schedule_history.py            # archive + report
    python tools/fetch_fee_schedule_history.py --report   # report only
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

PDF_URL = "kalshi.com/docs/kalshi-fee-schedule.pdf"
CDX = (
    "http://web.archive.org/cdx/search/cdx?url={url}"
    "&output=json&fl=timestamp,digest,length,statuscode&collapse=digest&limit=500"
)
# `id_` asks the Wayback Machine for the ORIGINAL bytes rather than a rewritten
# page -- without it the response is wrapped in archive chrome and pypdf sees
# HTML, not a PDF.
SNAPSHOT = "https://web.archive.org/web/{ts}id_/https://{url}"
ARCHIVE_DIR = Path(__file__).resolve().parent.parent / "docs" / "sources" / "fees"
REQUEST_SPACING_S = 4.0  # politeness toward a free public archive
# The archive throttles bursts by refusing the connection outright or by
# serving an HTML notice in place of the file -- both are transient and both
# look like "not a PDF" downstream, so both are retried rather than skipped.
MAX_ATTEMPTS = 4
BACKOFF_S = 15.0
# archive.org throttles urllib's default `Python-urllib/3.x` agent hard: with
# it, 19 of 33 captures failed every attempt while the SAME urls fetched fine
# from a browser-agent client. Identify the tool honestly, but do send an
# agent string the archive will serve.
HEADERS = {
    "User-Agent": (
        "kalshi-makers-takers-persistence/0.1 (academic replication; "
        "archiving Kalshi fee-schedule versions; +https://github.com/Vladosyna/kalshi-makers-takers-persistence)"
    ),
    "Accept": "application/pdf,*/*",
}

# From the June-2025 version onward the document dates ITSELF -- "Last updated
# and effective: June 5, 2025". That stamp, not the Wayback capture date, is
# the effective date the fee step function keys on: a capture merely bounds
# when a version was already public.
_LAST_UPDATED = re.compile(
    r"Last\s+[Uu]pdated(?:\s+and\s+effective)?:?\s*([A-Z][a-z]+\.? \d{1,2},? \d{4})",
    re.IGNORECASE,
)
# Both fee families are written as `fees = round up(<expr>)`; the general one
# is price-dependent (rate x C x P x (1-P)), the first maker one (May-June
# 2025) is a flat per-contract charge (rate x C). Capture whichever appears.
# The 2021-2022 versions differ in every incidental way -- "roundup" with no
# space, a percentage ("14%") instead of a decimal, lowercase c/p, and the
# multiplication sign as U+00D7 rather than "x" -- so match all of them; the
# 14% version is a real, dated rate change, not a formatting quirk to skip.
_FORMULA = re.compile(
    r"round\s*up\s*\(\s*([0-9.]+)\s*(%?)\s*[x×]\s*C\s*"
    r"([x×]\s*P\s*[x×]\s*\(\s*1\s*-\s*P\s*\))?\s*\)",
    re.IGNORECASE,
)
# "Maker Fees" also appears inside the GENERAL section ("...unless they are
# included in our 'Maker Fees' section"), so splitting on the bare phrase puts
# the taker formula on the maker side. The heading is the occurrence followed
# by the section's own opening -- either its scope sentence or its formula.
_MAKER_HEADING = re.compile(r"Maker Fees\s+(?=The products in this section|fees\s*=)")
# The S&P500 / NASDAQ-100 half-rate table sits AFTER the maker section, so the
# maker chunk has to be closed at this heading or the carve-out's 0.035 is
# misread as a maker rate.
_INDEX_HEADING = re.compile(r"Specific Trading Fees Table for S&P500")
_TICKERS = re.compile(r"\b(KX[A-Z0-9]+)\b")
# The maker section enumerates its scope as "Series tickers: A, B, C" and then
# states the formula. The 2025-09-17 version carries TWO such blocks (one for
# series joining on 09/18), so every block is captured, not just the first.
_SERIES_BLOCK = re.compile(r"Series tickers:(.*?)(?=fees\s*=|Series tickers:|$)", re.DOTALL)
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def _iso_date(stamp: str) -> str:
    """'Sept 2, 2025' / 'May 13, 2025' -> '2025-09-02'. Returns '' if unparsed."""
    m = re.match(r"([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})", stamp.strip())
    if not m:
        return ""
    month = _MONTHS.get(m.group(1).lower().rstrip("."))
    if not month:
        return ""
    return f"{int(m.group(3)):04d}-{month:02d}-{int(m.group(2)):02d}"


def _get(url: str, timeout: int) -> bytes:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=timeout) as resp:
        return resp.read()


def cdx_versions() -> list[dict]:
    rows = json.loads(_get(CDX.format(url=PDF_URL), timeout=60).decode("utf-8"))
    header, *data = rows
    out = []
    for row in data:
        rec = dict(zip(header, row, strict=True))
        if rec.get("statuscode") == "200":
            out.append(rec)
    return out


def archive(versions: list[dict]) -> list[Path]:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    paths = []
    for rec in versions:
        ts = rec["timestamp"]
        path = ARCHIVE_DIR / f"kalshi-fee-schedule-{ts}.pdf"
        paths.append(path)
        if path.exists():
            continue
        url = SNAPSHOT.format(ts=ts, url=PDF_URL)
        blob = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                candidate = _get(url, timeout=180)
            except Exception as exc:  # noqa: BLE001 - transient throttling
                reason = repr(exc)
            else:
                if candidate.startswith(b"%PDF"):
                    blob = candidate
                    break
                reason = f"not a PDF ({len(candidate)} bytes)"
            if attempt < MAX_ATTEMPTS:
                time.sleep(BACKOFF_S * attempt)
            else:
                print(f"  {ts}  GAVE UP after {MAX_ATTEMPTS} attempts: {reason}", file=sys.stderr)
        if blob is None:
            continue
        path.write_bytes(blob)
        print(f"  {ts}  archived {len(blob):,} bytes")
        time.sleep(REQUEST_SPACING_S)
    return paths


def extract_text(path: Path) -> str | None:
    txt_path = path.with_suffix(".txt")
    if txt_path.exists():
        return txt_path.read_text(encoding="utf-8")
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    try:
        text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    except Exception as exc:  # noqa: BLE001 - a corrupt capture must not stop the run
        print(f"  {path.name}  EXTRACT FAILED: {exc!r}", file=sys.stderr)
        return None
    txt_path.write_text(text, encoding="utf-8")
    return text


def summarise(text: str) -> dict:
    flat = " ".join(text.split())
    stamps = _LAST_UPDATED.findall(flat)
    body, _, index_section = flat.partition(_INDEX_HEADING.search(flat).group(0) if _INDEX_HEADING.search(flat) else "\x00")
    split = _MAKER_HEADING.split(body, maxsplit=1)
    general_section, maker_section = (split[0], split[1]) if len(split) == 2 else (body, "")

    def rates(chunk: str) -> tuple[list[str], list[str]]:
        found = []
        for rate, percent, price_dep in _FORMULA.findall(chunk):
            value = float(rate) / 100.0 if percent else float(rate)
            found.append((f"{value:g}", bool(price_dep)))
        return (
            sorted({r for r, price_dep in found if price_dep}),
            sorted({r for r, price_dep in found if not price_dep}),
        )

    taker_quadratic, taker_flat = rates(general_section)
    maker_quadratic, maker_flat = rates(maker_section)
    index_quadratic, _ = rates(index_section)
    # Everything after the maker formula is boilerplate about rebates and the
    # tables; the scope lives in the "Series tickers:" blocks before it.
    series_blocks = [sorted(set(_TICKERS.findall(block))) for block in _SERIES_BLOCK.findall(maker_section)]
    all_series = sorted({t for block in series_blocks for t in block})
    stamp = stamps[0] if stamps else ""
    return {
        "last_updated": stamp,
        "effective_from": _iso_date(stamp),
        "taker_rates_quadratic": taker_quadratic,
        "taker_rates_flat": taker_flat,
        # Half-rate carve-out for S&P500 (INX*) and NASDAQ-100 (NASDAQ100*)
        # market tickers -- present in every version from 2022-09 onward and
        # applying to 18.3% of R1's in-scope universe.
        "index_carveout_rates": index_quadratic,
        "maker_rates_quadratic": maker_quadratic,
        "maker_rates_flat": maker_flat,
        "maker_series": all_series,
        "maker_series_blocks": series_blocks,
        "has_maker_section": bool(maker_section),
        # From the Oct-2025 version Kalshi removed the list from the PDF and
        # deferred to the (client-rendered, un-archivable) web page. That is a
        # real, dated gap in per-series scope -- recorded, not guessed at.
        "scope_deferred_to_web": "kalshi.com/fee-schedule" in maker_section,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true", help="skip downloading; report on what is already archived")
    args = parser.parse_args()

    if args.report:
        paths = sorted(ARCHIVE_DIR.glob("kalshi-fee-schedule-*.pdf"))
    else:
        versions = cdx_versions()
        print(f"CDX: {len(versions)} distinct HTTP-200 captures of {PDF_URL}")
        paths = archive(versions)

    print()
    header = f"{'capture':<16} {'effective':<12} {'taker':<8} {'index':<7} {'maker':<20} scope"
    print(header)
    print("-" * len(header))
    history = []
    prev_signature = None
    for path in sorted(paths):
        if not path.exists():
            continue
        text = extract_text(path)
        if text is None:
            print(f"{path.stem[-14:]:<16} (pypdf unavailable -- archived only)")
            continue
        s = summarise(text)
        s["capture"] = path.stem[-14:]
        s["file"] = path.name
        history.append(s)
        maker = (
            f"{','.join(s['maker_rates_quadratic'])} x P(1-P)" if s["maker_rates_quadratic"]
            else (f"{','.join(s['maker_rates_flat'])} flat" if s["maker_rates_flat"] else "-")
        )
        if s["scope_deferred_to_web"]:
            scope = "(deferred to web page)"
        elif s["maker_series"]:
            scope = f"{len(s['maker_series'])} series"
            if len(s["maker_series_blocks"]) > 1:
                scope += f" in {len(s['maker_series_blocks'])} staged blocks"
        else:
            scope = "(no maker fees)"
        signature = (
            tuple(s["taker_rates_quadratic"]), tuple(s["index_carveout_rates"]),
            tuple(s["maker_rates_quadratic"]), tuple(s["maker_rates_flat"]),
            tuple(s["maker_series"]), s["scope_deferred_to_web"],
        )
        marker = "  <-- CHANGE" if prev_signature is not None and signature != prev_signature else ""
        prev_signature = signature
        print(
            f"{s['capture']:<16} {s['effective_from'] or '-':<12} "
            f"{','.join(s['taker_rates_quadratic']) or '-':<8} "
            f"{','.join(s['index_carveout_rates']) or '-':<7} {maker:<20} {scope}{marker}"
        )

    if history:
        out = ARCHIVE_DIR / "version_history.json"
        out.write_text(json.dumps(history, indent=2, sort_keys=True), encoding="utf-8")
        print()
        print(f"wrote {out} ({len(history)} versions) -- this is what data/fees.yaml is derived from")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
