"""Shared fixtures: tiny synthetic corpora, a fitted model, small budgets.

CI never touches the reference benchmark checkout; every fixture is planted-truth
synthetic (PMK-DET-002) and small enough that any number in an assertion can be
checked on paper or recomputed in seconds.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from punchmark.calibrate import CalibrationConfig, calibrate
from punchmark.detector import build_detector
from punchmark.model import CandidateSet
from punchmark.modelfile import ModelDoc, build_doc, write_model
from punchmark.power import PowerConfig, power_analysis
from punchmark.sidecar import load_and_attach
from punchmark.spec import spec_version
from punchmark.synth import SynthSpec, default_routes, generate

ROUTES = default_routes(3)  # synth/route-a, -b, -c
TASK = "synthtask"
CANDIDATES = CandidateSet(routes=tuple(sorted(ROUTES)))
CAL_CONFIG = CalibrationConfig(
    far_grid=(0.01, 0.05, 0.1), m_grid=(25, 50), n_null=200, seed=11, min_clusters=4
)
POW_CONFIG = PowerConfig(n_splice=60, power_target=0.8, seed=11)


@pytest.fixture(scope="session")
def synth_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("synth")
    generate(
        out,
        SynthSpec(
            routes=ROUTES, tasks=(TASK,), n_clusters=12, k=3, separation=0.6, seed=11
        ),
    )
    return out


def read_windowed(path: Path, candidates: CandidateSet | None = CANDIDATES):
    from punchmark.archive import read_archive

    return load_and_attach(read_archive(path, candidates), path)


@pytest.fixture(scope="session")
def train_sets(synth_dir: Path):
    return [
        read_windowed(p) for p in sorted(synth_dir.glob(f"{TASK}__*.jsonl.gz"))
    ]


@pytest.fixture(scope="session")
def fitted_doc(train_sets) -> ModelDoc:
    detector = build_detector("trivial")
    calibration = calibrate(detector, train_sets, CANDIDATES, CAL_CONFIG)
    power = power_analysis(
        calibration.oof_scored,
        CANDIDATES,
        calibration.operating_points,
        CAL_CONFIG,
        POW_CONFIG,
    )
    fitted = detector.fit(train_sets, CANDIDATES, CAL_CONFIG.seed)
    return build_doc(
        fitted=fitted,
        spec_version=spec_version(),
        calibration_sha256="pmk-cor-testcorpus000000",
        calibration_meta={"n_null": CAL_CONFIG.n_null, "seed": CAL_CONFIG.seed},
        operating_points=calibration.operating_points,
        curve=power.curve,
        power=power.power_points,
    )


@pytest.fixture(scope="session")
def model_path(fitted_doc: ModelDoc, tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("model") / "test.pmk-model.json"
    write_model(path, fitted_doc)
    return path
