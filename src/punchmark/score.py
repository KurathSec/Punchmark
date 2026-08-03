"""Scoring: one archive, one three-zone ruling at a declared operating point.

The refusal conditions are enumerated and mandatory (PMK-RUL-002); UNDETERMINED
is first-class and is what a passing statistic means when the archive could not
have resolved the requested substitution anyway (PMK-RUL-001). A ruling is a
statement about the route label as served within a candidate set -- never about
weights (PMK-CRT-002) and never open-set (PMK-CRT-003).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, replace

from .calibrate import ScoredRow, lookup_threshold, t_statistic
from .canonical import content_id
from .detector import fitted_from_params
from .errors import CalibrationError, SidecarError
from .model import ResponseSet, Ruling, Verdict, Window
from .modelfile import ModelDoc
from .rulings import ruling_body


@dataclass(frozen=True, slots=True)
class RulePolicy:
    far: float = 0.01
    rho_target: float = 1.0
    m_floor: int = 25
    c_floor: int = 8
    stub_cap: float = 0.05


def _finish(ruling: Ruling) -> Ruling:
    rid = content_id(ruling_body(ruling), "ruling_id", "pmk-r")
    return replace(ruling, ruling_id=rid)


def rule(doc: ModelDoc, rs: ResponseSet, policy: RulePolicy, spec_version: str) -> Ruling:
    """Score one windowed archive against a fitted model and return its ruling."""
    if rs.window is None:
        raise SidecarError(
            f"{rs.source_name}: no collection window; a ruling is per-(route, window) "
            "and punchmark refuses to rule without the caller-declared sidecar"
        )
    if rs.route not in doc.candidates.routes:
        raise CalibrationError(
            f"declared route {rs.route!r} is not in the model's candidate set "
            f"{list(doc.candidates.routes)}; a closed-set verdict about an undeclared "
            "route would be meaningless"
        )
    if rs.task not in doc.tasks:
        raise CalibrationError(
            f"task {rs.task!r} was not calibrated in this model (tasks: {list(doc.tasks)})"
        )

    valid = rs.valid_rows
    n_items = len(valid)
    clusters = rs.clusters
    n_clusters = len(clusters)
    stub_share = rs.n_stub_rows / len(rs.rows) if rs.rows else 1.0

    def base(
        verdict: Verdict,
        statistic: float | None,
        per_candidate: dict[str, float],
        threshold: float | None,
        rho_min: float | None,
        reasons: tuple[str, ...],
    ) -> Ruling:
        return _finish(
            Ruling(
                ruling_id="",
                verdict=verdict,
                route=rs.route,
                task=rs.task,
                window=Window(rs.window.start_utc, rs.window.end_utc)
                if rs.window
                else None,
                archive_sha256=rs.archive_sha256,
                model_id=doc.model_id,
                detector_id=doc.detector_id,
                detector_version=doc.detector_version,
                candidate_set_id=doc.candidates.candidate_set_id,
                candidates=doc.candidates.routes,
                far=policy.far,
                threshold=threshold,
                calibration_sha256=doc.calibration_sha256,
                spec_version=spec_version,
                statistic=statistic,
                per_candidate=per_candidate,
                n_items=n_items,
                n_clusters=n_clusters,
                n_stub_rows=rs.n_stub_rows,
                rho_target=policy.rho_target,
                rho_min=rho_min,
                reasons=reasons,
            )
        )

    reasons: list[str] = []
    if n_items < policy.m_floor:
        reasons.append(f"insufficient_items: {n_items} < floor {policy.m_floor}")
    if n_clusters < policy.c_floor:
        reasons.append(f"insufficient_clusters: {n_clusters} < floor {policy.c_floor}")
    if stub_share > policy.stub_cap:
        reasons.append(
            f"stub_share: {stub_share:.3f} of rows are error stubs (cap {policy.stub_cap})"
        )
    if reasons:
        return base(Verdict.UNDETERMINED, None, {}, None, None, tuple(reasons))

    fitted = fitted_from_params(doc.detector_id, doc.candidates, doc.params, doc.view)
    scored = fitted.score_rows(valid, rs.task)
    rows = [
        ScoredRow(key=row.item_key, cluster=row.cluster, scores=s)
        for row, s in zip(valid, scored, strict=True)
    ]
    per_candidate = {
        c: statistics.fmean(r.scores[c] for r in rows) for c in doc.candidates.routes
    }
    statistic = t_statistic(rows, rs.route, doc.candidates.routes)

    op = lookup_threshold(doc.operating_points, rs.task, policy.far, n_items)
    if op is None:
        available = sorted(
            {p.far for p in doc.operating_points if p.task == rs.task}
        )
        return base(
            Verdict.UNDETERMINED,
            statistic,
            per_candidate,
            None,
            None,
            (
                f"no_operating_point: nothing calibrated at far={policy.far} for "
                f"task {rs.task!r} at m <= {n_items} (calibrated far grid: {available})",
            ),
        )

    if statistic < op.threshold:
        return base(
            Verdict.SUBSTITUTED, statistic, per_candidate, op.threshold, None, ()
        )

    # Power gate: SAME-PRODUCER may only mean "a substitution of fraction >=
    # rho_target by any candidate would have been flagged with the calibrated
    # power; none was" (PMK-RUL-001). An unresolvable pair forces UNDETERMINED.
    pairs = [
        p
        for p in doc.power
        if p.task == rs.task and p.declared == rs.route and p.m == op.m and p.far == policy.far
    ]
    if not pairs:
        return base(
            Verdict.UNDETERMINED,
            statistic,
            per_candidate,
            op.threshold,
            None,
            (f"no_power_table: no power entries for (task={rs.task}, m={op.m})",),
        )
    unresolved = [
        p for p in pairs if p.rho_min is None or p.rho_min > policy.rho_target
    ]
    rho_min_worst = None
    resolvable = [p.rho_min for p in pairs if p.rho_min is not None]
    if resolvable and not unresolved:
        rho_min_worst = max(resolvable)
    if unresolved:
        names = ", ".join(f"{p.substitute}" for p in unresolved)
        return base(
            Verdict.UNDETERMINED,
            statistic,
            per_candidate,
            op.threshold,
            None,
            (
                f"power_limit: substitution by {names} at fraction {policy.rho_target} "
                "would not have been resolved at this k and item count; absence of an "
                "alarm is not evidence here",
            ),
        )
    return base(
        Verdict.SAME_PRODUCER, statistic, per_candidate, op.threshold, rho_min_worst, ()
    )
