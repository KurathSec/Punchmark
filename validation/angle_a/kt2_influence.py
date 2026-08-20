#!/usr/bin/env python3
"""Which base samples carry the KT2 exceedances? A direct measurement.

docs/honesty.md and the paper currently read the cluster bootstrap (kt2_bootstrap.json)
as showing that the held-out flagging "concentrates in a minority of base samples:
exclude them and the cell flags nothing". That sentence is an INFERENCE from wide
intervals, not a measurement. Review asked for the measurement (a cluster-level
influence diagnostic), and this script is it. If the sentence is wrong, the docs are
corrected rather than defended.

Design, in three parts, per cell (the three exceedance archives):

1. RECONCILIATION. Regenerate kt2's exact 2,500-split stream (identical seed labels)
   and refuse to proceed unless the recomputed per-ruling flag rate equals the
   committed kt2.json value. Every later number descends from a stream the committed
   artifact already pins.
2. ATTRIBUTION. Over that same stream, each cluster sits in exactly one half per
   split, so its membership contrast is well defined: delta(c) = flag rate of halves
   containing c minus flag rate of the complements.
3. REMOVAL CURVES. Rank clusters once by delta, then re-run the split stream with the
   top-k removed, on a FRESH seed stream: ranking and evaluating on the same stream
   would overstate concentration by selecting on that stream's noise (the in-sample
   curve is also recorded, labelled). A random-removal control (10 subsets per k)
   separates "these particular clusters carry it" from "any shrinkage lowers the
   rate", and it also absorbs the operating-point confound: as clusters are removed,
   half sizes cross the shipped m-grid boundary and the threshold changes for reasons
   unrelated to influence, so op.m is recorded per curve point.

k* is the smallest k whose fresh-stream rate is at or below the declared 0.01; k0 the
smallest whose rate is exactly zero (the docs' literal "flags nothing"). The verdict
vocabulary is LOCALISED / PARTIALLY_LOCALISED / DIFFUSE, and PARTIALLY_LOCALISED means
the docs sentence must soften to "flags at or below the declared rate".

Zero API calls: reads the sibling checkout's archives and the shipped model only.

Usage:  .venv/bin/python validation/angle_a/kt2_influence.py [--source PATH] [--write]
"""

from __future__ import annotations

import argparse
import random
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

import json  # noqa: E402

from punchmark.archive import read_archive  # noqa: E402
from punchmark.calibrate import (  # noqa: E402
    ScoredRow,
    ScoredSet,
    lookup_threshold,
    split_half,
    t_statistic,
)
from punchmark.canonical import (  # noqa: E402
    canonical_json,
    derive_seed,
    write_text_deterministic,
)
from punchmark.detector import fitted_from_params  # noqa: E402
from punchmark.model import CandidateSet  # noqa: E402
from punchmark.modelfile import read_model  # noqa: E402
from punchmark.sidecar import load_and_attach  # noqa: E402

CAL_DIR = ROOT / "calibration" / "spaghetti"
OUT = HERE / "derived" / "kt2_influence.json"
SEED = 20260803          # run.py's seed; the reconciliation stream depends on it
FAR = 0.01
N_SPLITS = 2500          # kt2's split count; 2 rulings per split
N_RAND_REPS = 10
N_RAND_SPLITS = 500
K_MAX = 40

ROUTES = (
    "deepseek-ai/DeepSeek-V4-Flash",
    "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "meta-llama/Meta-Llama-3.1-8B-Instruct",
    "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
)
CANDIDATES = CandidateSet(routes=tuple(sorted(ROUTES)))
TASK_ALIAS = {"comprehend_test": "comprehend", "refactor_test": "refactor_dev"}

# The three exceedance cells (kt2.json measured_pair_flag_rate), rel_dir bench/out/g3.
CELLS = [
    ("comprehend_test", "meta-llama/Meta-Llama-3.1-8B-Instruct", 0.1208),
    ("refactor_test", "meta-llama/Meta-Llama-3.1-8B-Instruct", 0.1144),
    ("refactor_test", "meta-llama/Llama-3.3-70B-Instruct-Turbo", 0.0598),
]


class ClusterSums:
    """Per-cluster score sums making T additive: T over any union of clusters equals
    the row-level t_statistic exactly (T is a difference of per-row means)."""

    def __init__(self, ss: ScoredSet):
        self.route = ss.route
        self.task = ss.task
        self.sums: dict[str, dict[str, float]] = {}
        self.counts: dict[str, int] = {}
        for name, rows in ss.clusters.items():
            acc = dict.fromkeys(CANDIDATES.routes, 0.0)
            for r in rows:
                for c in CANDIDATES.routes:
                    acc[c] += r.scores[c]
            self.sums[name] = acc
            self.counts[name] = len(rows)

    def t_over(self, names) -> tuple[float, int]:
        n = sum(self.counts[c] for c in names)
        means = {
            c: sum(self.sums[name][c] for name in names) / n
            for c in CANDIDATES.routes
        }
        declared = means[self.route]
        best_alt = max(v for c, v in means.items() if c != self.route)
        return declared - best_alt, n


def load_cell(source: Path, task: str, route: str) -> ScoredSet:
    path = source / "bench" / "out" / "g3" / f"{task}__{route.replace('/', '-')}.jsonl.gz"
    rs = read_archive(path, CANDIDATES)
    rs = load_and_attach(rs, path, CAL_DIR / "sidecars")
    doc = read_model(CAL_DIR / "goldens" / "default.pmk-model.json")
    fitted = fitted_from_params(doc.detector_id, doc.candidates, doc.params, doc.view)
    rows = rs.valid_rows
    scored = fitted.score_rows(rows, TASK_ALIAS[task])
    return ScoredSet(
        route=rs.route,
        task=TASK_ALIAS[task],
        source_name=rs.source_name,
        rows=tuple(
            ScoredRow(key=r.item_key, cluster=r.cluster, scores=s)
            for r, s in zip(rows, scored, strict=True)
        ),
    )


def run_stream(cs: ClusterSums, ops, clusters: dict, seed_parts, n_splits: int):
    """Flag rate over a split stream on the given cluster subset. Returns
    (per-ruling rate, per-half membership records or None)."""
    names_all = clusters
    flags = 0
    op_ms = set()
    halves = []
    for i in range(n_splits):
        rng = random.Random(derive_seed(*seed_parts, i, SEED))
        ha, hb = split_half(names_all, rng)
        for half in (ha, hb):
            cl_names = sorted({r.cluster for r in half})
            t, n = cs.t_over(cl_names)
            op = lookup_threshold(ops, cs.task, cs.route, FAR, n)
            is_flagged = op is not None and t < op.threshold
            if op is not None:
                op_ms.add(op.m)
            flags += int(is_flagged)
            halves.append((frozenset(cl_names), is_flagged))
    return flags / (2 * n_splits), halves, sorted(op_ms)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default=str(ROOT.parent / "Spaghetti-Architect"))
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    source = Path(args.source)

    doc = read_model(CAL_DIR / "goldens" / "default.pmk-model.json")
    committed = json.loads(
        (HERE / "derived" / "kt2.json").read_text(encoding="utf-8")
    )["measured_pair_flag_rate"]

    cells_out = {}
    docs_supported = True
    docs_flags_nothing_literal = True
    for task, route, expected in CELLS:
        ss = load_cell(source, task, route)
        cs = ClusterSums(ss)
        clusters = ss.clusters
        n_clusters = len(clusters)
        print(f"\n{ss.source_name}  ({n_clusters} clusters, {len(ss.rows)} rows)")

        # Exactness check: cluster-sum T equals row-level t_statistic.
        rng = random.Random(derive_seed("a4-exactness", ss.source_name, SEED))
        ha, _ = split_half(clusters, rng)
        t_rows = t_statistic(ha, ss.route, CANDIDATES.routes)
        t_sums, _ = cs.t_over(sorted({r.cluster for r in ha}))
        if abs(t_rows - t_sums) > 1e-12:
            raise SystemExit(f"cluster-sum T mismatch: {t_rows} vs {t_sums}")

        # 1. RECONCILIATION on the committed stream.
        rate, halves, _ = run_stream(
            cs, doc.operating_points, clusters, ("kt2-measured", ss.source_name),
            N_SPLITS,
        )
        if abs(rate - committed[ss.source_name]) > 1e-12 or abs(rate - expected) > 5e-5:
            raise SystemExit(
                f"reconciliation failed for {ss.source_name}: recomputed {rate}, "
                f"kt2.json {committed[ss.source_name]}"
            )
        print(f"  reconciled: per-ruling flag rate {rate:.4f} matches kt2.json")

        # 2. ATTRIBUTION: membership contrast over the reconciled stream.
        per_cluster = {}
        for c in sorted(clusters):
            with_f = [f for members, f in halves if c in members]
            without_f = [f for members, f in halves if c not in members]
            rw = sum(with_f) / len(with_f)
            rwo = sum(without_f) / len(without_f)
            per_cluster[c] = {
                "rate_with": round(rw, 6),
                "rate_without": round(rwo, 6),
                "delta": round(rw - rwo, 6),
                "n_with": len(with_f),
                "n_without": len(without_f),
            }
        ranking = sorted(per_cluster, key=lambda c: -per_cluster[c]["delta"])

        # 3. REMOVAL CURVES.
        boundary_note = None
        fresh_curve = []
        insample_curve = []
        rand_curve = []
        k_star = None
        k_zero = None
        for k in range(1, K_MAX + 1):
            removed = set(ranking[:k])
            kept = {c: clusters[c] for c in clusters if c not in removed}

            r_fresh, _, op_ms = run_stream(
                cs, doc.operating_points, kept,
                ("a4-removal-eval", ss.source_name, k), N_SPLITS,
            )
            fresh_curve.append({
                "k": k, "rate": round(r_fresh, 6), "op_m_values": op_ms,
            })
            if boundary_note is None and len(op_ms) > 1:
                boundary_note = k
            if k_star is None and r_fresh <= FAR:
                k_star = k
            if k_zero is None and r_fresh == 0.0:
                k_zero = k

            r_ins, _, _ = run_stream(
                cs, doc.operating_points, kept,
                ("kt2-measured", ss.source_name), N_SPLITS,
            )
            insample_curve.append({"k": k, "rate": round(r_ins, 6)})

            rates_j = []
            for j in range(N_RAND_REPS):
                sel_rng = random.Random(
                    derive_seed("a4-removal-rand-select", ss.source_name, k, j, SEED)
                )
                rand_removed = set(sel_rng.sample(sorted(clusters), k))
                rand_kept = {c: clusters[c] for c in clusters if c not in rand_removed}
                r_j, _, _ = run_stream(
                    cs, doc.operating_points, rand_kept,
                    ("a4-removal-rand", ss.source_name, k, j), N_RAND_SPLITS,
                )
                rates_j.append(r_j)
            rand_curve.append({
                "k": k,
                "mean_rate": round(statistics.fmean(rates_j), 6),
                "min_rate": round(min(rates_j), 6),
                "max_rate": round(max(rates_j), 6),
                "n_reps": N_RAND_REPS,
                "n_splits": N_RAND_SPLITS,
            })

        minority = n_clusters // 2
        rand_at_kstar = (
            rand_curve[k_star - 1]["mean_rate"] if k_star is not None else None
        )
        tolerance = 0.0144  # the screening tolerance, used only to read the control
        if k_star is not None and k_star < minority and (
            rand_at_kstar is not None and rand_at_kstar > tolerance
        ):
            verdict = "LOCALISED" if k_zero is not None and k_zero <= K_MAX else (
                "PARTIALLY_LOCALISED"
            )
        elif k_star is not None and k_star < minority:
            verdict = "PARTIALLY_LOCALISED"
        else:
            verdict = "DIFFUSE"
            docs_supported = False
        if k_zero is None or k_zero > K_MAX:
            docs_flags_nothing_literal = False

        print(f"  k*={k_star} (rate<=0.01), k0={k_zero} (rate==0), "
              f"random control at k*: {rand_at_kstar}  ->  {verdict}")

        cells_out[ss.source_name] = {
            "task_scored_as": cs.task,
            "route": route,
            "n_clusters": n_clusters,
            "recomputed_rate": round(rate, 6),
            "matches_kt2_json": True,
            "per_cluster": per_cluster,
            "ranking_by_delta": ranking,
            "removal_targeted_fresh_stream": fresh_curve,
            "removal_targeted_committed_stream": insample_curve,
            "removal_targeted_committed_stream_note":
                "in-sample in the seed stream the ranking was computed on; "
                "shown for comparison only",
            "removal_random": rand_curve,
            "op_m_boundary_first_crossed_at_k": boundary_note,
            "k_star_rate_leq_declared_far": k_star,
            "k_zero_flags": k_zero,
            "minority_bound": minority,
            "verdict": verdict,
        }

    doc_out = {
        "punchmark_schema": "angle_a_kt2_influence/v1",
        "seed": SEED,
        "declared_far": FAR,
        "n_splits": N_SPLITS,
        "question": (
            "Does the held-out flagging concentrate in a minority of base samples, as "
            "docs/honesty.md currently infers from the cluster bootstrap, or is it "
            "diffuse?"
        ),
        "method": (
            "Membership contrast on the exact committed kt2 split stream "
            "(reconciled per cell before any new number), then top-k removal curves "
            "evaluated on fresh seed streams with a random-removal control. op.m is "
            "recorded per curve point because removal shrinks halves across the "
            "shipped m-grid boundary, which moves the threshold for reasons "
            "unrelated to influence."
        ),
        "cells": cells_out,
        "docs_claim": {
            "text": (
                "flagging concentrates in a minority of base samples: exclude them "
                "and the cell flags nothing"
            ),
            "minority_supported_all_cells": docs_supported,
            "flags_nothing_literal_all_cells": docs_flags_nothing_literal,
        },
    }

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        write_text_deterministic(OUT, canonical_json(doc_out))
        print(f"\nwrote {OUT.relative_to(ROOT)}")
    else:
        print("\n(dry run; pass --write to record derived/kt2_influence.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
