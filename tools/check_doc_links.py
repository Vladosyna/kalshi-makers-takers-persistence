"""Check that every relative link in the Markdown docs resolves -- case included.

WHY CASE
--------
This machine's filesystem is case-insensitive and GitHub's is not. A link
written as `Claude.md` to a file named `CLAUDE.md` opens fine locally and 404s
for every reader. Five such links sat in the README until 2026-08-28, all
pointing at the repository's own central document.

So existence is not enough: the final path segment must match the directory
entry exactly.

Usage:
    python tools/check_doc_links.py
"""

from __future__ import annotations

import os
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules"}


def markdown_files() -> list[Path]:
    out = []
    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        out += [Path(root) / f for f in files if f.endswith(".md")]
    return sorted(out)


def check(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errs = []
    for m in re.finditer(r"\]\(([^)]+)\)", text):
        target = m.group(1).split("#")[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:", "<")):
            continue
        resolved = (path.parent / target).resolve()
        if not resolved.exists():
            errs.append(f"missing: {target}")
            continue
        # Case check: compare the name against the real directory entry.
        try:
            entries = os.listdir(resolved.parent)
        except OSError:
            continue
        if resolved.name and resolved.name not in entries:
            actual = next((e for e in entries if e.lower() == resolved.name.lower()), "?")
            errs.append(f"case mismatch: {target} -- on disk it is {actual!r}")
    return errs


def main() -> int:
    total, bad = 0, 0
    for md in markdown_files():
        errs = check(md)
        total += 1
        if errs:
            rel = md.relative_to(PROJECT_ROOT)
            print(f"  {rel}")
            for e in errs:
                print(f"      {e}")
            bad += len(errs)
    print(f"\n{total} Markdown file(s) checked, {bad} broken link(s)")
    if bad:
        print("A link that resolves on a case-insensitive filesystem still 404s on GitHub.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
