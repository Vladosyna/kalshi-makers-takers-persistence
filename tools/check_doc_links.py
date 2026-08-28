"""Check that every relative link in the Markdown docs resolves -- case included.

WHY CASE
--------
This machine's filesystem is case-insensitive and GitHub's is not, so a link
whose case is wrong opens locally and 404s for every reader.

WHY IT ASKS GIT, NOT THE FILESYSTEM
-----------------------------------
The first version of this checker read the working directory, and that made it
give different answers on different machines -- the exact bug class it exists to
catch. It passed on Windows and failed in CI, and the CI run was right: git was
tracking `Claude.md` while the Windows filesystem showed `CLAUDE.md`, with
`core.ignorecase=true` hiding the difference from git and from me. It also meant
the diagnosis behind that first version was backwards -- the README's original
links were correct and "fixing" them broke them.

GitHub serves what git tracks, so git's index is the only authority worth
consulting. (The file has since been renamed in git to `CLAUDE.md`, which is
what the local filesystem and Claude Code's own convention both expect.)

Usage:
    python tools/check_doc_links.py
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def tracked_paths() -> set[str] | None:
    """Every path git tracks, as forward-slash strings relative to the root.

    None means git could not answer -- an export with no .git directory, say --
    and the caller degrades to a filesystem check while saying so."""
    try:
        out = subprocess.run(
            ["git", "-C", str(PROJECT_ROOT), "ls-files"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return {line for line in out.split("\n") if line}


def markdown_files(tracked: set[str] | None) -> list[Path]:
    if tracked is not None:
        return sorted(PROJECT_ROOT / p for p in tracked if p.endswith(".md"))
    return sorted(
        p for p in PROJECT_ROOT.rglob("*.md")
        if not any(part in {".git", ".venv", "__pycache__", ".pytest_cache"} for part in p.parts)
    )


def repo_relative(md: Path, target: str) -> str | None:
    """Resolve a link to a repo-relative posix path LEXICALLY.

    Path.resolve() must not be used here. On Windows it consults the filesystem
    and hands back the on-disk spelling, so a link written `Claude.md` comes
    back as `CLAUDE.md` and the case mismatch this tool exists to find is erased
    before it can be compared. The first version did exactly that and reported
    a clean bill of health on a link that was wrong.
    """
    base = md.parent.relative_to(PROJECT_ROOT).as_posix()
    joined = f"{base}/{target}" if base != "." else target
    parts: list[str] = []
    for seg in joined.replace("\\", "/").split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            if not parts:
                return None
            parts.pop()
        else:
            parts.append(seg)
    return "/".join(parts)


def check(path: Path, tracked: set[str] | None) -> list[str]:
    errs = []
    for m in re.finditer(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
        target = m.group(1).split("#")[0].strip()
        if not target or target.startswith(("http://", "https://", "mailto:", "<")):
            continue
        rel = repo_relative(path, target)
        if rel is None:
            errs.append(f"points outside the repository: {target}")
            continue

        if tracked is None:
            if not (PROJECT_ROOT / rel).exists():
                errs.append(f"missing: {target}")
            continue

        # A link to a directory is fine if git tracks anything beneath it.
        if rel in tracked or any(t.startswith(rel.rstrip("/") + "/") for t in tracked):
            continue

        near = next((t for t in tracked if t.lower() == rel.lower()), None)
        if near:
            errs.append(f"case mismatch: {target} -- git tracks {near!r}")
        else:
            errs.append(f"not tracked by git: {target}")
    return errs


def main() -> int:
    tracked = tracked_paths()
    if tracked is None:
        print("git is unavailable -- falling back to a filesystem check, which "
              "cannot detect case mismatches on this platform")

    total, bad = 0, 0
    for md in markdown_files(tracked):
        if not md.exists():
            continue
        errs = check(md, tracked)
        total += 1
        if errs:
            print(f"  {md.relative_to(PROJECT_ROOT)}")
            for e in errs:
                print(f"      {e}")
            bad += len(errs)

    print(f"\n{total} Markdown file(s) checked, {bad} broken link(s)")
    if bad:
        print("GitHub serves what git tracks. A link that resolves in your working "
              "directory can still 404 for every reader.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
