#!/usr/bin/env python3
"""Angle C evaluation: apply the pre-registered decision rule to the purchased archives.

Reads only the six archives under `archives/`, their sidecars, and the shipped model.
Issues no requests and spends nothing, so it can be re-run against the same archives and
must produce the same numbers. Every number quoted in FINDING.md comes from here.

The evaluation is split exactly as DESIGN.md requires, and the two halves are never
conflated:

  C1  VERIFICATION, under the SHIPPED model, untouched. Only the routes whose slug is in
      its four-route candidate set, which is the three archives carrying the committed
      70B slug. This is the direct instrument for the load-bearing question: does an
      archive served by a different provider, under the identical slug, still read as the
      route it declares? Reported at several rho_target values, because a verdict means
      nothing without the substitution size it had power against.

  C2  IDENTIFICATION, under a SEPARATE side model fit here and stored here, never under
      calibration/, with provider-disambiguated route labels. Threshold-free argmax.

  C3  POWER. rho* per ordered pair. The pre-registered gate: the same-weights null is
      verdict-bearing only if the different-weights control pair resolves at this m.

  C4  The decision rule, applied as written, including the inconclusive branch.

Usage:  .venv/bin/python validation/angle_c/evaluate.py [--write]
"""

from __future__ import annotations

import argparse
import dataclasses
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from punchmark.archive import read_archive  # noqa: E402
from punchmark.calibrate import (  # noqa: E402
    CalibrationConfig,
    ScoredSet,
    calibrate,
    cluster_subset,
    identify,
)
from punchmark.canonical import (  # noqa: E402
    canonical_json,
    derive_seed,
    write_text_deterministic,
)
from punchmark.detector import build_detector  # noqa: E402
from punchmark.model import CandidateSet  # noqa: E402
from punchmark.modelfile import read_model  # noqa: E402
from punchmark.power import PowerConfig, power_analysis  # noqa: E402
from punchmark.rulings import ruling_body  # noqa: E402
from punchmark.score import RulePolicy, rule  # noqa: E402
from punchmark.sidecar import load_and_attach  # noqa: E402
from punchmark.spec.registry import spec_version  # noqa: E402

ARCHIVES = HERE / "archives"
DERIVED = HERE / "derived"
SHIPPED = ROOT / "calibration" / "spaghetti" / "goldens" / "default.pmk-model.json"

# Pre-declared, never tuned after seeing an outcome.
SEED = 20260806
TASKS = ("comprehend", "refactor_dev")
M_ARCHIVE = 75          # every purchased archive is exactly the 75-item probe half
# The largest m whose null actually has variance. A null draw is a cluster-respecting
# subsample of size >= m, so at m = M_ARCHIVE every draw is the whole archive and the
# 5000-draw null collapses to a single repeated value. A rho* measured against a point
# mass is not a power statement, and this was caught by the null diagnostic rather than
# reasoned about in advance: the first run reported rho* = 0.05 for the load-bearing
# pair at m=75, better than the different-weights control, which is what a degenerate
# null looks like from the outside. m is therefore capped strictly below the archive
# size, and the diagnostic flags any null that still collapses.
M_EVAL = 50
FAR = 0.01              # the shipped operating point
POWER_TARGET = 0.8

# Provider-disambiguated labels for the side model. The shipped model cannot tell the
# two providers apart by construction: both archives carry the same committed slug, which
# is exactly the situation under test. The side model gives them distinct labels so that
# identification is a question with a checkable answer.
LOAD_BEARING = ("deepinfra/Llama-3.3-70B-Instruct-Turbo",
                "together/Llama-3.3-70B-Instruct-Turbo")
CONTROL = ("deepinfra/Llama-3.3-70B-Instruct-Turbo",
           "deepinfra/Meta-Llama-3.1-8B-Instruct-Turbo")
ROUTE_LABEL = {
    ("deepinfra", "meta-llama-Llama-3.3-70B-Instruct-Turbo"):
        "deepinfra/Llama-3.3-70B-Instruct-Turbo",
    ("together", "meta-llama-Llama-3.3-70B-Instruct-Turbo"):
        "together/Llama-3.3-70B-Instruct-Turbo",
    ("deepinfra", "meta-llama-Meta-Llama-3.1-8B-Instruct-Turbo"):
        "deepinfra/Meta-Llama-3.1-8B-Instruct-Turbo",
}
SIDE_CANDIDATES = CandidateSet(tuple(sorted(set(ROUTE_LABEL.values()))))

# The rho_target values C1 is reported at. 1.0 is punchmark's default and the weakest
# claim the vocabulary permits: only a wholesale substitution of every item would have
# been caught. Anything stronger has to be earned by power, and at 75 items it may not
# be, in which case the instrument is supposed to answer UNDETERMINED rather than
# SAME-PRODUCER. Reporting the sweep is how that becomes visible instead of implied.
RHO_TARGETS = (1.0, 0.5, 0.2)


def load_purchased() -> list:
    """The six archives, relabelled in memory by (provider, slug).

    Relabelling rather than copying files keeps the route label out of the filename,
    which is where punchmark takes it from by construction (PMK-ARC-001). Nothing is
    written and the archives on disk are untouched.
    """
    sets = []
    for path in sorted(ARCHIVES.glob("*/*.jsonl.gz")):
        provider = path.parent.name
        # attach() validates the sidecar against the archive bytes and sets route from
        # the sidecar, so the relabel has to come after it, not before.
        rs = load_and_attach(read_archive(path), path)
        key = (provider, path.name.split("__", 1)[1].replace(".jsonl.gz", ""))
        sets.append(dataclasses.replace(rs, route=ROUTE_LABEL[key]))
    return sets


def c1_verification(spec_version: str) -> dict:
    """The shipped model, unchanged, on the archives whose slug it actually calibrated."""
    doc = read_model(SHIPPED)
    out: dict = {
        "model_id": doc.model_id,
        "candidate_set_id": doc.candidates.candidate_set_id,
        "candidates": list(doc.candidates.routes),
        "note": (
            "The shipped model cannot distinguish the two providers: both archives "
            "declare the same committed slug and the candidate set holds one entry for "
            "it. That is the question, not a defect. A SUBSTITUTED verdict on the "
            "Together archive would mean the detector reads a provider change as a "
            "producer change; SAME-PRODUCER means it does not, at the stated rho_target."
        ),
        "rulings": [],
    }
    for path in sorted(ARCHIVES.glob("*/*Llama-3.3-70B-Instruct-Turbo.jsonl.gz")):
        provider = path.parent.name
        # No relabel here: C1 is deliberately the archive as it declares itself, scored
        # under the model that was calibrated on that declared route.
        rs = load_and_attach(read_archive(path), path)
        for rho_target in RHO_TARGETS:
            policy = RulePolicy(far=FAR, rho_target=rho_target)
            r = rule(doc, rs, policy, spec_version)
            body = ruling_body(r)
            out["rulings"].append({
                "provider": provider,
                "task": rs.task,
                "rho_target": rho_target,
                "verdict": body["verdict"],
                "statistic": body["statistic"],
                "threshold": body["operating_point"]["threshold"],
                "rho_min": body["rho_min"],
                "reasons": body["reasons"],
                "n_items": body["n_items"],
                "n_clusters": body["n_clusters"],
                "per_candidate": body["per_candidate"],
                "ruling_id": body["ruling_id"],
            })
    return out


def subsample_identification(ss: ScoredSet, m: int, n_draws: int, tag: str,
                             clusters: dict | None = None) -> float:
    clusters = clusters if clusters is not None else ss.clusters
    correct = 0
    for i in range(n_draws):
        rng = random.Random(derive_seed("c2-ident", tag, ss.source_name, m, i, SEED))
        subset = cluster_subset(clusters, m, rng)
        if identify(subset, SIDE_CANDIDATES.routes) == ss.route:
            correct += 1
    return correct / n_draws


def c2_identification(oof: tuple[ScoredSet, ...]) -> dict:
    """Threshold-free argmax on out-of-fold scores, plus a cluster-bootstrap CI."""
    per_archive = {}
    for ss in oof:
        key = f"{ss.route}|{ss.task}"
        m = min(25, sum(len(v) for v in ss.clusters.values()))
        per_archive[key] = {
            "declared": ss.route,
            "identified_whole_set": identify(ss.rows, SIDE_CANDIDATES.routes),
            "n_items": len(ss.rows),
            "n_clusters": len(ss.clusters),
            "subsample_m": m,
            "subsample_identification_rate": round(
                subsample_identification(ss, m, 1000, "main"), 4),
        }
    n_correct = sum(1 for v in per_archive.values()
                    if v["declared"] == v["identified_whole_set"])

    boot: list[float] = []
    for b in range(200):
        rates = []
        for ss in oof:
            rng = random.Random(derive_seed("c2-boot", ss.source_name, b, SEED))
            names = sorted(ss.clusters)
            resampled = [rng.choice(names) for _ in names]
            clusters = {f"{n}#{j}": ss.clusters[n] for j, n in enumerate(resampled)}
            m = min(25, sum(len(v) for v in clusters.values()))
            rates.append(subsample_identification(ss, m, 50, f"boot{b}", clusters))
        boot.append(statistics.fmean(rates))
    boot.sort()

    chance = 1.0 / len(SIDE_CANDIDATES.routes)
    pooled = round(statistics.fmean(
        v["subsample_identification_rate"] for v in per_archive.values()), 4)
    ci_lower = round(boot[int(0.05 * len(boot))], 4)
    return {
        "candidate_set_id": SIDE_CANDIDATES.candidate_set_id,
        "candidates": list(SIDE_CANDIDATES.routes),
        "chance_rate": round(chance, 4),
        "whole_set_correct": f"{n_correct}/{len(per_archive)}",
        "per_archive": per_archive,
        "pooled_subsample_rate": pooled,
        "cluster_bootstrap_ci_lower_5pct": ci_lower,
        "above_chance": ci_lower > chance,
    }


def confusion(oof: tuple[ScoredSet, ...]) -> dict:
    """Full confusion over subsample draws, not just the diagonal.

    Review of the first version of this study asked, correctly, why an archive is
    identified correctly 10.9% of the time against a 33.3% chance rate. A rate below
    chance is not what an information floor produces: a coin-flip between two
    indistinguishable candidates lands AT chance, not under it. Reporting only the
    diagonal makes that impossible to diagnose, so the whole matrix is recorded and
    the answer becomes visible: the misidentifications are not spread over the other
    two labels, they go almost entirely to the archive's same-slug twin.
    """
    out: dict = {}
    for ss in oof:
        counts = dict.fromkeys(SIDE_CANDIDATES.routes, 0)
        m = min(25, sum(len(v) for v in ss.clusters.values()))
        n_draws = 1000
        for i in range(n_draws):
            # Same seed tag and draw count as subsample_identification, so this
            # matrix's diagonal IS the reported identification rate rather than a
            # second Monte Carlo estimate of it that disagrees in the third decimal.
            rng = random.Random(derive_seed("c2-ident", "main", ss.source_name, m, i, SEED))
            counts[identify(cluster_subset(ss.clusters, m, rng),
                            SIDE_CANDIDATES.routes)] += 1
        out[f"{ss.route}|{ss.task}"] = {
            "declared": ss.route,
            "n_draws": n_draws,
            "identified_as": {k: v / n_draws for k, v in counts.items()},
            "diagonal_matches_reported_rate": True,
        }
    return out


def permutation_control(purchased, detector, cal_cfg) -> dict:
    """Break the row-to-route association, refit, and confirm identification collapses.

    The paper claims a producer signal. The standard negative control is to destroy
    that signal while changing nothing else, and check the machinery returns chance.
    Labels are permuted at the ROW level within a task rather than at the archive
    level: relabelling whole archives would leave each archive's own text intact under
    its new name, and the detector would happily learn that, so an archive-level
    permutation tests nothing.
    """
    out = {}
    for task in TASKS:
        sets = [s for s in purchased if s.task == task]
        if len(sets) < 2:
            continue
        rows = [(s.route, r) for s in sets for r in s.rows]
        rng = random.Random(derive_seed("c2-perm", task, SEED))
        labels = [route for route, _ in rows]
        rng.shuffle(labels)
        shuffled: dict[str, list] = {r: [] for r in SIDE_CANDIDATES.routes}
        for (_orig, row), new in zip(rows, labels, strict=True):
            shuffled[new].append(row)
        permuted = [
            dataclasses.replace(s, route=s.route,
                                rows=tuple(shuffled[s.route]))
            for s in sets
        ]
        cal = calibrate(detector, permuted, SIDE_CANDIDATES, cal_cfg)
        correct = sum(1 for ss in cal.oof_scored
                      if identify(ss.rows, SIDE_CANDIDATES.routes) == ss.route)
        # Whole-set identification over three archives has three possible outcomes and
        # cannot distinguish anything; the subsample rate over 1000 draws per archive
        # is what makes this control readable.
        rates = [subsample_identification(ss, min(25, len(ss.rows)), 1000, "perm")
                 for ss in cal.oof_scored]
        out[task] = {
            "archives": len(permuted),
            "whole_set_correct": f"{correct}/{len(permuted)}",
            "pooled_subsample_rate": round(statistics.fmean(rates), 4),
            "chance_rate": round(1.0 / len(SIDE_CANDIDATES.routes), 4),
            "per_archive_rate": [round(r, 4) for r in rates],
        }
    return out


def pair_margins(oof: tuple[ScoredSet, ...]) -> dict:
    """mean log-likelihood under A minus under B, on the archive actually served by A.

    Positive means the archive's own route fits it better than the comparison route
    does. This is the pairwise separation the decision rule talks about, reported as a
    plain quantity rather than folded into a verdict.
    """
    out = {}
    for ss in oof:
        for other in SIDE_CANDIDATES.routes:
            if other == ss.route:
                continue
            own = statistics.fmean(r.scores[ss.route] for r in ss.rows)
            alt = statistics.fmean(r.scores[other] for r in ss.rows)
            out[f"{ss.task}|{ss.route} vs {other}"] = round(own - alt, 6)
    return out


def null_diagnostics(cal) -> dict:
    """How wide is the null each rho* is measured against?

    rho* is a ratio of a spliced shift to the null's spread, so a narrow null makes a
    small effect look resolvable. With 75 items and split-half pairs drawn inside one
    archive, a null can be narrow because the archive is homogeneous rather than
    because the detector is sharp, and the two are not distinguishable from rho* alone.
    Printing the spread is what lets a reader tell the difference.
    """
    out = {}
    for n in cal.nulls:
        draws = n.draws
        if not draws:
            continue
        ordered = sorted(draws)
        out[f"{n.task}|{n.route}|m={n.m}"] = {
            "n_draws": len(draws),
            "n_distinct": len(set(draws)),
            "mean": round(statistics.fmean(draws), 6),
            "stdev": round(statistics.stdev(draws), 6) if len(draws) > 1 else 0.0,
            "q01": round(ordered[max(0, int(0.01 * len(ordered)) - 1)], 6),
            "min": round(ordered[0], 6),
            "max": round(ordered[-1], 6),
            "n_clusters_min": n.n_clusters_min,
            # A null of one repeated value carries no information about spread, so
            # anything derived from it is void rather than merely imprecise.
            "degenerate": len(set(draws)) < 2,
        }
    return out


def c3_power(oof, points, cal_cfg, pow_cfg) -> dict:
    res = power_analysis(oof, SIDE_CANDIDATES, points, cal_cfg, pow_cfg)
    rho: dict[str, float | None] = {}
    records = []
    for p in res.power_points:
        if p.far != FAR:
            continue
        rho[f"{p.task}|{p.declared} substituted_by {p.substitute}|m={p.m}"] = p.rho_min
        records.append((p.task, p.declared, p.substitute, p.m, p.rho_min))

    def at_m(pair, task, m):
        """Worst (largest) rho* over both directions of a pair, at ONE m.

        Taking the max across the whole m grid would report the smallest set's power
        as if it were this archive's, so m is fixed at the archive's own size. None
        means the pair did not resolve at any spliced fraction: strictly weaker than
        a large rho*, and never silently dropped.
        """
        vals = [r[4] for r in records
                if r[0] == task and r[3] == m and {r[1], r[2]} == set(pair)]
        if not vals:
            return "not-calibrated"
        return None if any(v is None for v in vals) else max(vals)

    return {
        "far": FAR,
        "power_target": POWER_TARGET,
        "m": M_EVAL,
        "m_note": (
            f"archives hold {M_ARCHIVE} items; m is capped at {M_EVAL} because a null "
            f"drawn at m={M_ARCHIVE} is every draw the whole archive and collapses to a "
            "single value"),
        "rho_min_by_pair": rho,
        "load_bearing_pair_rho_at_m": {t: at_m(LOAD_BEARING, t, M_EVAL) for t in TASKS},
        "control_pair_rho_at_m": {t: at_m(CONTROL, t, M_EVAL) for t in TASKS},
        "load_bearing_pair_rho_all_m": {
            f"{t}|m={m}": at_m(LOAD_BEARING, t, m) for t in TASKS for m in cal_cfg.m_grid},
        "control_pair_rho_all_m": {
            f"{t}|m={m}": at_m(CONTROL, t, m) for t in TASKS for m in cal_cfg.m_grid},
        "rho_none_means": (
            "the pair did not reach the power target at any spliced fraction on the "
            "rho grid, so no substituted fraction is resolvable for it at this m"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    print("C1  verification under the shipped model")
    c1 = c1_verification(spec_version())
    for r in c1["rulings"]:
        print(f"    {r['provider']:9s} {r['task']:12s} rho_target={r['rho_target']:<4} "
              f"{r['verdict']:14s} T={r['statistic']:+.4f} thr={r['threshold']:+.4f} "
              f"rho*={r['rho_min']} {','.join(r['reasons']) if r['reasons'] else ''}")

    print("\nC2/C3  side model: fit, identify, power")
    purchased = load_purchased()
    detector = build_detector("chargram", view="CANON@1")
    cal_cfg = CalibrationConfig(
        far_grid=(0.001, 0.005, 0.01, 0.05, 0.1),
        m_grid=(25, M_EVAL),
        n_null=5000,
        seed=SEED,
        min_clusters=8,
    )
    cal = calibrate(detector, purchased, SIDE_CANDIDATES, cal_cfg)
    c2 = c2_identification(cal.oof_scored)
    margins = pair_margins(cal.oof_scored)
    pow_cfg = PowerConfig(n_splice=400, power_target=POWER_TARGET, seed=SEED)
    c3 = c3_power(cal.oof_scored, cal.operating_points, cal_cfg, pow_cfg)

    for k, v in c2["per_archive"].items():
        mark = "ok" if v["declared"] == v["identified_whole_set"] else "MISIDENTIFIED"
        print(f"    {k:58s} {mark:14s} sub-rate={v['subsample_identification_rate']}")
    print(f"    whole-set {c2['whole_set_correct']}, pooled {c2['pooled_subsample_rate']}, "
          f"CI lower {c2['cluster_bootstrap_ci_lower_5pct']} vs chance {c2['chance_rate']}")
    print("\n    pairwise margins (own route minus comparison, out-of-fold):")
    for k, v in sorted(margins.items()):
        print(f"      {k:70s} {v:+.4f}")
    print(f"\n    rho* (min resolvable substituted fraction) at far=0.01, m={M_EVAL}:")
    print(f"      load-bearing pair : {c3['load_bearing_pair_rho_at_m']}")
    print(f"      control pair      : {c3['control_pair_rho_at_m']}")
    print("    across the m grid:")
    print(f"      load-bearing      : {c3['load_bearing_pair_rho_all_m']}")
    print(f"      control           : {c3['control_pair_rho_all_m']}")

    conf = confusion(cal.oof_scored)
    print("\n    confusion over subsample draws (where the misses actually go):")
    for k, v in sorted(conf.items()):
        row = "  ".join(f"{r.split('/')[0][:9]}={p:.3f}"
                        for r, p in sorted(v["identified_as"].items()))
        print(f"      {k[:52]:52s} {row}")

    perm = permutation_control(purchased, detector, cal_cfg)
    # Three archives per task is too few to read one task's rate on its own; pooled
    # across both tasks is the figure the paper quotes.
    perm["pooled_over_tasks"] = round(
        statistics.fmean(v["pooled_subsample_rate"] for v in perm.values()), 4)
    perm["chance_rate"] = round(1.0 / len(SIDE_CANDIDATES.routes), 4)
    print("\n    row-label permutation control (signal destroyed, machinery unchanged):")
    for task in TASKS:
        v = perm[task]
        print(f"      {task:14s} pooled subsample {v['pooled_subsample_rate']} "
              f"vs chance {v['chance_rate']}  (whole-set {v['whole_set_correct']})")
    print(f"      {'BOTH TASKS':14s} {perm['pooled_over_tasks']} vs chance "
          f"{perm['chance_rate']}  (unpermuted: {c2['pooled_subsample_rate']})")

    nulls = null_diagnostics(cal)
    degenerate = sorted(k for k, v in nulls.items() if v["degenerate"])
    print(f"\n    null spread at m={M_EVAL} (rho* is relative to this):")
    for k, v in sorted(nulls.items()):
        if k.endswith(f"m={M_EVAL}"):
            print(f"      {k[:62]:62s} sd={v['stdev']:.5f} q01={v['q01']:+.5f} "
                  f"distinct={v['n_distinct']}/{v['n_draws']}"
                  f"{'  DEGENERATE' if v['degenerate'] else ''}")
    print(f"    degenerate nulls anywhere in the grid: "
          f"{degenerate if degenerate else 'none'}")

    doc = {
        "punchmark_schema": "angle_c_evaluation/v1",
        "seed": SEED,
        "c1_verification_shipped_model": c1,
        "c2_identification_side_model": c2,
        "c2_pairwise_margins": margins,
        "c2_confusion": conf,
        "c2_permutation_control": perm,
        "c3_power": c3,
        "c3_null_diagnostics": nulls,
        "alternative_space_note": (
            "The shipped model's candidate set holds one entry for the committed slug, "
            "so the alternatives its statistic is tested against are the three OTHER "
            "model families. A same-model provider swap is not among them. The C1 "
            "rho_min of 1.0 is therefore the resolvable fraction against those three "
            "alternatives and is not a power statement about a provider swap; the side "
            "model, whose candidate set separates the providers, is the only part of "
            "this study that measures provider separability."),
    }
    if args.write:
        DERIVED.mkdir(parents=True, exist_ok=True)
        write_text_deterministic(DERIVED / "angle_c_evaluation.json", canonical_json(doc))
        print(f"\nwrote {(DERIVED / 'angle_c_evaluation.json').relative_to(ROOT)}")
    else:
        print("\n(dry run; pass --write to record derived/angle_c_evaluation.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
