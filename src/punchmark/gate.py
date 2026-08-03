"""The CI gate: artifact-only policy over a fitted-model file and its baseline.

The gate consumes serialized artifacts and nothing else -- it never reads an
archive and never refits anything. Exit codes preserve the three-way distinction
(PMK-GTE-001): 0 pass, 1 measured fail, 2 unevaluable; both non-zero, so
UNEVALUABLE can never slip through as success, and an empty comparison can never
pass (PMK-GTE-002: a gate that checked nothing has not gated anything).

The policy (PMK-GTE-003): the calibrated operating point may only move together
with a declared detector-version change or a spec MAJOR bump. A moved threshold
under an unchanged version is exactly the silent recalibration the instrument
exists to forbid in others.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .canonical import fmt_float
from .errors import GateError
from .modelfile import ModelDoc

BASELINE_SCHEMA = "gate-baseline/v1"


@dataclass(frozen=True)
class GateResult:
    exit_code: int
    lines: tuple[str, ...]


def baseline_body(doc: ModelDoc) -> dict[str, Any]:
    """The committed baseline the gate compares against: the operating points plus
    everything a move must be justified by."""
    return {
        "punchmark_schema": BASELINE_SCHEMA,
        "detector": {"id": doc.detector_id, "version": doc.detector_version},
        "spec_major": doc.spec_version.split(".")[0],
        "calibration_sha256": doc.calibration_sha256,
        "candidate_set_id": doc.candidates.candidate_set_id,
        "operating_points": [
            {
                "task": p.task,
                "route": p.route,
                "far": fmt_float(p.far),
                "m": p.m,
                "threshold": fmt_float(p.threshold),
            }
            for p in sorted(
                doc.operating_points, key=lambda p: (p.task, p.route, p.far, p.m)
            )
        ],
    }


def read_baseline(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise GateError(f"{path}: unreadable baseline ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise GateError(f"{path}: baseline is not JSON ({exc.msg})") from exc
    if not isinstance(raw, dict) or raw.get("punchmark_schema") != BASELINE_SCHEMA:
        raise GateError(f"{path}: not a {BASELINE_SCHEMA} document")
    if not raw.get("operating_points"):
        raise GateError(
            f"{path}: baseline carries no operating points; an empty baseline gates "
            "nothing and is refused"
        )
    return raw


def evaluate(doc: ModelDoc, baseline: dict[str, Any], spec_version: str) -> GateResult:
    lines: list[str] = []
    current = baseline_body(doc)
    version_changed = current["detector"] != baseline.get("detector")
    spec_major_changed = current["spec_major"] != baseline.get("spec_major")
    lines.append(
        f"gate: detector {current['detector']['id']} v{current['detector']['version']} "
        f"(baseline v{baseline.get('detector', {}).get('version', '?')}); "
        f"spec {spec_version} (baseline major {baseline.get('spec_major', '?')})"
    )

    base_points = {
        (p["task"], p.get("route", "*"), p["far"], p["m"]): p["threshold"]
        for p in baseline["operating_points"]
    }
    cur_points = {
        (p["task"], p["route"], p["far"], p["m"]): p["threshold"]
        for p in current["operating_points"]
    }
    if not cur_points:
        raise GateError("model file carries no operating points; nothing to gate")

    moved = sorted(
        k for k in base_points.keys() & cur_points.keys()
        if base_points[k] != cur_points[k]
    )
    removed = sorted(base_points.keys() - cur_points.keys())
    added = sorted(cur_points.keys() - base_points.keys())
    calibration_moved = current["calibration_sha256"] != baseline.get("calibration_sha256")
    candidates_moved = current["candidate_set_id"] != baseline.get("candidate_set_id")

    changes: list[str] = []
    for k in moved:
        changes.append(
            f"operating point {k} moved {base_points[k]} -> {cur_points[k]}"
        )
    for k in removed:
        changes.append(f"operating point {k} disappeared")
    for k in added:
        changes.append(f"operating point {k} appeared")
    if calibration_moved:
        changes.append(
            f"calibration corpus moved {baseline.get('calibration_sha256')} -> "
            f"{current['calibration_sha256']}"
        )
    if candidates_moved:
        changes.append(
            f"candidate set moved {baseline.get('candidate_set_id')} -> "
            f"{current['candidate_set_id']}"
        )

    if not changes:
        lines.append("gate: operating points match the baseline; PASS")
        return GateResult(exit_code=0, lines=tuple(lines))

    for change in changes:
        lines.append(f"gate: {change}")
    if version_changed or spec_major_changed:
        justification = "detector version" if version_changed else "spec MAJOR"
        lines.append(
            f"gate: changes are declared by a {justification} bump; PASS "
            "(refresh the baseline together with this change)"
        )
        return GateResult(exit_code=0, lines=tuple(lines))
    lines.append(
        "gate: FAIL -- the calibrated operating point moved without a declared "
        "detector-version or spec-MAJOR bump. A silently moved threshold is the "
        "failure mode this tool exists to make visible; bump the version or revert "
        "the calibration. (No statement about model weights is implied.)"
    )
    return GateResult(exit_code=1, lines=tuple(lines))
