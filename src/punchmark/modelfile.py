"""The fitted-model file: ``<name>.pmk-model.json`` (schema ``model/v1``).

Everything a bare install needs to score an archive: detector identity and
params, candidate set, calibrated operating points, miss curve and power table,
and the calibration corpus hash they were computed from. ``model_id`` is a
content address (PMK-EMIT-002); a file that fails its own hash or carries an
unknown schema is refused, never partially read (a KeyError must not masquerade
as a verdict).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .canonical import canonical_json, content_id, fmt_float, write_text_deterministic
from .errors import ModelFileError
from .model import CandidateSet, FittedModel, OperatingPoint, PowerPoint
from .power import CurvePoint

SCHEMA = "model/v1"


@dataclass(frozen=True)
class ModelDoc:
    model_id: str
    spec_version: str
    detector_id: str
    detector_version: str
    feature_spec: str
    view: str
    candidates: CandidateSet
    calibration_sha256: str
    calibration_meta: dict[str, Any]
    operating_points: tuple[OperatingPoint, ...]
    curve: tuple[CurvePoint, ...]
    power: tuple[PowerPoint, ...]
    params: dict[str, Any]

    @property
    def tasks(self) -> tuple[str, ...]:
        return tuple(sorted({p.task for p in self.operating_points}))


def _body(doc: ModelDoc) -> dict[str, Any]:
    return {
        "punchmark_schema": SCHEMA,
        "model_id": doc.model_id,
        "spec_version": doc.spec_version,
        "detector": {
            "id": doc.detector_id,
            "version": doc.detector_version,
            "feature_spec": doc.feature_spec,
            "view": doc.view,
        },
        "candidate_set": {
            "id": doc.candidates.candidate_set_id,
            "routes": list(doc.candidates.routes),
        },
        "calibration": {"corpus_sha256": doc.calibration_sha256, **doc.calibration_meta},
        "operating_points": [
            {
                "task": p.task,
                "far": fmt_float(p.far),
                "m": p.m,
                "threshold": fmt_float(p.threshold),
                "n_null": p.n_null,
            }
            for p in doc.operating_points
        ],
        "curve": [
            {
                "task": c.task,
                "declared": c.declared,
                "substitute": c.substitute,
                "m": c.m,
                "far": fmt_float(c.far),
                "miss": fmt_float(c.miss),
            }
            for c in doc.curve
        ],
        "power": [
            {
                "task": p.task,
                "declared": p.declared,
                "substitute": p.substitute,
                "m": p.m,
                "far": fmt_float(p.far),
                "power_target": fmt_float(p.power_target),
                "rho_min": None if p.rho_min is None else fmt_float(p.rho_min),
            }
            for p in doc.power
        ],
        "params": doc.params,
    }


def build_doc(
    fitted: FittedModel,
    spec_version: str,
    calibration_sha256: str,
    calibration_meta: dict[str, Any],
    operating_points: tuple[OperatingPoint, ...],
    curve: tuple[CurvePoint, ...],
    power: tuple[PowerPoint, ...],
) -> ModelDoc:
    doc = ModelDoc(
        model_id="",
        spec_version=spec_version,
        detector_id=fitted.detector_id,
        detector_version=fitted.detector_version,
        feature_spec=fitted.feature_spec,
        view=fitted.view,
        candidates=fitted.candidates,
        calibration_sha256=calibration_sha256,
        calibration_meta=calibration_meta,
        operating_points=operating_points,
        curve=curve,
        power=power,
        params=fitted.to_params(),
    )
    model_id = content_id(_body(doc), "model_id", "pmk-m")
    return replace(doc, model_id=model_id)


def write_model(path: Path, doc: ModelDoc) -> None:
    write_text_deterministic(path, canonical_json(_body(doc)))


def read_model(path: Path) -> ModelDoc:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ModelFileError(f"{path}: unreadable ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise ModelFileError(f"{path}: not JSON ({exc.msg})") from exc
    if not isinstance(raw, dict) or raw.get("punchmark_schema") != SCHEMA:
        raise ModelFileError(
            f"{path}: not a {SCHEMA} fitted-model file; refuse rather than guess"
        )
    try:
        candidates = CandidateSet(routes=tuple(raw["candidate_set"]["routes"]))
        doc = ModelDoc(
            model_id=str(raw["model_id"]),
            spec_version=str(raw["spec_version"]),
            detector_id=str(raw["detector"]["id"]),
            detector_version=str(raw["detector"]["version"]),
            feature_spec=str(raw["detector"]["feature_spec"]),
            view=str(raw["detector"]["view"]),
            candidates=candidates,
            calibration_sha256=str(raw["calibration"]["corpus_sha256"]),
            calibration_meta={
                k: v for k, v in raw["calibration"].items() if k != "corpus_sha256"
            },
            operating_points=tuple(
                OperatingPoint(
                    task=str(p["task"]),
                    far=float(p["far"]),
                    m=int(p["m"]),
                    threshold=float(p["threshold"]),
                    n_null=int(p["n_null"]),
                )
                for p in raw["operating_points"]
            ),
            curve=tuple(
                CurvePoint(
                    task=str(c["task"]),
                    declared=str(c["declared"]),
                    substitute=str(c["substitute"]),
                    m=int(c["m"]),
                    far=float(c["far"]),
                    miss=float(c["miss"]),
                )
                for c in raw["curve"]
            ),
            power=tuple(
                PowerPoint(
                    task=str(p["task"]),
                    declared=str(p["declared"]),
                    substitute=str(p["substitute"]),
                    m=int(p["m"]),
                    far=float(p["far"]),
                    power_target=float(p["power_target"]),
                    rho_min=None if p["rho_min"] is None else float(p["rho_min"]),
                )
                for p in raw["power"]
            ),
            params=dict(raw["params"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ModelFileError(
            f"{path}: malformed {SCHEMA} document ({exc!r}); regenerate with punchmark fit"
        ) from exc
    expected = content_id(_body(doc), "model_id", "pmk-m")
    if doc.model_id != expected:
        raise ModelFileError(
            f"{path}: model_id {doc.model_id} does not match content ({expected}); "
            "the file was edited after it was written"
        )
    return doc
