"""Power: seeded substitution, miss curves, and the minimum resolvable separation.

The seeded-substitution population is spliced on the SCORE TABLE, never on text
(PMK-POW-001): for a declared route r0 and an actual substitute r', a fraction rho
of a subset's rows -- whole clusters, matched by item key -- are replaced with the
same items' rows from r''s archive. A substitution of known size and identity
therefore exists in the evaluation set rather than being hoped for.

Output (d) -- the minimum resolvable substituted fraction rho* at a declared
false-alarm rate and power target -- is what makes a null legible as a power limit
(PMK-POW-003). rho = 0 must reproduce the null (PMK-POW-002; a built-in
self-check), and the fidelity of spliced substitutions to real vendor changes
cannot be validated and is printed as a standing bound (PMK-POW-004).
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

from .calibrate import (
    CalibrationConfig,
    ScoredRow,
    ScoredSet,
    cluster_subset,
    conservative_quantile,
    t_statistic,
)
from .canonical import derive_seed
from .errors import CalibrationError
from .model import CandidateSet, OperatingPoint, PowerPoint


@dataclass(frozen=True, slots=True)
class PowerConfig:
    rho_grid: tuple[float, ...] = (0.0, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0)
    n_splice: int = 400
    power_target: float = 0.8
    seed: int = 0


@dataclass(frozen=True, slots=True)
class CurvePoint:
    task: str
    declared: str
    substitute: str
    m: int
    far: float
    miss: float


@dataclass(frozen=True)
class PowerResult:
    curve: tuple[CurvePoint, ...]
    power_points: tuple[PowerPoint, ...]


def splice(
    base: ScoredSet,
    donor: ScoredSet,
    m: int,
    rho: float,
    rng: random.Random,
) -> tuple[ScoredRow, ...]:
    """A cluster-respecting subset of ``base`` with ~rho of its rows replaced by the
    same items scored from ``donor``. Whole clusters swap together; items missing
    from the donor stay unswapped (counted by the caller via key alignment)."""
    if base.task != donor.task:
        raise CalibrationError("splice needs two archives of the same task")
    subset = cluster_subset(base.clusters, m, rng)
    if rho <= 0.0:
        return subset
    donor_by_key = {row.key: row for row in donor.rows}
    clusters: dict[str, list[ScoredRow]] = {}
    for row in subset:
        clusters.setdefault(row.cluster, []).append(row)
    names = sorted(clusters)
    rng.shuffle(names)
    target = rho * len(subset)
    swapped: set[str] = set()
    n_swapped = 0
    for name in names:
        if n_swapped >= target:
            break
        swapped.add(name)
        n_swapped += len(clusters[name])
    out: list[ScoredRow] = []
    for row in subset:
        if row.cluster in swapped and row.key in donor_by_key:
            out.append(donor_by_key[row.key])
        else:
            out.append(row)
    return tuple(out)


def _threshold_for(
    points: Sequence[OperatingPoint], task: str, route: str, far: float, m: int
) -> float:
    for p in points:
        if p.task == task and p.route == route and p.far == far and p.m == m:
            return p.threshold
    raise CalibrationError(
        f"no operating point for (task={task}, route={route}, far={far}, m={m})"
    )


def power_analysis(
    oof: Sequence[ScoredSet],
    candidates: CandidateSet,
    points: Sequence[OperatingPoint],
    cal_config: CalibrationConfig,
    config: PowerConfig,
) -> PowerResult:
    """Miss curves and rho* for every ordered candidate pair, per task and set size.

    Declared route = the base archive's own route; actual producer = the donor.
    ``miss`` at rho is the fraction of spliced sets NOT flagged (T >= threshold).
    """
    by_task_route: dict[tuple[str, str], ScoredSet] = {}
    for ss in oof:
        by_task_route[(ss.task, ss.route)] = ss
    curve: list[CurvePoint] = []
    power_points: list[PowerPoint] = []
    tasks = sorted({ss.task for ss in oof})
    calibrated = {(p.task, p.route, p.m) for p in points}
    for task in tasks:
        routes = [r for t, r in by_task_route if t == task]
        for m in cal_config.m_grid:
            for declared in sorted(routes):
                if (task, declared, m) not in calibrated:
                    continue
                base = by_task_route[(task, declared)]
                if sum(len(v) for v in base.clusters.values()) < m:
                    continue
                for substitute in sorted(routes):
                    if substitute == declared:
                        continue
                    donor = by_task_route[(task, substitute)]
                    rho_min: float | None = None
                    for far in sorted(cal_config.far_grid):
                        threshold = _threshold_for(points, task, declared, far, m)
                        # miss at full substitution is the curve's y-axis
                        misses = 0
                        for i in range(config.n_splice):
                            rng = random.Random(
                                derive_seed(
                                    "power", task, declared, substitute, m,
                                    "rho=1.0", f"far={far}", i, config.seed,
                                )
                            )
                            rows = splice(base, donor, m, 1.0, rng)
                            if t_statistic(rows, declared, candidates.routes) >= threshold:
                                misses += 1
                        curve.append(
                            CurvePoint(
                                task=task,
                                declared=declared,
                                substitute=substitute,
                                m=m,
                                far=far,
                                miss=misses / config.n_splice,
                            )
                        )
                    # rho* at the declared 1% point (or the closest available far)
                    far_star = 0.01 if 0.01 in cal_config.far_grid else cal_config.far_grid[0]
                    threshold = _threshold_for(points, task, declared, far_star, m)
                    for rho in sorted(config.rho_grid):
                        if rho == 0.0:
                            continue
                        flagged = 0
                        for i in range(config.n_splice):
                            rng = random.Random(
                                derive_seed(
                                    "power", task, declared, substitute, m,
                                    f"rho={rho}", f"far={far_star}", i, config.seed,
                                )
                            )
                            rows = splice(base, donor, m, rho, rng)
                            if t_statistic(rows, declared, candidates.routes) < threshold:
                                flagged += 1
                        if flagged / config.n_splice >= config.power_target:
                            rho_min = rho
                            break
                    power_points.append(
                        PowerPoint(
                            task=task,
                            declared=declared,
                            substitute=substitute,
                            m=m,
                            far=far_star,
                            power_target=config.power_target,
                            rho_min=rho_min,
                        )
                    )
    if not curve:
        raise CalibrationError("power analysis produced no curve points; check m_grid vs data")
    return PowerResult(curve=tuple(curve), power_points=tuple(power_points))


def rho_zero_selfcheck(
    oof: Sequence[ScoredSet],
    candidates: CandidateSet,
    points: Sequence[OperatingPoint],
    m: int,
    far: float,
    n_draws: int,
    seed: int,
) -> float:
    """The PMK-POW-002 self-check: the flag rate of UNspliced (rho = 0) subsets at
    the calibrated threshold. Must come out <= far up to resampling noise; the
    caller asserts and reports it."""
    flagged = 0
    total = 0
    for ss in oof:
        clusters = ss.clusters
        if sum(len(v) for v in clusters.values()) < m:
            continue
        threshold = _threshold_for(points, ss.task, ss.route, far, m)
        for i in range(n_draws):
            rng = random.Random(derive_seed("rho-zero", ss.source_name, m, f"far={far}", i, seed))
            rows = cluster_subset(clusters, m, rng)
            if t_statistic(rows, ss.route, candidates.routes) < threshold:
                flagged += 1
            total += 1
    if total == 0:
        raise CalibrationError("rho-zero self-check had no usable archives")
    return flagged / total


def quantile_of(draws: Sequence[float], alpha: float) -> float:
    """Re-exported conservative quantile for reporting layers."""
    return conservative_quantile(draws, alpha)
