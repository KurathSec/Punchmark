"""Power: seeded substitution, miss curves, and the minimum resolvable separation.

The seeded-substitution population is spliced on the SCORE TABLE, never on text
(PMK-POW-001): for a declared route r0 and an actual substitute r', a fraction rho
of a subset's rows -- whole clusters, matched by item key -- are replaced with the
same items' rows from r''s archive. A donor that cannot cover a swapped cluster's
item keys is a refusal, never a silent partial swap.

rho = 0 must reproduce the null (PMK-POW-002), and the check is ENFORCED here: for
every calibrated (task, route, m, far) cell, ``power_analysis`` measures the flag
rate of unspliced subsets at the calibrated threshold and REFUSES to report power
when it exceeds the declared far beyond binomial noise -- a violation means the
splice machinery or the calibration is broken.

Output (d) -- the minimum resolvable substituted fraction rho* at power_target,
reported PER CALIBRATED FAR so a ruling at any declared operating point has a
power table to consult (PMK-POW-003) -- is what makes a null legible as a power
limit. The fidelity of spliced substitutions to real vendor changes cannot be
validated and is printed as a standing bound (PMK-POW-004).
"""

from __future__ import annotations

import math
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
    rho_grid: tuple[float, ...] = (0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0)
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
    """A cluster-respecting subset of ``base`` with ~rho of its rows replaced by
    the same items scored from ``donor``. Whole clusters swap together; a donor
    that lacks any swapped item's key is a refusal (PMK-POW-001) -- a silent
    partial swap would understate the seeded substitution."""
    if base.task != donor.task:
        raise CalibrationError("splice needs two archives of the same task")
    subset = cluster_subset(base.clusters, m, rng)
    if rho <= 0.0:
        return subset
    donor_by_key = {row.key: row for row in donor.rows}
    return _swap(subset, donor_by_key, rho, rng)


def _swap(
    subset: tuple[ScoredRow, ...],
    donor_by_key: dict[str, ScoredRow],
    rho: float,
    rng: random.Random,
) -> tuple[ScoredRow, ...]:
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
    missing = [
        row.key for row in subset if row.cluster in swapped and row.key not in donor_by_key
    ]
    if missing:
        raise CalibrationError(
            f"splice donor lacks {len(missing)} of the swapped clusters' item keys "
            f"(first: {missing[0]!r}); a partial swap would understate the seeded "
            "substitution, so this is refused"
        )
    return tuple(
        donor_by_key[row.key] if row.cluster in swapped else row for row in subset
    )


def _selfcheck_tolerance(far: float, n: int) -> float:
    """far plus three binomial sigmas plus one-draw granularity."""
    return far + 3.0 * math.sqrt(far * (1.0 - far) / n) + 1.0 / n


def power_analysis(
    oof: Sequence[ScoredSet],
    candidates: CandidateSet,
    points: Sequence[OperatingPoint],
    cal_config: CalibrationConfig,
    config: PowerConfig,
) -> PowerResult:
    """Miss curves and rho* for every ordered candidate pair, per (task, m, far).

    Declared route = the base archive's own route; actual producer = the donor
    (every archive of the cell contributes as a base; donor rows are merged by
    item key across the substitute's archives). Splice draws are made once per
    (pair, m, rho) and evaluated against every calibrated far's threshold; the
    rho = 0 self-check runs first and refuses the whole analysis on failure
    (PMK-POW-002).
    """
    bases: dict[tuple[str, str], list[ScoredSet]] = {}
    donors: dict[tuple[str, str], dict[str, ScoredRow]] = {}
    for ss in oof:
        bases.setdefault((ss.task, ss.route), []).append(ss)
        merged = donors.setdefault((ss.task, ss.route), {})
        for row in ss.rows:
            merged.setdefault(row.key, row)

    thresholds: dict[tuple[str, str, int], dict[float, float]] = {}
    for p in points:
        thresholds.setdefault((p.task, p.route, p.m), {})[p.far] = p.threshold

    curve: list[CurvePoint] = []
    power_points: list[PowerPoint] = []

    for (task, declared), cell_bases in sorted(bases.items()):
        routes_in_task = sorted({r for (t, r) in bases if t == task and r != declared})
        for m in cal_config.m_grid:
            fars = thresholds.get((task, declared, m))
            if not fars:
                continue  # nothing calibrated for this cell; nothing to report
            usable = [
                b for b in cell_bases
                if sum(len(v) for v in b.clusters.values()) >= m
            ]
            if not usable:
                continue
            n_per_base = max(1, config.n_splice // len(usable))

            # PMK-POW-002: unspliced subsets must reproduce the null
            t_zero: list[float] = []
            for base in usable:
                for i in range(n_per_base):
                    rng = random.Random(
                        derive_seed("power-rho0", task, declared, base.source_name,
                                    m, i, config.seed)
                    )
                    subset = cluster_subset(base.clusters, m, rng)
                    t_zero.append(t_statistic(subset, declared, candidates.routes))
            for far, threshold in sorted(fars.items()):
                rate = sum(1 for t in t_zero if t < threshold) / len(t_zero)
                if rate > _selfcheck_tolerance(far, len(t_zero)):
                    raise CalibrationError(
                        f"rho=0 self-check failed for (task={task}, route={declared}, "
                        f"m={m}, far={far}): unspliced flag rate {rate:.4f} exceeds "
                        "the declared far beyond noise; the splice machinery or the "
                        "calibration is broken and power is refused (PMK-POW-002)"
                    )

            for substitute in routes_in_task:
                donor_by_key = donors[(task, substitute)]
                rho_min_by_far: dict[float, float | None] = dict.fromkeys(fars)
                for rho in sorted(config.rho_grid):
                    t_vals: list[float] = []
                    for base in usable:
                        for i in range(n_per_base):
                            rng = random.Random(
                                derive_seed("power", task, declared, substitute,
                                            base.source_name, m, f"rho={rho}", i,
                                            config.seed)
                            )
                            subset = cluster_subset(base.clusters, m, rng)
                            subset = _swap(subset, donor_by_key, rho, rng)
                            t_vals.append(
                                t_statistic(subset, declared, candidates.routes)
                            )
                    for far, threshold in sorted(fars.items()):
                        power = sum(1 for t in t_vals if t < threshold) / len(t_vals)
                        if rho == 1.0:
                            curve.append(
                                CurvePoint(
                                    task=task, declared=declared,
                                    substitute=substitute, m=m, far=far,
                                    miss=1.0 - power,
                                )
                            )
                        if rho_min_by_far[far] is None and power >= config.power_target:
                            rho_min_by_far[far] = rho
                for far in sorted(fars):
                    power_points.append(
                        PowerPoint(
                            task=task, declared=declared, substitute=substitute,
                            m=m, far=far, power_target=config.power_target,
                            rho_min=rho_min_by_far[far],
                        )
                    )
    if not curve:
        raise CalibrationError(
            "power analysis produced no curve points; check m_grid vs data and "
            "ensure rho_grid contains 1.0"
        )
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
    """Standalone PMK-POW-002 probe (the ENFORCED form lives inside
    ``power_analysis``): the flag rate of unspliced subsets at the calibrated
    threshold, pooled over archives whose (task, route, far, m) cell has an
    operating point. Cells with no calibrated threshold are skipped, never
    guessed."""
    flagged = 0
    total = 0
    for ss in oof:
        clusters = ss.clusters
        if sum(len(v) for v in clusters.values()) < m:
            continue
        threshold: float | None = None
        for p in points:
            if (p.task, p.route, p.far, p.m) == (ss.task, ss.route, far, m):
                threshold = p.threshold
                break
        if threshold is None:
            continue
        for i in range(n_draws):
            rng = random.Random(
                derive_seed("rho-zero", ss.source_name, m, f"far={far}", i, seed)
            )
            rows = cluster_subset(clusters, m, rng)
            if t_statistic(rows, ss.route, candidates.routes) < threshold:
                flagged += 1
            total += 1
    if total == 0:
        raise CalibrationError(
            "rho-zero self-check had no usable (archive, operating point) cell"
        )
    return flagged / total


def quantile_of(draws: Sequence[float], alpha: float) -> float:
    """Re-exported conservative quantile for reporting layers."""
    return conservative_quantile(draws, alpha)
