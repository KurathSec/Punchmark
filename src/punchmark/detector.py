"""Detectors: the seam between text and statistics.

A detector implements ``DetectorModel``/``FittedModel`` over ``ResponseSet``s: it
never touches a file and never imports a reader (PMK-DET-001); its fitted state is
plain data that round-trips exactly through ``to_params``/``from_params``.

The scaffold ships ``trivial`` (PMK-DET-002): a per-(route, task) character
unigram centroid scored by negative L1 distance -- deliberately tuning-free, so
every downstream mechanism (calibration, power, rulings, certificates, the gate)
is exercised end-to-end before the real detector lands. Per-task state is
strictly separate: models for different tasks never share a feature space, or the
model would learn the task instead of the producer.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from typing import Any

from .errors import DetectorError
from .features import get_spec, row_counts
from .model import CandidateSet, DetectorModel, FittedModel, ResponseRow, ResponseSet

TRIVIAL_ID = "trivial"
TRIVIAL_VERSION = "1"
_TRIVIAL_SPEC = "chargram1/v1"
_TRIVIAL_VIEW = "RAW@1"


def _check_train(
    train: Sequence[ResponseSet], candidates: CandidateSet
) -> dict[str, dict[str, list[ResponseSet]]]:
    """task -> route -> sets; refuses a fit that cannot cover its own candidate set."""
    if len(candidates.routes) < 2:
        raise DetectorError(
            "a candidate set needs at least two routes; identification against one "
            "candidate decides nothing"
        )
    by_task: dict[str, dict[str, list[ResponseSet]]] = defaultdict(lambda: defaultdict(list))
    for rs in train:
        if rs.route not in candidates.routes:
            raise DetectorError(
                f"training archive {rs.source_name} carries route {rs.route!r} which is "
                "not in the candidate set; every training label must be declared"
            )
        by_task[rs.task][rs.route].append(rs)
    for task, routes in by_task.items():
        missing = set(candidates.routes) - set(routes)
        if missing:
            raise DetectorError(
                f"task {task!r} has no training archive for candidate(s) "
                f"{sorted(missing)}; a candidate the model never saw cannot be scored"
            )
    if not by_task:
        raise DetectorError("no training archives supplied")
    return {t: dict(r) for t, r in by_task.items()}


class TrivialFitted:
    """Nearest-centroid unigram reference model. Scores are negative L1 distances
    between a row's normalized bucket distribution and each route centroid --
    higher means closer, which gives them the same orientation as the
    log-likelihoods the real detector emits."""

    def __init__(
        self,
        candidates: CandidateSet,
        centroids: dict[str, dict[str, dict[int, float]]],
    ) -> None:
        self._candidates = candidates
        self._centroids = centroids  # task -> route -> bucket -> prob

    @property
    def detector_id(self) -> str:
        return TRIVIAL_ID

    @property
    def detector_version(self) -> str:
        return TRIVIAL_VERSION

    @property
    def feature_spec(self) -> str:
        return _TRIVIAL_SPEC

    @property
    def view(self) -> str:
        return _TRIVIAL_VIEW

    @property
    def candidates(self) -> CandidateSet:
        return self._candidates

    @property
    def tasks(self) -> tuple[str, ...]:
        return tuple(sorted(self._centroids))

    def score_rows(
        self, rows: Sequence[ResponseRow], task: str
    ) -> list[dict[str, float]]:
        if task not in self._centroids:
            raise DetectorError(
                f"model was not fitted for task {task!r}; fitted tasks: {list(self.tasks)}"
            )
        centroids = self._centroids[task]
        out: list[dict[str, float]] = []
        for row in rows:
            if row.is_stub or not row.raw_outputs:
                raise DetectorError(
                    "score_rows received a stub row; callers filter to valid rows"
                )
            counts = row_counts(row.raw_outputs, self.view, self.feature_spec)
            total = sum(counts.values())
            scores: dict[str, float] = {}
            for route, centroid in centroids.items():
                if total == 0:
                    scores[route] = 0.0
                    continue
                dist = 0.0
                for bucket, prob in centroid.items():
                    dist += abs(counts.get(bucket, 0) / total - prob)
                for bucket, c in counts.items():
                    if bucket not in centroid:
                        dist += c / total
                scores[route] = -dist
            out.append(scores)
        return out

    def to_params(self) -> dict[str, object]:
        return {
            "centroids": {
                task: {
                    route: {str(b): p for b, p in sorted(centroid.items())}
                    for route, centroid in sorted(routes.items())
                }
                for task, routes in sorted(self._centroids.items())
            }
        }

    @classmethod
    def from_params(
        cls, candidates: CandidateSet, params: dict[str, Any]
    ) -> TrivialFitted:
        raw = params.get("centroids")
        if not isinstance(raw, dict):
            raise DetectorError("trivial params missing 'centroids'")
        centroids: dict[str, dict[str, dict[int, float]]] = {}
        for task, routes in raw.items():
            centroids[str(task)] = {
                str(route): {int(b): float(p) for b, p in centroid.items()}
                for route, centroid in routes.items()
            }
        return cls(candidates, centroids)


class TrivialDetector:
    @property
    def detector_id(self) -> str:
        return TRIVIAL_ID

    @property
    def detector_version(self) -> str:
        return TRIVIAL_VERSION

    def fit(
        self, train: Sequence[ResponseSet], candidates: CandidateSet, seed: int
    ) -> FittedModel:
        del seed  # the trivial detector is closed-form; the seed is part of the contract
        by_task = _check_train(train, candidates)
        get_spec(_TRIVIAL_SPEC)
        centroids: dict[str, dict[str, dict[int, float]]] = {}
        for task, routes in by_task.items():
            centroids[task] = {}
            for route, sets in routes.items():
                pooled: Counter[int] = Counter()
                for rs in sets:
                    for row in rs.valid_rows:
                        pooled.update(row_counts(row.raw_outputs, _TRIVIAL_VIEW, _TRIVIAL_SPEC))
                total = sum(pooled.values())
                if total == 0:
                    raise DetectorError(
                        f"no featurizable text for route {route!r}, task {task!r}"
                    )
                centroids[task][route] = {b: c / total for b, c in pooled.items()}
        return TrivialFitted(candidates, centroids)


def build_detector(detector_id: str) -> DetectorModel:
    detectors: dict[str, DetectorModel] = {TRIVIAL_ID: TrivialDetector()}
    try:
        return detectors[detector_id]
    except KeyError:
        raise DetectorError(
            f"unknown detector {detector_id!r}; shipped detectors: {sorted(detectors)}"
        ) from None


def fitted_from_params(
    detector_id: str, candidates: CandidateSet, params: dict[str, Any]
) -> FittedModel:
    if detector_id == TRIVIAL_ID:
        return TrivialFitted.from_params(candidates, params)
    raise DetectorError(f"unknown detector {detector_id!r} in fitted-model file")
