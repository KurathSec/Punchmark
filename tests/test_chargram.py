"""The chargram multinomial detector (PMK-DET-003/004)."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from punchmark.calibrate import identify, score_set
from punchmark.detector import (
    CHARGRAM_DEFAULT_VIEW,
    ChargramFitted,
    build_detector,
    fitted_from_params,
)
from punchmark.errors import DetectorError
from punchmark.model import CandidateSet
from punchmark.synth import SynthSpec, default_routes, generate
from tests.conftest import read_windowed
from tests.test_detector_seam import CANDIDATES, TRAIN, row


def test_defaults_and_view_validation() -> None:
    det = build_detector("chargram")
    fitted = det.fit(TRAIN, CANDIDATES, seed=0)
    assert fitted.view == CHARGRAM_DEFAULT_VIEW == "CANON@1"
    assert fitted.feature_spec == "chargram/v1"
    with pytest.raises(DetectorError, match="unknown text view"):
        build_detector("chargram", view="NOPE@1")
    with pytest.raises(DetectorError, match="fixed to view"):
        build_detector("trivial", view="CANON@1")


def test_log_likelihoods_by_hand() -> None:
    """One-route-one-row arithmetic: theta = (c + 0.5) / (C + 0.5 * D)."""
    fitted = build_detector("chargram").fit(TRAIN, CANDIDATES, seed=0)
    params = fitted.to_params()
    table = params["log_theta"]["t"]["r/a"]
    unseen = params["log_unseen"]["t"]["r/a"]
    # every stored log-theta must exceed the unseen mass and be a rounded float
    for lt in table.values():
        assert lt > unseen
        assert lt == round(lt, 6)
    # scoring a row of pure a-style text ranks r/a first
    scores = fitted.score_rows([row("sx", "aaaa aaab")], "t")[0]
    assert scores["r/a"] > scores["r/b"]
    # scores are per-gram normalized: magnitudes are log-prob scale, not summed
    assert all(-30 < v < 0 for v in scores.values())


def test_params_roundtrip_exactly_and_view_consistency() -> None:
    fitted = build_detector("chargram").fit(TRAIN, CANDIDATES, seed=0)
    params = fitted.to_params()
    rebuilt = fitted_from_params("chargram", CANDIDATES, dict(params), "CANON@1")
    assert isinstance(rebuilt, ChargramFitted)
    assert rebuilt.to_params() == params
    probe = [row("sx", "aaaa zzzz")]
    assert fitted.score_rows(probe, "t") == rebuilt.score_rows(probe, "t")
    with pytest.raises(DetectorError, match="inconsistent"):
        fitted_from_params("chargram", CANDIDATES, dict(params), "RAW@1")
    with pytest.raises(DetectorError, match="no valid 'view'"):
        fitted_from_params("chargram", CANDIDATES, {"log_theta": {}, "log_unseen": {}})


def test_fit_is_deterministic() -> None:
    a = build_detector("chargram").fit(TRAIN, CANDIDATES, seed=0).to_params()
    b = build_detector("chargram").fit(TRAIN, CANDIDATES, seed=99).to_params()
    assert a == b  # closed form; the seed is part of the seam, not the math


def test_identifies_planted_truth_at_moderate_separation(tmp_path: Path) -> None:
    routes = default_routes(3)
    candidates = CandidateSet(routes=tuple(sorted(routes)))
    generate(
        tmp_path,
        SynthSpec(routes=routes, tasks=("t",), n_clusters=8, k=2, separation=0.3, seed=8),
    )
    train = [
        read_windowed(p, candidates) for p in sorted(tmp_path.glob("t__*.jsonl.gz"))
    ]
    fitted = build_detector("chargram").fit(train, candidates, seed=0)
    for rs in train:
        scored = score_set(fitted, rs)
        assert identify(scored.rows, candidates.routes) == rs.route


def test_view_changes_the_fingerprint() -> None:
    """Fitting on ABL@1 must produce a genuinely different model than CANON@1."""
    canon = build_detector("chargram", view="CANON@1").fit(TRAIN, CANDIDATES, 0)
    abl = build_detector("chargram", view="ABL@1").fit(TRAIN, CANDIDATES, 0)
    assert canon.to_params() != abl.to_params()
    assert abl.view == "ABL@1"


def test_unseen_mass_is_log_lambda_over_denominator() -> None:
    fitted = build_detector("chargram").fit(TRAIN, CANDIDATES, seed=0)
    params = fitted.to_params()
    table = params["log_theta"]["t"]["r/a"]
    unseen = params["log_unseen"]["t"]["r/a"]
    # reconstruct C_r from any bucket: not directly recoverable, but the unseen
    # mass must equal log(0.5 / denom) for the same denom the buckets used --
    # check via the smallest bucket (count 1): log((1+0.5)/denom) - log(0.5/denom)
    # = log(3.0)
    smallest = min(table.values())
    assert math.isclose(smallest - unseen, math.log(3.0), abs_tol=2e-6)
