"""The documentation link checker must actually be able to fail.

Its first version could not. It resolved link targets with Path.resolve(),
which on Windows consults the filesystem and returns the on-disk spelling, so
`Claude.md` came back as `CLAUDE.md` and the case mismatch the tool exists to
find was erased before any comparison happened. It reported a clean repository
while pointing at a file whose tracked name was different, and only a
deliberate probe of a known-bad link revealed it.

So these tests are not about the repository's links. They are about whether the
checker distinguishes the cases it claims to.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from check_doc_links import check, main, repo_relative, tracked_paths  # noqa: E402


@pytest.fixture(scope="module")
def tracked():
    t = tracked_paths()
    if t is None:
        pytest.skip("git is unavailable, so the case checks cannot run")
    return t


def _probe(tmp_path: Path, link: str, tracked) -> list[str]:
    """Write one link into a Markdown file that sits at the repository root.

    The file must live at the root, because link targets are resolved relative
    to the file's own directory.
    """
    md = PROJECT_ROOT / "_test_linkcheck_probe.md"
    md.write_text(link, encoding="utf-8")
    try:
        return check(md, tracked)
    finally:
        md.unlink(missing_ok=True)


@pytest.mark.parametrize(
    "link,should_fail,reason",
    [
        ("[x](CLAUDE.md)", False, "exact tracked name"),
        ("[x](Claude.md)", True, "case mismatch -- the whole point"),
        ("[x](claude.md)", True, "case mismatch, lowered"),
        ("[x](Docs/known_gaps.md)", True, "case mismatch in a directory segment"),
        ("[x](docs/known_gaps.md)", False, "exact nested name"),
        ("[x](docs/does_not_exist.md)", True, "untracked target"),
        ("[x](reports/final/)", False, "directory with tracked files under it"),
        ("[x](../CLAUDE.md)", True, "escapes the repository"),
        ("[x](https://example.com/Claude.md)", False, "external URL is not ours to check"),
        ("[x](mailto:someone@example.com)", False, "mailto is not a path"),
        ("[x](CLAUDE.md#a-section)", False, "anchors are stripped before resolving"),
    ],
)
def test_link_shapes(tmp_path, tracked, link, should_fail, reason):
    errs = _probe(tmp_path, link, tracked)
    assert bool(errs) is should_fail, f"{reason}: got {errs}"


def test_case_mismatch_names_the_tracked_spelling(tmp_path, tracked):
    """The message has to say what the right name is, or the reader has to go
    looking for it -- and the whole failure mode is that the wrong name looks
    right."""
    errs = _probe(tmp_path, "[x](Claude.md)", tracked)
    assert errs and "CLAUDE.md" in errs[0]
    assert "case mismatch" in errs[0]


def test_resolution_is_lexical_not_filesystem():
    """repo_relative must not consult the filesystem. If it did, this would come
    back as the on-disk spelling on a case-insensitive system."""
    md = PROJECT_ROOT / "probe.md"
    assert repo_relative(md, "Claude.md") == "Claude.md"
    assert repo_relative(md, "./docs/../CLAUDE.md") == "CLAUDE.md"
    assert repo_relative(md, "docs/known_gaps.md") == "docs/known_gaps.md"
    assert repo_relative(md, "../outside.md") is None


def test_repository_links_all_resolve():
    """The repository's own documentation, checked the way CI checks it."""
    assert main() == 0
