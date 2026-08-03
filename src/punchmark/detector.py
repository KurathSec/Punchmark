"""Detectors: the seam between text and statistics.

A detector implements ``DetectorModel``/``FittedModel`` over ``ResponseSet``s: it
never touches a file and never imports a reader (PMK-DET-001); its fitted state is
plain data that round-trips exactly through ``to_params``/``from_params``.

Two detectors ship:

- ``chargram`` (PMK-DET-003), the calibrated detector: a per-(route, task)
  Jeffreys-smoothed multinomial over hashed character 3-5-gram buckets, scored as
  the per-gram-normalized log-likelihood. Closed form, no optimizer; its known
  flaw -- overconfident posteriors -- is irrelevant because posteriors are never
  used: every threshold is an empirical null quantile (PMK-CAL-004). The primary
  text view is CANON@1, frozen before any held-out scoring (PMK-DET-004); RAW@1
  and ABL@1 exist for the recorded formatting-ablation study.
- ``trivial`` (PMK-DET-002): a character-unigram nearest-centroid reference, so
  every downstream mechanism is exercised end-to-end independently of the real
  detector.

Per-task state is strictly separate: models for different tasks never share a
feature space, or the model would learn the task instead of the producer.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from collections.abc import Sequence
from typing import Any

from .errors import DetectorError
from .features import get_spec, row_counts
from .model import CandidateSet, DetectorModel, FittedModel, ResponseRow, ResponseSet
from .views import VIEWS

TRIVIAL_ID = "trivial"
TRIVIAL_VERSION = "1"
_TRIVIAL_SPEC = "chargram1/v1"
_TRIVIAL_VIEW = "RAW@1"

CHARGRAM_ID = "chargram"
CHARGRAM_VERSION = "1"
_CHARGRAM_SPEC = "chargram/v1"
CHARGRAM_DEFAULT_VIEW = "CANON@1"
_LAMBDA = 0.5  # Jeffreys prior (PMK-DET-003)


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


class ChargramFitted:
    """Per-(task, route) smoothed multinomial (PMK-DET-003):

        theta_{r,b} = (c_{r,b} + lambda) / (C_r + lambda * D),  lambda = 0.5

    Per-row evidence is the per-gram-normalized log-likelihood
    ``l_i(r) = sum_b c_{i,b} * log theta_{r,b} / sum_b c_{i,b}`` -- one row is one
    evidence unit regardless of draw count (PMK-FEA-002). Log-probs are rounded
    to 6 places at fit time so params are compact and byte-stable (PMK-EMIT-001)
    and round-trip exactly.
    """

    def __init__(
        self,
        candidates: CandidateSet,
        view: str,
        tables: dict[str, dict[str, dict[int, float]]],
        log_unseen: dict[str, dict[str, float]],
    ) -> None:
        self._candidates = candidates
        self._view = view
        self._tables = tables  # task -> route -> bucket -> log theta
        self._log_unseen = log_unseen  # task -> route -> log theta for unseen buckets

    @property
    def detector_id(self) -> str:
        return CHARGRAM_ID

    @property
    def detector_version(self) -> str:
        return CHARGRAM_VERSION

    @property
    def feature_spec(self) -> str:
        return _CHARGRAM_SPEC

    @property
    def view(self) -> str:
        return self._view

    @property
    def candidates(self) -> CandidateSet:
        return self._candidates

    @property
    def tasks(self) -> tuple[str, ...]:
        return tuple(sorted(self._tables))

    def score_rows(
        self, rows: Sequence[ResponseRow], task: str
    ) -> list[dict[str, float]]:
        if task not in self._tables:
            raise DetectorError(
                f"model was not fitted for task {task!r}; fitted tasks: {list(self.tasks)}"
            )
        tables = self._tables[task]
        unseen = self._log_unseen[task]
        out: list[dict[str, float]] = []
        for row in rows:
            if row.is_stub or not row.raw_outputs:
                raise DetectorError(
                    "score_rows received a stub row; callers filter to valid rows"
                )
            counts = row_counts(row.raw_outputs, self._view, self.feature_spec)
            total = sum(counts.values())
            scores: dict[str, float] = {}
            for route in self._candidates.routes:
                table = tables[route]
                default = unseen[route]
                if total == 0:
                    scores[route] = default
                    continue
                ll = sum(c * table.get(b, default) for b, c in counts.items())
                scores[route] = ll / total
            out.append(scores)
        return out

    def to_params(self) -> dict[str, object]:
        return {
            "view": self._view,
            "log_theta": {
                task: {
                    route: {str(b): lt for b, lt in sorted(table.items())}
                    for route, table in sorted(routes.items())
                }
                for task, routes in sorted(self._tables.items())
            },
            "log_unseen": {
                task: dict(sorted(routes.items()))
                for task, routes in sorted(self._log_unseen.items())
            },
        }

    @classmethod
    def from_params(
        cls, candidates: CandidateSet, params: dict[str, Any], view: str | None = None
    ) -> ChargramFitted:
        stored_view = params.get("view")
        if not isinstance(stored_view, str) or stored_view not in VIEWS:
            raise DetectorError("chargram params carry no valid 'view'")
        if view is not None and view != stored_view:
            raise DetectorError(
                f"model file declares view {view!r} but params were fitted on "
                f"{stored_view!r}; the file is inconsistent"
            )
        raw_tables = params.get("log_theta")
        raw_unseen = params.get("log_unseen")
        if not isinstance(raw_tables, dict) or not isinstance(raw_unseen, dict):
            raise DetectorError("chargram params missing 'log_theta'/'log_unseen'")
        tables = {
            str(task): {
                str(route): {int(b): float(lt) for b, lt in table.items()}
                for route, table in routes.items()
            }
            for task, routes in raw_tables.items()
        }
        unseen = {
            str(task): {str(route): float(v) for route, v in routes.items()}
            for task, routes in raw_unseen.items()
        }
        return cls(candidates, stored_view, tables, unseen)


class ChargramDetector:
    def __init__(self, view: str = CHARGRAM_DEFAULT_VIEW) -> None:
        if view not in VIEWS:
            raise DetectorError(f"unknown text view {view!r}; shipped views: {sorted(VIEWS)}")
        self._view = view

    @property
    def detector_id(self) -> str:
        return CHARGRAM_ID

    @property
    def detector_version(self) -> str:
        return CHARGRAM_VERSION

    def fit(
        self, train: Sequence[ResponseSet], candidates: CandidateSet, seed: int
    ) -> FittedModel:
        del seed  # closed-form; the seed is part of the seam contract
        by_task = _check_train(train, candidates)
        spec = get_spec(_CHARGRAM_SPEC)
        tables: dict[str, dict[str, dict[int, float]]] = {}
        unseen: dict[str, dict[str, float]] = {}
        for task, routes in by_task.items():
            tables[task] = {}
            unseen[task] = {}
            for route, sets in routes.items():
                pooled: Counter[int] = Counter()
                for rs in sets:
                    for row in rs.valid_rows:
                        pooled.update(row_counts(row.raw_outputs, self._view, _CHARGRAM_SPEC))
                total = sum(pooled.values())
                if total == 0:
                    raise DetectorError(
                        f"no featurizable text for route {route!r}, task {task!r}"
                    )
                denom = total + _LAMBDA * spec.n_buckets
                tables[task][route] = {
                    b: round(math.log((c + _LAMBDA) / denom), 6)
                    for b, c in pooled.items()
                }
                unseen[task][route] = round(math.log(_LAMBDA / denom), 6)
        return ChargramFitted(candidates, self._view, tables, unseen)


def build_detector(detector_id: str, view: str | None = None) -> DetectorModel:
    if detector_id == CHARGRAM_ID:
        return ChargramDetector(view=view or CHARGRAM_DEFAULT_VIEW)
    if detector_id == TRIVIAL_ID:
        if view is not None and view != _TRIVIAL_VIEW:
            raise DetectorError(
                f"the trivial reference detector is fixed to view {_TRIVIAL_VIEW}"
            )
        return TrivialDetector()
    raise DetectorError(
        f"unknown detector {detector_id!r}; shipped detectors: "
        f"{sorted((CHARGRAM_ID, TRIVIAL_ID))}"
    )


def fitted_from_params(
    detector_id: str,
    candidates: CandidateSet,
    params: dict[str, Any],
    view: str | None = None,
) -> FittedModel:
    if detector_id == TRIVIAL_ID:
        return TrivialFitted.from_params(candidates, params)
    if detector_id == CHARGRAM_ID:
        return ChargramFitted.from_params(candidates, params, view)
    raise DetectorError(f"unknown detector {detector_id!r} in fitted-model file")
