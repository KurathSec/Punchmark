"""Splices, the rho-zero self-check, and rho* (PMK-POW-001..003)."""

from __future__ import annotations

import random

import pytest

from punchmark.calibrate import ScoredRow, ScoredSet, build_nulls, crossfit_scored, operating_points
from punchmark.detector import build_detector
from punchmark.errors import CalibrationError
from punchmark.power import power_analysis, rho_zero_selfcheck, splice
from tests.conftest import CAL_CONFIG, CANDIDATES, POW_CONFIG


def sset(route: str, value: float, n_clusters: int = 6, per: int = 4) -> ScoredSet:
    rows = []
    for c in range(n_clusters):
        for j in range(per):
            rows.append(
                ScoredRow(
                    key=f"{c}-{j}",
                    cluster=f"c{c}",
                    scores={"r/a": value, "r/b": -value},
                )
            )
    return ScoredSet(
        route=route, task="t", source_name=f"t__{route.replace('/', '-')}.jsonl.gz",
        rows=tuple(rows),
    )


def test_splice_rho_zero_is_identity() -> None:
    base, donor = sset("r/a", 1.0), sset("r/b", -1.0)
    rows = splice(base, donor, 12, 0.0, random.Random(2))
    assert all(r.scores["r/a"] == 1.0 for r in rows)


def test_splice_rho_one_swaps_every_matched_row_whole_clusters() -> None:
    base, donor = sset("r/a", 1.0), sset("r/b", -1.0)
    rows = splice(base, donor, 12, 1.0, random.Random(2))
    assert all(r.scores["r/a"] == -1.0 for r in rows)
    # intermediate rho swaps whole clusters only
    rows = splice(base, donor, 24, 0.5, random.Random(2))
    by_cluster: dict[str, set[float]] = {}
    for r in rows:
        by_cluster.setdefault(r.cluster, set()).add(r.scores["r/a"])
    for values in by_cluster.values():
        assert len(values) == 1, "a cluster was split by the splice"


def test_splice_requires_same_task() -> None:
    base = sset("r/a", 1.0)
    donor = ScoredSet(route="r/b", task="other", source_name="x", rows=base.rows)
    with pytest.raises(CalibrationError, match="same task"):
        splice(base, donor, 8, 0.5, random.Random(0))


def test_power_analysis_full_pipeline_and_rho_zero_selfcheck(train_sets) -> None:
    oof = crossfit_scored(build_detector("trivial"), train_sets, CANDIDATES, seed=5)
    nulls = build_nulls(oof, CANDIDATES, CAL_CONFIG)
    points = tuple(operating_points(nulls, CAL_CONFIG))
    result = power_analysis(oof, CANDIDATES, points, CAL_CONFIG, POW_CONFIG)

    # every ordered pair appears at every calibrated (task, m)
    tasks_ms = {(p.task, p.m) for p in points}
    for task, m in tasks_ms:
        pairs = {
            (p.declared, p.substitute)
            for p in result.power_points
            if p.task == task and p.m == m
        }
        n = len(CANDIDATES.routes)
        assert len(pairs) == n * (n - 1)

    # separable synthetic routes: a full swap must be detectable somewhere
    assert any(p.rho_min is not None for p in result.power_points)

    # the PMK-POW-002 self-check: unspliced subsets flag at <= far (+ slack for
    # resampling noise at 60 draws)
    rate = rho_zero_selfcheck(
        oof, CANDIDATES, points, m=25, far=0.05, n_draws=60, seed=9
    )
    assert rate <= 0.05 + 0.05


def test_miss_curve_is_monotone_in_far(hard_train_sets) -> None:
    """Raising the tolerated false-alarm rate can only lower (or keep) the miss.

    Uses a deliberately harder fixture than the shared one: at the shared
    separation every miss is already 0.0, so the assertion could not fail and the
    test proved nothing.
    """
    oof = crossfit_scored(build_detector("trivial"), hard_train_sets, CANDIDATES, seed=5)
    nulls = build_nulls(oof, CANDIDATES, CAL_CONFIG)
    points = tuple(operating_points(nulls, CAL_CONFIG))
    result = power_analysis(oof, CANDIDATES, points, CAL_CONFIG, POW_CONFIG)
    misses_seen = {c.miss for c in result.curve}
    assert len(misses_seen) > 1, (
        "fixture is too easy: every miss is identical, so monotonicity is vacuous"
    )
    by_pair: dict[tuple, list] = {}
    for c in result.curve:
        by_pair.setdefault((c.task, c.declared, c.substitute, c.m), []).append(c)
    for curve_points in by_pair.values():
        ordered = sorted(curve_points, key=lambda c: c.far)
        misses = [c.miss for c in ordered]
        assert misses == sorted(misses, reverse=True)
