"""Build the submission PDF from the LaTeX source, and check what came out.

WHY A SCRIPT
------------
Three pdflatex passes in a scratch directory, then a check that the rendered PDF
actually contains the numbers it is supposed to. Doing that by hand is how a
paper gets submitted with a stale figure in it: the .tex compiles, the PDF looks
right, and nobody re-reads twenty pages of coefficients.

The build runs in a temporary directory so the fifteen auxiliary files LaTeX
produces never reach the repository. Only the PDF is copied back.

WHAT THE CHECK COVERS
---------------------
Every headline figure, read from the analysis artifacts and searched for in the
PDF's extracted text -- the same artifact-first direction as
verify_paper_figures.py, one step further down the pipeline. Plus the two
declarations Elsevier requires, the exploratory label that must travel with the
event-study result, and the absence of any AWAITING placeholder.

Requires a TeX installation with elsarticle, lmodern and microtype. MiKTeX
fetches those on first use if AutoInstall is on.

Usage:
    python tools/build_paper_pdf.py
    python tools/build_paper_pdf.py --check-only    # verify the committed PDF
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEX = PROJECT_ROOT / "reports" / "final" / "paper_a_composition.tex"
PDF = PROJECT_ROOT / "reports" / "final" / "paper_a_composition.pdf"
PASSES = 3  # frontmatter, cross-references, then the table of contents settling


def _load(name: str) -> dict:
    with open(PROJECT_ROOT / "reports" / name, encoding="utf-8") as f:
        return json.load(f)


def expected_figures() -> dict[str, str]:
    r1, lock = _load("r1/r1_report.json"), _load("r2/verdict_lock.json")
    esc, ev = _load("r2/escalation_run.json"), _load("r2/event_study.json")
    mt, dec = r1["maker_taker_split"], lock["decomposition"]["fee"]
    clean, twfe = lock["maker_fee_did"]["clean_controls"], lock["maker_fee_did"]["twfe"]
    fills = sum(e["trade_count"] for e in r1["taker_field_population_by_era"].values())
    return {
        "total fills": f"{fills:,}",
        "R2 in-scope markets": f"{lock['r2_filters']['passed']:,}",
        "R1 in-scope contracts": f"{r1['in_scope_markets']:,}",
        "maker return >=50c": f"+{mt['maker_return_50c_plus']:.2%}",
        "taker return": f"{mt['taker_return']:.2%}",
        "within term": f"+{dec['within']:.4f}",
        "between term": f"+{dec['between']:.4f}",
        "clean-controls delta": f"{clean['delta_did']:.4f}",
        "clean-controls se": f"{clean['delta_did_se']:.4f}",
        "TWFE delta": f"+{twfe['delta_did']:.4f}",
        "treated series": f"{twfe['n_treated_series']:,}",
        "event clusters": f"{twfe['n_clusters']:,}",
        "pre-trend p": f"p = {ev['pretrend_p']:.2f}",
        "post-trend p": f"p = {ev['posttrend_p']:.3f}",
        "maker margin, gross": f"+{esc['maker_margin']['layer_a']:.2%}",
        "maker margin, fee held constant": f"+{esc['maker_margin']['layer_c']:.2%}",
        "event study k=+4": f"{ev['coefficients']['4']:.4f}",
        "reference slope": f"{lock['psi_bar_r1']:.4f}",
    }


def pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    raw = "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    flat = " ".join(raw.split())
    for a, b in (("−", "-"), ("–", "-"), ("—", "-"), (" ", " ")):
        flat = flat.replace(a, b)
    return flat


def build() -> Path:
    tex = shutil.which("pdflatex")
    if not tex:
        print("pdflatex is not on PATH. Install a TeX distribution (MiKTeX or "
              "TeX Live) with elsarticle, lmodern and microtype.")
        raise SystemExit(1)

    with tempfile.TemporaryDirectory(prefix="paper-pdf-") as tmp:
        work = Path(tmp)
        shutil.copy2(TEX, work / TEX.name)
        for i in range(1, PASSES + 1):
            proc = subprocess.run(
                [tex, "-interaction=nonstopmode", TEX.name],
                cwd=work, capture_output=True, text=True,
            )
            built = work / TEX.with_suffix(".pdf").name
            if not built.exists() and i == PASSES:
                log = (work / TEX.with_suffix(".log").name)
                errs = [ln for ln in log.read_text(encoding="utf-8", errors="replace").split("\n")
                        if ln.startswith("!")] if log.exists() else []
                print("pdflatex produced no PDF:")
                for e in errs[:10]:
                    print(f"  {e}")
                if not errs:
                    print(proc.stdout[-1500:])
                raise SystemExit(1)

        log = (work / TEX.with_suffix(".log").name).read_text(encoding="utf-8", errors="replace")
        stats = {
            "errors": sum(1 for ln in log.split("\n") if ln.startswith("!")),
            "undefined refs": log.count("undefined"),
            "overfull boxes": log.count("Overfull"),
        }
        print(f"  built with {PASSES} passes: " + ", ".join(f"{k} {v}" for k, v in stats.items()))
        shutil.copy2(work / TEX.with_suffix(".pdf").name, PDF)

    return PDF


def check(path: Path) -> int:
    text = pdf_text(path)
    bad = []
    for label, needle in expected_figures().items():
        if needle not in text:
            bad.append(f"{label}: expected {needle!r} in the PDF")

    required = [
        ("Declaration of interest", True),
        ("Declaration of Generative AI", True),
        ("read as exploratory", True),
        ("AWAITING", False),
    ]
    for needle, want in required:
        if (needle in text) is not want:
            bad.append(f"{needle!r}: {'missing' if want else 'still present'}")

    total = len(expected_figures()) + len(required)
    print(f"  {total - len(bad)}/{total} checks passed against the rendered PDF")
    for b in bad:
        print(f"    FAIL {b}")
    return 1 if bad else 0


def main() -> int:
    if "--check-only" not in sys.argv:
        build()
    elif not PDF.exists():
        print(f"no PDF at {PDF}")
        return 1
    size = PDF.stat().st_size
    print(f"  {PDF.relative_to(PROJECT_ROOT)} -- {size / 1024:.0f} KB")
    return check(PDF)


if __name__ == "__main__":
    raise SystemExit(main())
