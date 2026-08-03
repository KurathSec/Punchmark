"""Two processes, two hash seeds, byte-identical artifacts (PMK-EMIT-001/003)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

SCRIPT = """
import sys
from pathlib import Path
from punchmark.archive import read_archive
from punchmark.calibrate import CalibrationConfig, calibrate
from punchmark.detector import build_detector
from punchmark.model import CandidateSet
from punchmark.modelfile import build_doc, write_model
from punchmark.power import PowerConfig, power_analysis
from punchmark.sidecar import load_and_attach
from punchmark.spec import spec_version
from punchmark.synth import SynthSpec, default_routes, generate

out = Path(sys.argv[1])
routes = default_routes(2)
candidates = CandidateSet(routes=tuple(sorted(routes)))
generate(out / "arch", SynthSpec(routes=routes, tasks=("t",), n_clusters=6, k=2,
                                 separation=0.7, seed=13))
train = [load_and_attach(read_archive(p, candidates), p)
         for p in sorted((out / "arch").glob("t__*.jsonl.gz"))]
det = build_detector("chargram")
config = CalibrationConfig(far_grid=(0.05,), m_grid=(20,), n_null=120, seed=13,
                           min_clusters=3)
cal = calibrate(det, train, candidates, config)
power = power_analysis(cal.oof_scored, candidates, cal.operating_points, config,
                       PowerConfig(n_splice=30, seed=13))
doc = build_doc(det.fit(train, candidates, 13), spec_version(), "pmk-cor-fixed",
                {"seed": 13}, cal.operating_points, power.curve, power.power_points)
write_model(out / "model.json", doc)
"""


def _run(tmp_path: Path, hashseed: str) -> bytes:
    out = tmp_path / f"run-{hashseed}"
    out.mkdir()
    subprocess.run(
        [sys.executable, "-c", SCRIPT, str(out)],
        check=True,
        env={"PYTHONHASHSEED": hashseed, "PATH": "/usr/bin:/bin"},
    )
    return (out / "model.json").read_bytes()


def test_model_bytes_survive_hash_randomization(tmp_path: Path) -> None:
    assert _run(tmp_path, "1") == _run(tmp_path, "31337")
