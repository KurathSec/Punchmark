"""The three-zone ruling and its mandatory refusals (PMK-RUL-001/002)."""

from __future__ import annotations

import gzip
import json
import shutil
from pathlib import Path

import pytest

from punchmark.archive import read_archive
from punchmark.errors import CalibrationError, SidecarError
from punchmark.model import ResponseSet, Verdict
from punchmark.score import RulePolicy, rule
from punchmark.spec import spec_version
from tests.conftest import CANDIDATES, TASK, read_windowed


def _sidecar_for(path: Path, route: str) -> None:
    import hashlib

    digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    body = {
        "punchmark_schema": "window/v1",
        "archive": path.name,
        "archive_sha256": digest,
        "route": route,
        "task": TASK,
        "window": {
            "start_utc": "2026-01-01T00:00:00+00:00",
            "end_utc": "2026-01-01T01:00:00+00:00",
        },
        "collector": {},
        "declared_by": "test",
    }
    path.with_name(path.name + ".window.json").write_text(
        json.dumps(body, indent=2) + "\n", encoding="utf-8"
    )


def test_true_archive_rules_same_producer(fitted_doc, synth_dir) -> None:
    rs = read_windowed(synth_dir / f"{TASK}__synth-route-a.jsonl.gz")
    ruling = rule(fitted_doc, rs, RulePolicy(far=0.01), spec_version())
    assert ruling.verdict is Verdict.SAME_PRODUCER
    assert ruling.statistic is not None and ruling.threshold is not None
    assert ruling.statistic >= ruling.threshold
    assert ruling.rho_min is not None
    assert ruling.ruling_id.startswith("pmk-r-")
    assert "NO_WEIGHTS_CLAIM" in ruling.does_not_show


def test_planted_substitution_rules_substituted(
    fitted_doc, synth_dir, tmp_path
) -> None:
    # route-b bytes under a route-a label: the planted substitution
    src = synth_dir / f"{TASK}__synth-route-b.jsonl.gz"
    dst = tmp_path / f"{TASK}__synth-route-a.jsonl.gz"
    shutil.copyfile(src, dst)
    _sidecar_for(dst, "synth/route-a")
    rs = read_windowed(dst)
    ruling = rule(fitted_doc, rs, RulePolicy(far=0.01), spec_version())
    assert ruling.verdict is Verdict.SUBSTITUTED
    assert ruling.statistic is not None and ruling.threshold is not None
    assert ruling.statistic < ruling.threshold


def test_identical_inputs_reproduce_identical_ruling_ids(fitted_doc, synth_dir) -> None:
    rs = read_windowed(synth_dir / f"{TASK}__synth-route-a.jsonl.gz")
    a = rule(fitted_doc, rs, RulePolicy(far=0.01), spec_version())
    b = rule(fitted_doc, rs, RulePolicy(far=0.01), spec_version())
    assert a.ruling_id == b.ruling_id


def test_small_archive_is_undetermined_not_guessed(fitted_doc, tmp_path) -> None:
    rows = []
    for c in range(3):
        rows.append(
            {
                "sample": f"s{c:03d}",
                "variant": "base",
                "profile": "minimal",
                "language": "python",
                "intrinsic": {"n_ops": 1},
                "tier": "A",
                "raw_outputs": ["tiny"],
            }
        )
    path = tmp_path / f"{TASK}__synth-route-a.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    _sidecar_for(path, "synth/route-a")
    rs = read_windowed(path)
    ruling = rule(fitted_doc, rs, RulePolicy(far=0.01), spec_version())
    assert ruling.verdict is Verdict.UNDETERMINED
    assert any("insufficient_items" in r for r in ruling.reasons)
    assert any("insufficient_clusters" in r for r in ruling.reasons)


def test_rho_target_below_power_forces_undetermined(fitted_doc, synth_dir) -> None:
    rs = read_windowed(synth_dir / f"{TASK}__synth-route-a.jsonl.gz")
    ruling = rule(
        fitted_doc, rs, RulePolicy(far=0.01, rho_target=0.001), spec_version()
    )
    assert ruling.verdict is Verdict.UNDETERMINED
    assert any("power_limit" in r for r in ruling.reasons)
    assert "absence of an alarm is not evidence" in " ".join(ruling.reasons)


def test_refusals_window_route_task(fitted_doc, synth_dir) -> None:
    path = synth_dir / f"{TASK}__synth-route-a.jsonl.gz"
    unwindowed = read_archive(path, CANDIDATES)
    with pytest.raises(SidecarError, match="refuses to rule"):
        rule(fitted_doc, unwindowed, RulePolicy(), spec_version())

    windowed = read_windowed(path)
    off_candidate = ResponseSet(
        route="synth/route-z",
        task=windowed.task,
        window=windowed.window,
        rows=windowed.rows,
        archive_sha256=windowed.archive_sha256,
        source_name=windowed.source_name,
    )
    with pytest.raises(CalibrationError, match="not in the model's candidate set"):
        rule(fitted_doc, off_candidate, RulePolicy(), spec_version())

    off_task = ResponseSet(
        route=windowed.route,
        task="uncalibrated",
        window=windowed.window,
        rows=windowed.rows,
        archive_sha256=windowed.archive_sha256,
        source_name=windowed.source_name,
    )
    with pytest.raises(CalibrationError, match="not calibrated"):
        rule(fitted_doc, off_task, RulePolicy(), spec_version())
