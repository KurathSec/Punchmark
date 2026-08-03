"""Sidecar binding and agreement rules (PMK-SDC-001/002/003)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from punchmark.archive import read_archive
from punchmark.errors import SidecarError
from punchmark.model import CandidateSet
from punchmark.sidecar import (
    attach,
    default_sidecar_path,
    load_and_attach,
    load_sidecar,
)
from tests.test_archive import full_row, write_archive

CANDIDATES = CandidateSet(routes=("org-b/model-two", "org/model-one"))


def make_archive(tmp_path: Path) -> Path:
    return write_archive(
        tmp_path / "task__org-model-one.jsonl.gz", [full_row("s1"), full_row("s2")]
    )


def sidecar_body(rs, **overrides) -> dict:
    body = {
        "punchmark_schema": "window/v1",
        "archive": rs.source_name,
        "archive_sha256": rs.archive_sha256,
        "route": "org/model-one",
        "task": rs.task,
        "window": {
            "start_utc": "2026-06-01T00:00:00+00:00",
            "end_utc": "2026-06-01T02:00:00+00:00",
        },
        "collector": {},
        "declared_by": "test",
    }
    body.update(overrides)
    return body


def write_sidecar(archive_path: Path, body: dict) -> Path:
    path = default_sidecar_path(archive_path)
    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
    return path


def test_missing_sidecar_refusal_prints_the_exact_shape(tmp_path: Path) -> None:
    path = make_archive(tmp_path)
    rs = read_archive(path, CANDIDATES)
    with pytest.raises(SidecarError) as exc:
        load_and_attach(rs, path)
    message = str(exc.value)
    assert '"punchmark_schema": "window/v1"' in message
    assert rs.archive_sha256 in message


def test_attach_happy_path_resolves_window_and_route(tmp_path: Path) -> None:
    path = make_archive(tmp_path)
    rs = read_archive(path, CANDIDATES)
    write_sidecar(path, sidecar_body(rs))
    windowed = load_and_attach(rs, path)
    assert windowed.window is not None
    assert windowed.window.start_utc == "2026-06-01T00:00:00+00:00"
    assert windowed.route == "org/model-one"


def test_hash_binding(tmp_path: Path) -> None:
    path = make_archive(tmp_path)
    rs = read_archive(path, CANDIDATES)
    write_sidecar(path, sidecar_body(rs, archive_sha256="sha256:" + "0" * 64))
    with pytest.raises(SidecarError, match="does not describe this archive"):
        load_and_attach(rs, path)


def test_route_must_slug_match_filename(tmp_path: Path) -> None:
    path = make_archive(tmp_path)
    rs = read_archive(path, CANDIDATES)
    sc_path = write_sidecar(path, sidecar_body(rs, route="org-b/model-two"))
    with pytest.raises(SidecarError, match="filename is the oracle"):
        attach(rs, load_sidecar(sc_path))


def test_task_must_match_filename(tmp_path: Path) -> None:
    path = make_archive(tmp_path)
    rs = read_archive(path, CANDIDATES)
    sc_path = write_sidecar(path, sidecar_body(rs, task="othertask"))
    with pytest.raises(SidecarError, match="filename is the oracle"):
        attach(rs, load_sidecar(sc_path))


@pytest.mark.parametrize(
    "window",
    [
        {"start_utc": "not-a-date", "end_utc": "2026-06-01T00:00:00+00:00"},
        {"start_utc": "2026-06-01T00:00:00", "end_utc": "2026-06-01T01:00:00+00:00"},
        {"start_utc": "2026-06-02T00:00:00+00:00", "end_utc": "2026-06-01T00:00:00+00:00"},
        {"start_utc": "2026-06-01T00:00:00+00:00"},
    ],
)
def test_window_validation(tmp_path: Path, window: dict) -> None:
    path = make_archive(tmp_path)
    rs = read_archive(path, CANDIDATES)
    sc_path = write_sidecar(path, sidecar_body(rs, window=window))
    with pytest.raises(SidecarError):
        load_sidecar(sc_path)


def test_wrong_schema_and_missing_fields(tmp_path: Path) -> None:
    path = make_archive(tmp_path)
    rs = read_archive(path, CANDIDATES)
    sc_path = write_sidecar(path, {"punchmark_schema": "other/v1"})
    with pytest.raises(SidecarError, match="window/v1"):
        load_sidecar(sc_path)
    body = sidecar_body(rs)
    del body["route"]
    sc_path = write_sidecar(path, body)
    with pytest.raises(SidecarError, match="missing required field"):
        load_sidecar(sc_path)


def test_sidecar_dir_override_for_read_only_checkouts(tmp_path: Path) -> None:
    """Sidecars for archives in a read-only checkout live elsewhere: the sidecar
    directory is searched first, then beside the archive."""
    archive_dir = tmp_path / "checkout"
    archive_dir.mkdir()
    path = write_archive(
        archive_dir / "task__org-model-one.jsonl.gz", [full_row("s1"), full_row("s2")]
    )
    rs = read_archive(path, CANDIDATES)
    sidecar_dir = tmp_path / "sidecars"
    sidecar_dir.mkdir()
    (sidecar_dir / (path.name + ".window.json")).write_text(
        json.dumps(sidecar_body(rs)) + "\n", encoding="utf-8"
    )
    windowed = load_and_attach(rs, path, sidecar_dir)
    assert windowed.window is not None
    with pytest.raises(SidecarError, match="never inferred"):
        load_and_attach(rs, path, tmp_path / "empty")
