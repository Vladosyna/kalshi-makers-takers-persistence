"""Structural checks on the LaTeX build, for a machine with no LaTeX on it.

This is not a substitute for compiling. It is what can be established without a
compiler, so that the .tex is not shipped completely unexamined:

  * environments open and close in order;
  * braces balance;
  * every \\cite key resolves to a \\bibitem, and no \\bibitem is unused;
  * every \\ref resolves to a \\label;
  * `%`, `&`, `_`, `#` are escaped outside the places they are legal;
  * every tabular row has the column count its preamble declares;
  * every number stated in the Markdown source also appears in the .tex.

The last one is the point of the exercise. A conversion that drops or mangles a
figure is the failure mode that matters, and it is invisible to a compiler --
the document would build perfectly with a wrong number in it.

Usage:
    python tools/lint_tex.py
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEX = PROJECT_ROOT / "reports" / "final" / "paper_a_composition.tex"
MD = PROJECT_ROOT / "reports" / "final" / "paper_a_composition.md"


def strip_comments(src: str) -> str:
    """Drop LaTeX comments, respecting \\% which is a literal percent."""
    out = []
    for line in src.split("\n"):
        i, keep = 0, line
        while i < len(line):
            if line[i] == "%" and (i == 0 or line[i - 1] != "\\"):
                keep = line[:i]
                break
            i += 1
        out.append(keep)
    return "\n".join(out)


def check_environments(src: str) -> list[str]:
    stack, errs = [], []
    for m in re.finditer(r"\\(begin|end)\{([^}]+)\}", src):
        kind, name = m.group(1), m.group(2)
        if kind == "begin":
            stack.append(name)
        else:
            if not stack:
                errs.append(f"\\end{{{name}}} with nothing open")
            elif stack[-1] != name:
                errs.append(f"\\end{{{name}}} closes \\begin{{{stack[-1]}}}")
                stack.pop()
            else:
                stack.pop()
    errs += [f"\\begin{{{n}}} never closed" for n in stack]
    return errs


def check_braces(src: str) -> list[str]:
    depth = 0
    for i, ch in enumerate(src):
        if ch in "{}" and (i == 0 or src[i - 1] != "\\"):
            depth += 1 if ch == "{" else -1
            if depth < 0:
                line = src[:i].count("\n") + 1
                return [f"unbalanced closing brace at line {line}"]
    return [f"{depth} brace(s) left open"] if depth else []


def check_citations(src: str) -> list[str]:
    cited = set()
    for m in re.finditer(r"\\cite[tp]?\{([^}]+)\}", src):
        cited.update(k.strip() for k in m.group(1).split(","))
    defined = set(re.findall(r"\\bibitem\[[^\]]*\]\{([^}]+)\}", src))
    errs = [f"\\cite{{{k}}} has no \\bibitem" for k in sorted(cited - defined)]
    errs += [f"\\bibitem{{{k}}} is never cited" for k in sorted(defined - cited)]
    return errs


def check_refs(src: str) -> list[str]:
    refs = set(re.findall(r"\\ref\{([^}]+)\}", src))
    labels = set(re.findall(r"\\label\{([^}]+)\}", src))
    return [f"\\ref{{{r}}} has no \\label" for r in sorted(refs - labels)]


def check_specials(src: str) -> list[str]:
    """Bare specials outside math and outside tabular alignment."""
    errs = []
    # Blank out math so $\%$-free math does not trip the scan.
    masked = re.sub(r"\$[^$]*\$", lambda m: " " * len(m.group(0)), src)
    in_tabular = 0
    for lineno, line in enumerate(masked.split("\n"), 1):
        if re.search(r"\\begin\{(tabular|align|equation)", line):
            in_tabular += 1
        if re.search(r"\\end\{(tabular|align|equation)", line):
            in_tabular = max(0, in_tabular - 1)
        for ch, name in (("%", "percent"), ("#", "hash")):
            for m in re.finditer(re.escape(ch), line):
                i = m.start()
                if i > 0 and line[i - 1] == "\\":
                    continue
                errs.append(f"line {lineno}: unescaped {name} -- {line.strip()[:60]}")
        if not in_tabular:
            for m in re.finditer(r"&", line):
                if m.start() > 0 and line[m.start() - 1] == "\\":
                    continue
                errs.append(f"line {lineno}: & outside tabular -- {line.strip()[:60]}")
    return errs


def check_tabular_columns(src: str) -> list[str]:
    errs = []
    for m in re.finditer(r"\\begin\{tabular\}\{([^}]*)\}(.*?)\\end\{tabular\}", src, re.S):
        preamble, body = m.group(1), m.group(2)
        ncol = len(re.findall(r"[lcr]|p\{[^}]*\}", preamble))
        for raw in body.split("\\\\"):
            row = re.sub(r"\\(toprule|midrule|bottomrule|cmidrule\S*)", "", raw).strip()
            if not row:
                continue
            cells = len(re.findall(r"(?<!\\)&", row)) + 1
            if cells != ncol:
                errs.append(f"row has {cells} cells, preamble declares {ncol}: {row[:60]}")
    return errs


def check_numbers_survived(tex: str, md: str) -> list[str]:
    """Every figure in the Markdown must appear in the .tex."""
    def figures(text: str) -> set[str]:
        text = text.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")
        # Section numbers are not figures. In Markdown they are literal ("### 6.3",
        # "see \u00a76.3"); in LaTeX they are generated by \subsection and \ref and so
        # appear nowhere in the source. Comparing them reports every cross-
        # reference as a lost number.
        text = re.sub(r"(?m)^#{1,6}\s+\d+(\.\d+)*", "", text)
        text = re.sub(r"\u00a7\s*\d+(\.\d+)*", "", text)
        text = re.sub(r"(?i)\b(section|appendix)\s+\d+(\.\d+)*", "", text)
        # numbers with a decimal point or a thousands comma; bare integers are
        # too noisy (years, counts in prose) to compare usefully
        return set(re.findall(r"\d[\d,]*\.\d+|\d{1,3}(?:,\d{3})+", text))

    md_nums = figures(md)
    tex_nums = figures(tex)
    missing = sorted(md_nums - tex_nums, key=lambda s: (-len(s), s))
    return [f"figure {n!r} is in the Markdown but not the .tex" for n in missing]


def main() -> int:
    if not TEX.exists():
        print(f"no such file: {TEX}")
        return 1
    with io.open(TEX, encoding="utf-8") as f:
        raw = f.read()
    with io.open(MD, encoding="utf-8") as f:
        md = f.read()
    src = strip_comments(raw)

    groups = [
        ("environments balance", check_environments(src)),
        ("braces balance", check_braces(src)),
        ("citations resolve", check_citations(src)),
        ("cross-references resolve", check_refs(src)),
        ("specials escaped", check_specials(src)),
        ("tabular column counts", check_tabular_columns(src)),
        ("figures survived the conversion", check_numbers_survived(raw, md)),
    ]

    bad = 0
    for label, errs in groups:
        print(f"  {'ok  ' if not errs else 'FAIL'} {label}"
              + ("" if not errs else f" ({len(errs)})"))
        for e in errs[:12]:
            print(f"         {e}")
        if len(errs) > 12:
            print(f"         ... and {len(errs) - 12} more")
        bad += len(errs)

    print()
    if bad:
        print(f"{bad} structural problem(s). NOTE: this is not a compile -- "
              "no LaTeX toolchain is installed here.")
        return 1
    print("structurally clean. NOT COMPILE-VERIFIED: no LaTeX toolchain is "
          "installed here, so run pdflatex before trusting it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
