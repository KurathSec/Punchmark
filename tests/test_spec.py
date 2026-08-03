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


def _citation_corpus() -> dict[Path, str]:
    files: dict[Path, str] = {}
    generated = ROOT / "docs" / "spec" / "rulings.md"  # cites everything by construction
    for pattern in ("src/punchmark/**/*.py", "tests/**/*.py", "docs/**/*.md",
                    "*.md", "tools/**/*.py", "validation/**/*.py"):
        for path in ROOT.glob(pattern):
            if path == generated:
                continue
            files[path] = path.read_text(encoding="utf-8")
    return files


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
    corpus = _citation_corpus()
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
