"""The detector seam contract (PMK-DET-001/002)."""

from __future__ import annotations

import pytest

from punchmark.detector import TrivialFitted, build_detector, fitted_from_params
from punchmark.errors import DetectorError
from punchmark.model import CandidateSet, FittedModel, ResponseRow, ResponseSet, Window


def row(sample: str, text: str) -> ResponseRow:
    return ResponseRow(
        sample=sample,
        profile="minimal",
        language="python",
        variant="base",
        tier=None,
        intrinsic={"n_ops": 1},
        raw_outputs=(text,),
        is_stub=False,
    )


def rset(route: str, task: str, rows: list[ResponseRow]) -> ResponseSet:
    return ResponseSet(
        route=route,
        task=task,
        window=Window("2026-01-01T00:00:00+00:00", "2026-01-01T01:00:00+00:00"),
        rows=tuple(rows),
        archive_sha256="sha256:" + "0" * 64,
        source_name=f"{task}__{route.replace('/', '-')}.jsonl.gz",
    )


CANDIDATES = CandidateSet(routes=("r/a", "r/b"))
TRAIN = [
    rset("r/a", "t", [row("s1", "aaaa aaaa"), row("s2", "aaab aaba")]),
    rset("r/b", "t", [row("s1", "zzzz zzzz"), row("s2", "zzzy zyzz")]),
]


def test_trivial_satisfies_the_protocol_and_identifies() -> None:
    fitted = build_detector("trivial").fit(TRAIN, CANDIDATES, seed=0)
    assert isinstance(fitted, FittedModel)
    scores = fitted.score_rows([row("sx", "aaaa aaba")], "t")
    assert set(scores[0]) == {"r/a", "r/b"}
    assert scores[0]["r/a"] > scores[0]["r/b"]


def test_params_roundtrip_exactly() -> None:
    fitted = build_detector("trivial").fit(TRAIN, CANDIDATES, seed=0)
    params = fitted.to_params()
    rebuilt = fitted_from_params("trivial", CANDIDATES, dict(params))
    assert isinstance(rebuilt, TrivialFitted)
    assert rebuilt.to_params() == params
    a = fitted.score_rows([row("sx", "aaaa zzzz")], "t")
    b = rebuilt.score_rows([row("sx", "aaaa zzzz")], "t")
    assert a == b


def test_fit_refusals() -> None:
    det = build_detector("trivial")
    with pytest.raises(DetectorError, match="at least two routes"):
        det.fit(TRAIN, CandidateSet(routes=("r/a",)), seed=0)
    with pytest.raises(DetectorError, match="no training archive for candidate"):
        det.fit([TRAIN[0]], CANDIDATES, seed=0)
    undeclared = rset("r/c", "t", [row("s1", "mmmm")])
    with pytest.raises(DetectorError, match="not in the candidate set"):
        det.fit([*TRAIN, undeclared], CANDIDATES, seed=0)
    with pytest.raises(DetectorError, match="no training archives"):
        det.fit([], CANDIDATES, seed=0)


def test_unknown_detector_refused() -> None:
    with pytest.raises(DetectorError, match="unknown detector"):
        build_detector("nope")
    with pytest.raises(DetectorError, match="unknown detector"):
        fitted_from_params("nope", CANDIDATES, {})


def test_scoring_unfitted_task_and_stub_rows_refused() -> None:
    fitted = build_detector("trivial").fit(TRAIN, CANDIDATES, seed=0)
    with pytest.raises(DetectorError, match="not fitted for task"):
        fitted.score_rows([row("s", "x")], "other-task")
    stub = ResponseRow(
        sample="s",
        profile="p",
        language="l",
        variant=None,
        tier=None,
        intrinsic=None,
        raw_outputs=(),
        is_stub=True,
    )
    with pytest.raises(DetectorError, match="stub"):
        fitted.score_rows([stub], "t")
