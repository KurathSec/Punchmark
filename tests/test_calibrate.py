"""Calibration arithmetic on paper-checkable fixtures (PMK-CAL-001..004)."""

from __future__ import annotations

import random

import pytest

from punchmark.calibrate import (
    CalibrationConfig,
    ScoredRow,
    ScoredSet,
    build_nulls,
    cluster_subset,
    conservative_quantile,
    crossfit_scored,
    identify,
    lookup_threshold,
    operating_points,
    split_half,
    t_statistic,
)
from punchmark.errors import CalibrationError
from punchmark.model import OperatingPoint
from tests.conftest import CAL_CONFIG, CANDIDATES


def srow(key: str, cluster: str, a: float, b: float) -> ScoredRow:
    return ScoredRow(key=key, cluster=cluster, scores={"r/a": a, "r/b": b})


def test_t_statistic_by_hand() -> None:
    rows = [srow("1", "c1", 1.0, 0.0), srow("2", "c1", 3.0, 1.0)]
    # mean a = 2.0, mean b = 0.5 -> T(a) = 1.5, T(b) = -1.5
    assert t_statistic(rows, "r/a", ("r/a", "r/b")) == pytest.approx(1.5)
    assert t_statistic(rows, "r/b", ("r/a", "r/b")) == pytest.approx(-1.5)
    assert identify(rows, ("r/a", "r/b")) == "r/a"


def test_t_statistic_refusals() -> None:
    with pytest.raises(CalibrationError, match="empty set"):
        t_statistic([], "r/a", ("r/a", "r/b"))
    with pytest.raises(CalibrationError, match="alternative"):
        t_statistic([srow("1", "c", 1, 0)], "r/a", ("r/a",))


def test_conservative_quantile_is_conservative() -> None:
    draws = [float(i) for i in range(100)]  # 0..99
    t = conservative_quantile(draws, 0.05)
    # empirical P(T < t) must be <= 0.05
    assert sum(1 for d in draws if d < t) / len(draws) <= 0.05
    # alpha smaller than 1/n falls back to the minimum
    assert conservative_quantile(draws, 0.001) == 0.0


def test_cluster_subset_moves_whole_clusters() -> None:
    clusters = {
        f"c{i}": tuple(srow(f"{i}-{j}", f"c{i}", 0, 0) for j in range(5))
        for i in range(6)
    }
    subset = cluster_subset(clusters, 12, random.Random(3))
    assert len(subset) >= 12
    picked = {r.cluster for r in subset}
    for name in picked:  # every picked cluster is complete
        assert sum(1 for r in subset if r.cluster == name) == 5
    with pytest.raises(CalibrationError, match="cannot draw"):
        cluster_subset(clusters, 999, random.Random(3))


def test_split_half_partitions_clusters() -> None:
    clusters = {
        f"c{i}": tuple(srow(f"{i}-{j}", f"c{i}", 0, 0) for j in range(3))
        for i in range(5)
    }
    a, b = split_half(clusters, random.Random(1))
    clusters_a = {r.cluster for r in a}
    clusters_b = {r.cluster for r in b}
    assert clusters_a.isdisjoint(clusters_b)
    assert clusters_a | clusters_b == set(clusters)
    assert len(a) + len(b) == 15


def test_crossfit_scores_every_valid_row_out_of_fold(train_sets) -> None:
    from punchmark.detector import build_detector

    oof = crossfit_scored(build_detector("trivial"), train_sets, CANDIDATES, seed=5)
    assert len(oof) == len(train_sets)
    for ss, rs in zip(oof, train_sets, strict=True):
        assert len(ss.rows) == len(rs.valid_rows)
        assert [r.key for r in ss.rows] == [v.item_key for v in rs.valid_rows]
        for row in ss.rows:
            assert set(row.scores) == set(CANDIDATES.routes)


def test_nulls_and_operating_points_keep_the_far_promise(train_sets) -> None:
    from punchmark.detector import build_detector

    oof = crossfit_scored(build_detector("trivial"), train_sets, CANDIDATES, seed=5)
    nulls = build_nulls(oof, CANDIDATES, CAL_CONFIG)
    assert nulls, "synthetic corpus must support at least one (task, m) null"
    points = operating_points(nulls, CAL_CONFIG)
    for null in nulls:
        for far in CAL_CONFIG.far_grid:
            point = next(
                p
                for p in points
                if (p.task, p.route, p.m, p.far) == (null.task, null.route, null.m, far)
            )
            empirical = sum(1 for d in null.draws if d < point.threshold) / len(null.draws)
            assert empirical <= far, (
                f"threshold at far={far} flags {empirical} of its own null"
            )


def test_null_needs_enough_clusters() -> None:
    tiny = ScoredSet(
        route="r/a",
        task="t",
        source_name="t__r-a.jsonl.gz",
        rows=tuple(srow(str(i), "onecluster", 0.0, 0.0) for i in range(50)),
    )
    with pytest.raises(CalibrationError, match="no .task, m. cell"):
        build_nulls([tiny], CANDIDATES, CalibrationConfig(m_grid=(25,), min_clusters=4))


def test_lookup_threshold_is_conservative_and_refuses_below_floor() -> None:
    points = [
        OperatingPoint(task="t", route="r/a", far=0.01, m=25, threshold=-1.0, n_null=100),
        OperatingPoint(task="t", route="r/a", far=0.01, m=50, threshold=-0.5, n_null=100),
    ]
    assert lookup_threshold(points, "t", "r/a", 0.01, 60).m == 50
    assert lookup_threshold(points, "t", "r/a", 0.01, 49).m == 25
    assert lookup_threshold(points, "t", "r/a", 0.01, 10) is None
    assert lookup_threshold(points, "t", "r/a", 0.05, 60) is None
    assert lookup_threshold(points, "t", "r/b", 0.01, 60) is None
