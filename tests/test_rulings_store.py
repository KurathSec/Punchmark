"""Append-only store invariants (PMK-RUL-003/004)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from punchmark.canonical import content_id
from punchmark.errors import RulingError
from punchmark.model import Ruling, Verdict, Window
from punchmark.rulings import append, find, ruling_body, verify


def make_ruling(**overrides) -> Ruling:
    base = Ruling(
        ruling_id="",
        verdict=Verdict.SAME_PRODUCER,
        route="r/a",
        task="t",
        window=Window("2026-01-01T00:00:00+00:00", "2026-01-01T01:00:00+00:00"),
        archive_sha256="sha256:" + "1" * 64,
        model_id="pmk-m-0000000000000000",
        detector_id="trivial",
        detector_version="1",
        candidate_set_id="pmk-cs-0000000000000000",
        candidates=("r/a", "r/b"),
        far=0.01,
        threshold=-0.5,
        calibration_sha256="pmk-cor-0000000000000000",
        spec_version="0.1.0",
        statistic=0.25,
        per_candidate={"r/a": 0.25, "r/b": -0.25},
        n_items=50,
        n_clusters=10,
        n_stub_rows=0,
        rho_target=1.0,
        rho_min=0.3,
    )
    draft = replace(base, **overrides)
    rid = content_id(ruling_body(draft), "ruling_id", "pmk-r")
    return replace(draft, ruling_id=rid)


def test_append_verify_find_roundtrip(tmp_path: Path) -> None:
    store = tmp_path / "rulings.jsonl"
    r1 = make_ruling()
    append(store, r1)
    r2 = make_ruling(route="r/b", verdict=Verdict.SUBSTITUTED, statistic=-0.9)
    append(store, r2)
    bodies = verify(store)
    assert [b["ruling_id"] for b in bodies] == [r1.ruling_id, r2.ruling_id]
    assert find(store, r2.ruling_id)["verdict"] == "SUBSTITUTED"


def test_duplicate_append_refused(tmp_path: Path) -> None:
    store = tmp_path / "rulings.jsonl"
    r = make_ruling()
    append(store, r)
    with pytest.raises(RulingError, match="already in the store"):
        append(store, r)


def test_edited_line_is_tamper(tmp_path: Path) -> None:
    store = tmp_path / "rulings.jsonl"
    append(store, make_ruling())
    body = json.loads(store.read_text().splitlines()[0])
    body["verdict"] = "SUBSTITUTED"  # the edit
    store.write_text(json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(RulingError, match="edited after it was appended"):
        verify(store)


def test_supersedes_must_name_an_earlier_ruling(tmp_path: Path) -> None:
    store = tmp_path / "rulings.jsonl"
    ghost = make_ruling(supersedes="pmk-r-doesnotexist00")
    with pytest.raises(RulingError, match="not in the store"):
        append(store, ghost)
    r1 = make_ruling()
    append(store, r1)
    r2 = make_ruling(supersedes=r1.ruling_id, statistic=0.3)
    append(store, r2)
    assert verify(store)[1]["supersedes"] == r1.ruling_id


def test_ruling_id_pins_the_contractual_four(tmp_path: Path) -> None:
    """PMK-RUL-004: detector version, candidate set, operating point, calibration
    hash -- changing any one changes the id."""
    base = make_ruling()
    assert make_ruling().ruling_id == base.ruling_id
    for change in (
        {"detector_version": "2"},
        {"candidate_set_id": "pmk-cs-1111111111111111"},
        {"far": 0.05},
        {"threshold": -0.4},
        {"calibration_sha256": "pmk-cor-1111111111111111"},
    ):
        assert make_ruling(**change).ruling_id != base.ruling_id


def test_missing_store_verifies_empty(tmp_path: Path) -> None:
    assert verify(tmp_path / "absent.jsonl") == []
    with pytest.raises(RulingError, match="not found"):
        find(tmp_path / "absent.jsonl", "pmk-r-x")
