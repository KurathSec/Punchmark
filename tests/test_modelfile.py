"""Fitted-model file: byte-stable roundtrip, tamper detection (PMK-EMIT-001/002)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from punchmark.errors import ModelFileError
from punchmark.modelfile import read_model, write_model


def test_write_read_write_is_byte_identical(fitted_doc, tmp_path: Path) -> None:
    p1 = tmp_path / "a.pmk-model.json"
    write_model(p1, fitted_doc)
    doc = read_model(p1)
    p2 = tmp_path / "b.pmk-model.json"
    write_model(p2, doc)
    assert p1.read_bytes() == p2.read_bytes()
    assert doc.model_id == fitted_doc.model_id
    assert doc.tasks == fitted_doc.tasks


def test_edited_model_file_fails_its_own_hash(fitted_doc, tmp_path: Path) -> None:
    path = tmp_path / "m.pmk-model.json"
    write_model(path, fitted_doc)
    raw = json.loads(path.read_text())
    raw["operating_points"][0]["threshold"] = -99.0
    path.write_text(json.dumps(raw, sort_keys=True, indent=2) + "\n")
    with pytest.raises(ModelFileError, match="edited after it was written"):
        read_model(path)


def test_unknown_schema_and_malformed_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "x.pmk-model.json"
    path.write_text('{"punchmark_schema": "model/v99"}\n')
    with pytest.raises(ModelFileError, match="not a model/v1"):
        read_model(path)
    path.write_text('{"punchmark_schema": "model/v1", "model_id": "pmk-m-x"}\n')
    with pytest.raises(ModelFileError, match="malformed"):
        read_model(path)
    path.write_text("not json\n")
    with pytest.raises(ModelFileError, match="not JSON"):
        read_model(path)
