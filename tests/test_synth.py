"""The planted-truth harness: deterministic, recoverable, refusable."""

from __future__ import annotations

from pathlib import Path

import pytest

from punchmark.calibrate import identify, score_set
from punchmark.detector import build_detector
from punchmark.errors import SynthError
from punchmark.model import CandidateSet
from punchmark.synth import SynthSpec, default_routes, generate
from tests.conftest import read_windowed


def test_generation_is_byte_deterministic(tmp_path: Path) -> None:
    spec = SynthSpec(
        routes=default_routes(2), tasks=("t",), n_clusters=4, k=2, separation=0.5, seed=3
    )
    a = generate(tmp_path / "a", spec)
    b = generate(tmp_path / "b", spec)
    for pa, pb in zip(a, b, strict=True):
        assert pa.read_bytes() == pb.read_bytes()
        sa = Path(str(pa) + ".window.json").read_text()
        sb = Path(str(pb) + ".window.json").read_text()
        assert sa.replace("/a/", "/") == sb.replace("/b/", "/")


def test_planted_truth_is_recovered_by_the_trivial_detector(tmp_path: Path) -> None:
    routes = default_routes(3)
    candidates = CandidateSet(routes=tuple(sorted(routes)))
    spec = SynthSpec(
        routes=routes, tasks=("t",), n_clusters=8, k=2, separation=0.7, seed=21
    )
    generate(tmp_path, spec)
    train = [
        read_windowed(p, candidates) for p in sorted(tmp_path.glob("t__*.jsonl.gz"))
    ]
    fitted = build_detector("trivial").fit(train, candidates, seed=0)
    for rs in train:
        scored = score_set(fitted, rs)
        assert identify(scored.rows, candidates.routes) == rs.route


def test_refusals() -> None:
    with pytest.raises(SynthError):
        default_routes(1)
    with pytest.raises(SynthError, match="clusters"):
        generate(
            Path("/nonexistent"),
            SynthSpec(
                routes=default_routes(2), tasks=("t",), n_clusters=1, k=1,
                separation=0.5, seed=0,
            ),
        )
    with pytest.raises(SynthError, match="separation"):
        generate(
            Path("/nonexistent"),
            SynthSpec(
                routes=default_routes(2), tasks=("t",), n_clusters=4, k=1,
                separation=1.5, seed=0,
            ),
        )
