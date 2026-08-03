"""The native reader's tolerance table, pinned (PMK-ARC-001/002/003)."""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from punchmark.archive import (
    modal_k,
    parse_archive_name,
    ragged_rows,
    read_archive,
    route_for_slug,
)
from punchmark.errors import ArchiveError
from punchmark.model import CandidateSet

CANDIDATES = CandidateSet(routes=("org-b/model-two", "org/model-one"))


def write_archive(path: Path, rows: list[dict]) -> Path:
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    return path


def full_row(sample: str = "s1", **overrides) -> dict:
    row = {
        "sample": sample,
        "variant": "base",
        "profile": "minimal",
        "language": "python",
        "intrinsic": {"n_ops": 2},
        "tier": "A",
        "raw_outputs": ["hello", "hello"],
    }
    row.update(overrides)
    return row


def test_filename_parsing() -> None:
    task, slug = parse_archive_name(Path("comprehend__org-model-one.jsonl.gz"))
    assert task == "comprehend"
    assert slug == "org-model-one"


@pytest.mark.parametrize(
    "name",
    ["noext.txt", "nosep.jsonl.gz", "__empty-task.jsonl.gz", "task__.jsonl.gz"],
)
def test_filename_refusals(name: str) -> None:
    with pytest.raises(ArchiveError):
        parse_archive_name(Path(name))


def test_slug_resolves_only_through_candidates() -> None:
    assert route_for_slug("org-model-one", CANDIDATES) == "org/model-one"
    assert route_for_slug("org-b-model-two", CANDIDATES) == "org-b/model-two"
    with pytest.raises(ArchiveError, match="not in the candidate set"):
        route_for_slug("unknown-slug", CANDIDATES)


def test_reads_full_and_tierless_rows(tmp_path: Path) -> None:
    row_no_tier = {k: v for k, v in full_row("s2").items() if k != "tier"}
    path = write_archive(
        tmp_path / "task__org-model-one.jsonl.gz", [full_row("s1"), row_no_tier]
    )
    rs = read_archive(path, CANDIDATES)
    assert rs.route == "org/model-one"
    assert rs.task == "task"
    assert [r.tier for r in rs.rows] == ["A", None]
    assert rs.n_stub_rows == 0
    assert len(rs.valid_rows) == 2


def test_without_candidates_the_slug_stands(tmp_path: Path) -> None:
    path = write_archive(tmp_path / "task__org-model-one.jsonl.gz", [full_row()])
    rs = read_archive(path)
    assert rs.route == "org-model-one"


def test_stub_rows_are_recognized_and_counted(tmp_path: Path) -> None:
    stub = {"sample": "s9", "profile": "max", "language": "cpp"}
    path = write_archive(
        tmp_path / "task__org-model-one.jsonl.gz", [full_row(), stub]
    )
    rs = read_archive(path, CANDIDATES)
    assert rs.n_stub_rows == 1
    assert len(rs.valid_rows) == 1
    stub_row = rs.rows[1]
    assert stub_row.is_stub
    assert stub_row.raw_outputs == ()
    assert stub_row.variant is None and stub_row.tier is None and stub_row.intrinsic is None


@pytest.mark.parametrize(
    "mutation",
    [
        {"extra_key": 1},
        {"raw_outputs": []},
        {"raw_outputs": ["ok", 3]},
        {"raw_outputs": "not-a-list"},
        {"intrinsic": {"n_ops": "two"}},
        {"intrinsic": [1, 2]},
    ],
)
def test_malformed_rows_are_typed_refusals(tmp_path: Path, mutation: dict) -> None:
    path = write_archive(
        tmp_path / "task__org-model-one.jsonl.gz", [full_row(**mutation)]
    )
    with pytest.raises(ArchiveError):
        read_archive(path, CANDIDATES)


def test_partial_stub_is_refused_not_guessed(tmp_path: Path) -> None:
    # A row missing raw_outputs but carrying MORE than the stub triple is neither
    # schema; it must refuse, not silently become a stub (PMK-ARC-002).
    almost = {"sample": "s1", "profile": "minimal", "language": "python", "tier": "A"}
    path = write_archive(tmp_path / "task__org-model-one.jsonl.gz", [almost])
    with pytest.raises(ArchiveError, match="neither row schema"):
        read_archive(path, CANDIDATES)


def test_duplicate_item_identity_refused(tmp_path: Path) -> None:
    path = write_archive(
        tmp_path / "task__org-model-one.jsonl.gz", [full_row("s1"), full_row("s1")]
    )
    with pytest.raises(ArchiveError, match="duplicate item"):
        read_archive(path, CANDIDATES)


def test_not_json_and_empty_archive(tmp_path: Path) -> None:
    bad = tmp_path / "task__org-model-one.jsonl.gz"
    with gzip.open(bad, "wt", encoding="utf-8") as fh:
        fh.write("{not json\n")
    with pytest.raises(ArchiveError, match="not JSON"):
        read_archive(bad, CANDIDATES)
    empty = tmp_path / "empty__org-model-one.jsonl.gz"
    write_archive(empty, [])
    with pytest.raises(ArchiveError, match="empty archive"):
        read_archive(empty, CANDIDATES)


def test_ragged_k_tolerated_and_counted(tmp_path: Path) -> None:
    rows = [
        full_row("s1"),
        full_row("s2", raw_outputs=["only-one"]),
        full_row("s3"),
    ]
    path = write_archive(tmp_path / "task__org-model-one.jsonl.gz", rows)
    rs = read_archive(path, CANDIDATES)
    assert modal_k(rs) == 2
    assert ragged_rows(rs) == 1
