"""Calibration: the same-route within-window null and its thresholds.

The operating point is the deliverable. Everything here follows four rulings:

- the resampling cluster unit is the base sample name (PMK-CAL-001): a sample's
  variants, profiles and languages share program content and move together in
  every subsample and splice;
- the null is CROSS-FITTED (PMK-CAL-002): the null distribution of the set
  statistic T is built only from out-of-fold scores (2-fold split by cluster
  within each training archive), because an in-sample null is optimistic, sets
  the threshold too tight, and silently overshoots the declared false-alarm rate
  on held-out data. The shipped model is fitted on everything; its thresholds
  come from the cross-fitted null and are therefore slightly conservative,
  which is declared;
- null material is same-route pairs measured INSIDE one window -- subsets of a
  single archive (PMK-CAL-003); cross-window comparisons are a diagnostic, never
  a null;
- the threshold at declared false-alarm rate ``far`` is the conservative
  empirical far-quantile of the null (PMK-CAL-004), and set-size lookup at
  scoring time takes the largest calibrated m that does not exceed the archive's,
  which widens rather than narrows the null.
"""

from __future__ import annotations

import random
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from .canonical import derive_seed
from .errors import CalibrationError
from .model import (
    CandidateSet,
    DetectorModel,
    FittedModel,
    OperatingPoint,
    ResponseSet,
)


@dataclass(frozen=True, slots=True)
class ScoredRow:
    key: str
    cluster: str
    scores: dict[str, float]


@dataclass(frozen=True, slots=True)
class ScoredSet:
    """One archive's rows scored against every candidate: the cached 'score table'
    everything downstream is pure arithmetic over."""

    route: str
    task: str
    source_name: str
    rows: tuple[ScoredRow, ...]

    @property
    def clusters(self) -> dict[str, tuple[ScoredRow, ...]]:
        grouped: dict[str, list[ScoredRow]] = {}
        for row in self.rows:
            grouped.setdefault(row.cluster, []).append(row)
        return {c: tuple(rs) for c, rs in grouped.items()}


@dataclass(frozen=True, slots=True)
class CalibrationConfig:
    far_grid: tuple[float, ...] = (0.001, 0.005, 0.01, 0.05, 0.1)
    m_grid: tuple[int, ...] = (25, 50, 100, 150)
    n_null: int = 2000
    seed: int = 0
    min_clusters: int = 8


@dataclass(frozen=True, slots=True)
class NullDistribution:
    task: str
    m: int
    draws: tuple[float, ...]
    n_archives: int
    n_clusters_min: int


@dataclass(frozen=True)
class Calibration:
    operating_points: tuple[OperatingPoint, ...]
    nulls: tuple[NullDistribution, ...] = field(repr=False)
    oof_scored: tuple[ScoredSet, ...] = field(repr=False)


def score_set(fitted: FittedModel, rs: ResponseSet) -> ScoredSet:
    rows = rs.valid_rows
    scored = fitted.score_rows(rows, rs.task)
    return ScoredSet(
        route=rs.route,
        task=rs.task,
        source_name=rs.source_name,
        rows=tuple(
            ScoredRow(key=row.item_key, cluster=row.cluster, scores=s)
            for row, s in zip(rows, scored, strict=True)
        ),
    )


def t_statistic(rows: Sequence[ScoredRow], declared: str, candidates: Sequence[str]) -> float:
    """T(S; r0) = mean_i l_i(r0) - max_{r != r0} mean_i l_i(r). Negative T is
    evidence against the declared producer."""
    if not rows:
        raise CalibrationError("T undefined on an empty set")
    mean_declared = statistics.fmean(r.scores[declared] for r in rows)
    alternatives = [c for c in candidates if c != declared]
    if not alternatives:
        raise CalibrationError("T needs at least one alternative candidate")
    best_alt = max(
        statistics.fmean(r.scores[c] for r in rows) for c in alternatives
    )
    return mean_declared - best_alt


def identify(rows: Sequence[ScoredRow], candidates: Sequence[str]) -> str:
    """Whole-set identification: the candidate with the highest mean evidence."""
    if not rows:
        raise CalibrationError("identification undefined on an empty set")
    return max(candidates, key=lambda c: statistics.fmean(r.scores[c] for r in rows))


def cluster_subset(
    clusters: dict[str, tuple[ScoredRow, ...]], m: int, rng: random.Random
) -> tuple[ScoredRow, ...]:
    """A cluster-respecting subset with AT LEAST m rows: whole clusters are drawn
    without replacement until the row count reaches m. Clusters move whole; the
    nominal m is a floor, never an exact size (declared)."""
    names = sorted(clusters)
    rng.shuffle(names)
    picked: list[ScoredRow] = []
    for name in names:
        picked.extend(clusters[name])
        if len(picked) >= m:
            break
    if len(picked) < m:
        raise CalibrationError(
            f"cannot draw a subset of {m} rows from {sum(len(v) for v in clusters.values())}"
        )
    return tuple(picked)


def split_half(
    clusters: dict[str, tuple[ScoredRow, ...]], rng: random.Random
) -> tuple[tuple[ScoredRow, ...], tuple[ScoredRow, ...]]:
    """One cluster-respecting split of an archive into two halves: the within-window
    same-route pair unit (PMK-CAL-003)."""
    names = sorted(clusters)
    if len(names) < 2:
        raise CalibrationError("split-half needs at least two clusters")
    rng.shuffle(names)
    cut = len(names) // 2
    a = tuple(row for n in names[:cut] for row in clusters[n])
    b = tuple(row for n in names[cut:] for row in clusters[n])
    return a, b


def conservative_quantile(draws: Sequence[float], alpha: float) -> float:
    """The empirical alpha-quantile taken from below: flagging at T < t keeps the
    empirical flag rate <= alpha on the null draws (PMK-CAL-004)."""
    if not draws:
        raise CalibrationError("no null draws")
    ordered = sorted(draws)
    idx = max(0, int(alpha * len(ordered)) - 1)
    return ordered[idx]


def crossfit_scored(
    detector: DetectorModel,
    train: Sequence[ResponseSet],
    candidates: CandidateSet,
    seed: int,
) -> list[ScoredSet]:
    """Out-of-fold score tables for every training archive (PMK-CAL-002).

    Clusters of each archive are split into two folds deterministically; model A
    is fitted on fold-A rows of every archive and scores fold-B rows, and vice
    versa. Row order within each archive is preserved."""
    folds: dict[str, dict[str, int]] = {}
    for rs in train:
        rng = random.Random(derive_seed("crossfit-folds", rs.source_name, seed))
        names = sorted({row.cluster for row in rs.valid_rows})
        if len(names) < 2:
            raise CalibrationError(
                f"{rs.source_name}: cross-fitting needs at least two clusters"
            )
        rng.shuffle(names)
        cut = len(names) // 2
        folds[rs.source_name] = {n: (0 if i < cut else 1) for i, n in enumerate(names)}

    def restrict(rs: ResponseSet, fold: int) -> ResponseSet:
        rows = tuple(
            row
            for row in rs.rows
            if not row.is_stub and folds[rs.source_name][row.cluster] == fold
        )
        return ResponseSet(
            route=rs.route,
            task=rs.task,
            window=rs.window,
            rows=rows,
            archive_sha256=rs.archive_sha256,
            source_name=rs.source_name,
        )

    fitted_by_fold: dict[int, FittedModel] = {}
    for fold in (0, 1):
        subset = [restrict(rs, fold) for rs in train]
        fitted_by_fold[fold] = detector.fit(subset, candidates, seed)

    out: list[ScoredSet] = []
    for rs in train:
        rows = rs.valid_rows
        scored_rows: list[ScoredRow] = []
        for fold in (0, 1):
            fold_rows = [r for r in rows if folds[rs.source_name][r.cluster] == fold]
            if not fold_rows:
                continue
            # fold-0 rows are scored by the model fitted on fold 1, and vice versa
            other = fitted_by_fold[1 - fold]
            for row, s in zip(
                fold_rows, other.score_rows(fold_rows, rs.task), strict=True
            ):
                scored_rows.append(ScoredRow(key=row.item_key, cluster=row.cluster, scores=s))
        by_key = {sr.key: sr for sr in scored_rows}
        ordered = tuple(by_key[row.item_key] for row in rows)
        out.append(
            ScoredSet(route=rs.route, task=rs.task, source_name=rs.source_name, rows=ordered)
        )
    return out


def build_nulls(
    oof: Sequence[ScoredSet],
    candidates: CandidateSet,
    config: CalibrationConfig,
) -> list[NullDistribution]:
    """Null draws of T per (task, m), pooled over that task's archives: for each
    archive, cluster-respecting subsets scored against the archive's OWN route."""
    by_task: dict[str, list[ScoredSet]] = {}
    for ss in oof:
        by_task.setdefault(ss.task, []).append(ss)
    nulls: list[NullDistribution] = []
    for task, sets in sorted(by_task.items()):
        for m in config.m_grid:
            draws: list[float] = []
            n_clusters_min: int | None = None
            usable = 0
            for ss in sets:
                clusters = ss.clusters
                n_rows = sum(len(v) for v in clusters.values())
                if n_rows < m or len(clusters) < config.min_clusters:
                    continue
                usable += 1
                n_clusters_min = (
                    len(clusters)
                    if n_clusters_min is None
                    else min(n_clusters_min, len(clusters))
                )
                per_archive = max(1, config.n_null // max(1, len(sets)))
                for i in range(per_archive):
                    rng = random.Random(
                        derive_seed("null", task, ss.source_name, m, i, config.seed)
                    )
                    subset = cluster_subset(clusters, m, rng)
                    draws.append(t_statistic(subset, ss.route, candidates.routes))
            if usable == 0:
                continue
            nulls.append(
                NullDistribution(
                    task=task,
                    m=m,
                    draws=tuple(draws),
                    n_archives=usable,
                    n_clusters_min=n_clusters_min or 0,
                )
            )
    if not nulls:
        raise CalibrationError(
            "no (task, m) cell had enough rows and clusters to build a null; "
            f"the smallest requested m is {min(config.m_grid)} and the cluster floor is "
            f"{config.min_clusters}"
        )
    return nulls


def operating_points(
    nulls: Iterable[NullDistribution], config: CalibrationConfig
) -> list[OperatingPoint]:
    points: list[OperatingPoint] = []
    for null in nulls:
        for far in config.far_grid:
            points.append(
                OperatingPoint(
                    task=null.task,
                    far=far,
                    m=null.m,
                    threshold=conservative_quantile(null.draws, far),
                    n_null=len(null.draws),
                )
            )
    return points


def lookup_threshold(
    points: Sequence[OperatingPoint], task: str, far: float, n_items: int
) -> OperatingPoint | None:
    """The operating point for an archive of ``n_items`` rows: the largest
    calibrated m not exceeding it (conservative; PMK-CAL-004). None when the
    archive is below the calibrated floor -- an UNDETERMINED, never a guess."""
    eligible = [p for p in points if p.task == task and p.far == far and p.m <= n_items]
    if not eligible:
        return None
    return max(eligible, key=lambda p: p.m)


def calibrate(
    detector: DetectorModel,
    train: Sequence[ResponseSet],
    candidates: CandidateSet,
    config: CalibrationConfig,
) -> Calibration:
    oof = crossfit_scored(detector, train, candidates, config.seed)
    nulls = build_nulls(oof, candidates, config)
    points = operating_points(nulls, config)
    return Calibration(
        operating_points=tuple(points),
        nulls=tuple(nulls),
        oof_scored=tuple(oof),
    )
