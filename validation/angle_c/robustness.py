#!/usr/bin/env python3
"""Two robustness checks review asked for, both free.

1. A permutation DISTRIBUTION, not one draw. The write-up reported a single
   row-label permutation and correctly declined to call it a p-value. Review pointed
   out that the long-task permuted rate (0.438 against a chance rate of 0.3333) sits
   well above chance on the one task where the positive result lives, and that one
   draw cannot say whether that matters. Running many permutations turns the sanity
   check into a test.

2. Leave-4-out sensitivity for the rate-limited requests. Four of the Together
   refactor archive's POSTs were shed to rate limiting and retried, and that archive
   is one of the two in the headline contrast. The per-item record does not identify
   WHICH items were affected, because the 429 counter is per-archive. So the affected
   rows cannot be dropped directly. Dropping every 4-item subset instead answers the
   stronger question: does removing ANY four items move the result? If not, removing
   the four unknown ones cannot either.

Reads the purchased archives only. Issues no requests.

Usage:  .venv/bin/python validation/angle_c/robustness.py [--write]
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
from punchmark.calibrate import cluster_subset, crossfit_scored, identify  # noqa: E402
from punchmark.canonical import (  # noqa: E402
    canonical_json,
    derive_seed,
    write_text_deterministic,
)
from punchmark.detector import build_detector  # noqa: E402
from punchmark.model import CandidateSet  # noqa: E402
from punchmark.sidecar import load_and_attach  # noqa: E402

ARCHIVES = HERE / "archives"
OUT = HERE / "derived" / "robustness.json"
SEED = 20260806
TASKS = ("comprehend", "refactor_dev")
SLUG = "meta-llama-Llama-3.3-70B-Instruct-Turbo"
EIGHT = "meta-llama-Meta-Llama-3.1-8B-Instruct-Turbo"
N_PERM = 200
N_LEAVE = 200
K_LEAVE = 4

A = "deepinfra/Llama-3.3-70B"
B = "together/Llama-3.3-70B"
C8 = "deepinfra/Llama-3.1-8B"
CANDS = CandidateSet((A, B, C8))


def load(provider: str, slug: str, task: str, label: str):
    path = ARCHIVES / provider / f"{task}__{slug}.jsonl.gz"
    if not path.exists():
        return None
    return dataclasses.replace(load_and_attach(read_archive(path), path), route=label)


def pooled_rate(scored, tag: str, n_draws: int = 300) -> float:
    """Mean over archives of the cluster-respecting subsample identification rate."""
    rates = []
    for ss in scored:
        m = min(25, sum(len(v) for v in ss.clusters.values()))
        hit = 0
        for i in range(n_draws):
            rng = random.Random(derive_seed("rob", tag, ss.source_name, m, i, SEED))
            hit += int(identify(cluster_subset(ss.clusters, m, rng), CANDS.routes)
                       == ss.route)
        rates.append(hit / n_draws)
    return statistics.fmean(rates)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    detector = build_detector("chargram", view="CANON@1")
    out: dict = {"punchmark_schema": "angle_c_robustness/v1", "seed": SEED,
                 "n_permutations": N_PERM, "chance_rate": round(1 / 3, 4),
                 "permutation": {}, "leave_k_out": {}}

    for task in TASKS:
        sets = [load("deepinfra", SLUG, task, A), load("together", SLUG, task, B),
                load("deepinfra", EIGHT, task, C8)]
        if any(s is None for s in sets):
            continue

        observed = pooled_rate(crossfit_scored(detector, sets, CANDS, SEED), f"obs{task}")

        # 1. Permutation distribution: destroy the row-to-route association B times.
        null = []
        rows = [(s.route, r) for s in sets for r in s.rows]
        for b in range(N_PERM):
            rng = random.Random(derive_seed("rob-perm", task, b, SEED))
            labels = [r for r, _ in rows]
            rng.shuffle(labels)
            bag: dict[str, list] = {r: [] for r in CANDS.routes}
            for (_o, row), new in zip(rows, labels, strict=True):
                bag[new].append(row)
            permuted = [dataclasses.replace(s, rows=tuple(bag[s.route])) for s in sets]
            null.append(pooled_rate(crossfit_scored(detector, permuted, CANDS, SEED),
                                    f"p{task}{b}", n_draws=100))
        null.sort()
        # One-sided: how often does destroyed-signal data reach the observed rate?
        n_ge = sum(1 for v in null if v >= observed)
        out["permutation"][task] = {
            "observed_pooled_rate": round(observed, 4),
            "permutation_null_mean": round(statistics.fmean(null), 4),
            "permutation_null_p05": round(null[int(0.05 * len(null))], 4),
            "permutation_null_p95": round(null[min(len(null) - 1,
                                                   int(0.95 * len(null)))], 4),
            "permutation_null_max": round(null[-1], 4),
            "n_null_ge_observed": n_ge,
            "p_value": round((n_ge + 1) / (N_PERM + 1), 5),
        }

        # 2. Leave-k-out on the Together archive, the one carrying the shed requests.
        tog = next(s for s in sets if s.route == B)
        keys = sorted({r.item_key for r in tog.rows})
        rates = []
        for i in range(N_LEAVE):
            rng = random.Random(derive_seed("rob-leave", task, i, SEED))
            drop = set(rng.sample(keys, K_LEAVE))
            trimmed = dataclasses.replace(
                tog, rows=tuple(r for r in tog.rows if r.item_key not in drop))
            trial = [trimmed if s.route == B else s for s in sets]
            sc = crossfit_scored(detector, trial, CANDS, SEED)
            tg = next(s for s in sc if s.route == B)
            m = min(25, sum(len(v) for v in tg.clusters.values()))
            hit = 0
            for j in range(200):
                rr = random.Random(derive_seed("rob-lv", task, i, j, SEED))
                hit += int(identify(cluster_subset(tg.clusters, m, rr), CANDS.routes)
                           == B)
            rates.append(hit / 200)
        rates.sort()
        out["leave_k_out"][task] = {
            "k_dropped": K_LEAVE,
            "n_trials": N_LEAVE,
            "together_identification_min": round(rates[0], 4),
            "together_identification_median": round(statistics.median(rates), 4),
            "together_identification_max": round(rates[-1], 4),
        }

    for task in TASKS:
        p = out["permutation"].get(task)
        lv = out["leave_k_out"].get(task)
        if p:
            print(f"{task:14s} observed {p['observed_pooled_rate']}  "
                  f"perm null mean {p['permutation_null_mean']} "
                  f"[p05 {p['permutation_null_p05']}, p95 {p['permutation_null_p95']}, "
                  f"max {p['permutation_null_max']}]  p={p['p_value']}")
        if lv:
            print(f"{'':14s} leave-{K_LEAVE}-out Together id: "
                  f"{lv['together_identification_min']} to "
                  f"{lv['together_identification_max']} "
                  f"(median {lv['together_identification_median']})")

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        write_text_deterministic(OUT, canonical_json(out))
        print(f"\nwrote {OUT.relative_to(ROOT)}")
    else:
        print("\n(dry run; pass --write to record derived/robustness.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
