"""Check that everything the drafts put in quotation marks is actually a quotation.

WHY
---
On 2026-08-28 an audit against the source PDF found three passages presented as
quotations that the original does not say. They were paraphrases from this
project's spec notes that hardened into quotations somewhere between the spec
and the draft. Two sat in sections arguing about what the original's prose
says -- the worst place to paraphrase inside quotation marks, because there the
exact words are the evidence.

Nothing would have caught that. `verify_paper_figures.py` checks numbers against
artifacts; a misquotation has no artifact. This does the equivalent job for
quoted text.

TWO MODES
---------
Default: every quoted fragment in both drafts must appear in
docs/source_quotes.yaml, either as a recorded quotation or on the exempt list.
This runs anywhere, needs no PDF, and catches a new paraphrase being introduced.

--pdf PATH: additionally re-verify each recorded quotation against the source
PDF itself. Run this whenever a copy is at hand. The PDF is not committed --
it is someone else's paper and this repository is public.

Usage:
    python tools/audit_source_quotes.py
    python tools/audit_source_quotes.py --pdf "C:/path/to/Kalshi.pdf"
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUOTES = PROJECT_ROOT / "docs" / "source_quotes.yaml"
PAPERS = {
    "paper_a": PROJECT_ROOT / "reports" / "final" / "paper_a_composition.md",
    "paper_b": PROJECT_ROOT / "reports" / "final" / "paper_b_replication.md",
}

# Shortest fragment worth treating as a quotation. Below this, quotation marks
# in these drafts are scare quotes or single terms ("significant", "fragile"),
# not attributions.
MIN_QUOTE_CHARS = 18


def norm(s: str) -> str:
    """Collapse whitespace and fold the typography that differs between a PDF
    extract and a Markdown draft. Line breaks are the main offender: a quotation
    wrapped across two lines is the same quotation."""
    s = " ".join(s.split())
    for a, b in (("\u2212", "-"), ("\u2013", "-"), ("\u2014", "-"),
                 ("\u2019", "'"), ("\u201c", '"'), ("\u201d", '"'),
                 ("\u00a0", " ")):
        s = s.replace(a, b)
    return s


def load_pinned() -> tuple[list[dict], list[dict]]:
    """Read the YAML without a YAML dependency: the file is a fixed shape this
    repository controls, and adding PyYAML to run one linter is not worth it."""
    text = open(QUOTES, encoding="utf-8").read()
    quotes, exempt = [], []
    for block, out, key in (("quotes:", quotes, "text"), ("exempt:", exempt, "fragment")):
        if block not in text:
            continue
        section = text[text.index(block) + len(block):]
        nxt = re.search(r"(?m)^\w+:", section)
        section = section[:nxt.start()] if nxt else section
        for item in re.split(r"(?m)^  - ", section)[1:]:
            m = re.search(rf"{key}:\s*(?:>-\s*\n((?:\s{{6,}}.*\n?)+)|(.+))", item)
            if not m:
                continue
            val = m.group(1) or m.group(2)
            out.append({"text": norm(val.strip().strip('"'))})
    return quotes, exempt


def quoted_fragments(path: Path) -> list[str]:
    t = norm(open(path, encoding="utf-8").read())
    return re.findall(rf'"([^"]{{{MIN_QUOTE_CHARS},400}})"', t)


def main() -> int:
    pinned, exempt = load_pinned()
    if not pinned:
        print(f"no quotations parsed from {QUOTES} -- the file's shape changed")
        return 1
    print(f"{len(pinned)} recorded quotation(s), {len(exempt)} exempt fragment(s)")

    failures = []
    for path in PAPERS.values():
        frags = quoted_fragments(path)
        print(f"\n  {path.name}: {len(frags)} quoted fragment(s)")
        for q in frags:
            body = norm(q).rstrip(".").strip()
            if any(e["text"].rstrip(".") in body or body in e["text"] for e in exempt):
                print(f"    n/a       {body[:72]!r}")
                continue
            hit = any(body in p["text"] or p["text"].rstrip(".") in body for p in pinned)
            print(f"    {'recorded ' if hit else 'UNRECORDED'} {body[:72]!r}")
            if not hit:
                failures.append((path.name, body))

    if "--pdf" in sys.argv:
        pdf = Path(sys.argv[sys.argv.index("--pdf") + 1])
        print(f"\n  re-verifying the recorded quotations against {pdf.name}")
        try:
            from pypdf import PdfReader
        except ImportError:
            print("    pypdf not installed; skipping")
        else:
            src = norm("\n".join((p.extract_text() or "") for p in PdfReader(str(pdf)).pages))
            # PDFs hyphenate across line breaks; rejoin so "to- tal" matches "total"
            src = re.sub(r"(\w)- (\w)", r"\1\2", src)
            for p in pinned:
                ok = p["text"] in src
                print(f"    {'ok  ' if ok else 'FAIL'} {p['text'][:70]!r}")
                if not ok:
                    failures.append((pdf.name, p["text"]))

    print()
    if failures:
        print(f"{len(failures)} problem(s):")
        for where, what in failures:
            print(f"  {where}: {what[:100]!r}")
        print("\nA fragment in quotation marks must be the source's words. If it is a "
              "paraphrase, drop the quotation marks; if it is a quotation, record it "
              "in docs/source_quotes.yaml.")
        return 1
    print("every quoted fragment is accounted for")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
