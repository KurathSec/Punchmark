"""Mechanical gate 2: spec coverage.

Every active ruling is cited from code, tests or docs; every ruling-id-shaped
string resolves to a known ruling; ids are unique; the version parses.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from punchmark.errors import SpecError
from punchmark.spec import all_decisions, require, spec_version

ROOT = Path(__file__).parent.parent
ID_SHAPE = re.compile(r"\bPMK-[A-Z]{3,4}-\d{3}\b")


# The citation corpus answers "is this ruling cited by the implementation?", so it
# deliberately excludes generated pages and study write-ups: a ruling cited only from
# a FINDING.md is not cited by the code that implements it.
_CITATION_PATTERNS = ("src/punchmark/**/*.py", "tests/**/*.py", "docs/**/*.md",
                      "*.md", "tools/**/*.py", "validation/**/*.py")
# The resolution corpus answers "does every id-shaped string name a real ruling?",
# which must sweep every text file a reader could follow, study write-ups included.
_RESOLUTION_PATTERNS = _CITATION_PATTERNS + (
    "validation/**/*.md", "calibration/**/*.md", "calibration/**/*.py",
    "src/punchmark/spec/rulings/*.toml", ".github/**/*.md", ".github/**/*.yml",
)
_GENERATED = ("docs/spec/rulings.md",)


def _read(patterns: tuple[str, ...]) -> dict[Path, str]:
    generated = {ROOT / g for g in _GENERATED}
    files: dict[Path, str] = {}
    for pattern in patterns:
        for path in ROOT.glob(pattern):
            if path in generated or not path.is_file():
                continue
            files[path] = path.read_text(encoding="utf-8")
    return files


def _citation_corpus() -> dict[Path, str]:
    return _read(_CITATION_PATTERNS)


def _resolution_corpus() -> dict[Path, str]:
    return _read(_RESOLUTION_PATTERNS)


def test_version_parses() -> None:
    major, minor, patch = spec_version().split(".")
    assert all(part.isdigit() for part in (major, minor, patch))


def test_every_active_ruling_is_cited_outside_its_own_toml() -> None:
    corpus = _citation_corpus()
    uncited = []
    for decision in all_decisions():
        if decision.status != "active":
            continue
        if not any(decision.id in text for text in corpus.values()):
            uncited.append(decision.id)
    assert not uncited, (
        f"active rulings never cited from code, tests or docs: {uncited}; "
        "a ruling nobody cites is either dead or silently violated"
    )


def test_every_id_shaped_string_resolves() -> None:
    """Every PMK-shaped string anywhere a reader could follow must name a real
    ruling. This sweeps wider than the citation corpus, study write-ups included."""
    corpus = _resolution_corpus()
    known = {d.id for d in all_decisions()}
    phantoms = set()
    for text in corpus.values():
        for match in ID_SHAPE.findall(text):
            if match not in known:
                phantoms.add(match)
    assert not phantoms, f"ruling-shaped ids that resolve to nothing: {sorted(phantoms)}"


def test_require_refuses_unknown() -> None:
    phantom = "-".join(("PMK", "ZZZ", "999"))  # assembled so the scanner ignores it
    with pytest.raises(SpecError, match="unknown spec ruling"):
        require(phantom)


def test_require_returns_active_rulings() -> None:
    decision = require("PMK-CRT-002")
    assert decision.status == "active"
    assert "weights" in decision.text
