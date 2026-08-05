"""The gate matrix (PMK-GTE-001/002/003)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from punchmark.canonical import canonical_json
from punchmark.errors import GateError
from punchmark.gate import baseline_body, evaluate, read_baseline
from punchmark.model import OperatingPoint
from punchmark.spec import spec_version


def write_baseline(path: Path, body: dict) -> Path:
    path.write_text(canonical_json(body))
    return path


def test_identical_model_passes(fitted_doc, tmp_path: Path) -> None:
    baseline = write_baseline(tmp_path / "b.json", baseline_body(fitted_doc))
    result = evaluate(fitted_doc, read_baseline(baseline), spec_version())
    assert result.exit_code == 0
    assert any("PASS" in line for line in result.lines)


def _moved(doc):
    points = list(doc.operating_points)
    points[0] = OperatingPoint(
        task=points[0].task,
        route=points[0].route,
        far=points[0].far,
        m=points[0].m,
        threshold=points[0].threshold - 1.0,
        n_null=points[0].n_null,
    )
    return replace(doc, operating_points=tuple(points))


def test_moved_operating_point_without_bump_fails(fitted_doc, tmp_path: Path) -> None:
    baseline = write_baseline(tmp_path / "b.json", baseline_body(fitted_doc))
    result = evaluate(_moved(fitted_doc), read_baseline(baseline), spec_version())
    assert result.exit_code == 1
    assert any("moved without a declared" in line for line in result.lines)
    # every FAIL restates the scope note
    assert any("model weights" in line for line in result.lines)


def test_moved_operating_point_with_detector_bump_passes(
    fitted_doc, tmp_path: Path
) -> None:
    baseline = write_baseline(tmp_path / "b.json", baseline_body(fitted_doc))
    moved = replace(_moved(fitted_doc), detector_version="2")
    result = evaluate(moved, read_baseline(baseline), spec_version())
    assert result.exit_code == 0
    assert any("declared by a detector version bump" in line for line in result.lines)


def test_moved_calibration_corpus_fails(fitted_doc, tmp_path: Path) -> None:
    baseline = write_baseline(tmp_path / "b.json", baseline_body(fitted_doc))
    moved = replace(fitted_doc, calibration_sha256="pmk-cor-ffffffffffffffff")
    result = evaluate(moved, read_baseline(baseline), spec_version())
    assert result.exit_code == 1
    assert any("calibration corpus moved" in line for line in result.lines)


def test_empty_baseline_is_unevaluable(fitted_doc, tmp_path: Path) -> None:
    body = baseline_body(fitted_doc)
    body["operating_points"] = []
    baseline = write_baseline(tmp_path / "b.json", body)
    with pytest.raises(GateError, match="empty baseline"):
        read_baseline(baseline)


def test_unknown_baseline_schema_is_unevaluable(tmp_path: Path) -> None:
    path = tmp_path / "b.json"
    path.write_text('{"punchmark_schema": "other/v1"}\n')
    with pytest.raises(GateError, match="not a gate-baseline/v1"):
        read_baseline(path)
    path.write_text("nope\n")
    with pytest.raises(GateError, match="not JSON"):
        read_baseline(path)


def test_model_without_operating_points_is_unevaluable(fitted_doc, tmp_path: Path) -> None:
    baseline = write_baseline(tmp_path / "b.json", baseline_body(fitted_doc))
    gutted = replace(fitted_doc, operating_points=())
    with pytest.raises(GateError, match="nothing to gate"):
        evaluate(gutted, read_baseline(baseline), spec_version())


def test_baseline_body_is_deterministic(fitted_doc) -> None:
    assert canonical_json(baseline_body(fitted_doc)) == canonical_json(
        baseline_body(fitted_doc)
    )
    json.loads(canonical_json(baseline_body(fitted_doc)))  # valid JSON
