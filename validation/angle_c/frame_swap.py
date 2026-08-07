#!/usr/bin/env python3
"""Put a detector that CAN see the provider distinction through the verdict frame.

The paper claims the detector is a replaceable slot and the calibration frame supplies
the guarantee. Review pointed out, correctly, that the claim is asserted and never
exercised: the side model of the identification study is used for argmax only, outside
the calibration, and is explicitly "never used as an operating point". So every negative
result in the paper is measured with the deliberately plain detector, and nothing
separates "this regime is hard" from "this slot occupant is weak".

This runs the experiment. The side model's candidate set contains BOTH providers, so it
can express the alternative the shipped candidate set cannot. We then pose the actual
substitution question in the frame's own terms: take the archive served by provider B,
declare it to be provider A's route, calibrate a threshold from provider A's own null,
and ask for a verdict.

If the frame issues SUBSTITUTED, the design claim is demonstrated rather than argued:
the frame works, and the shipped null was a property of an under-specified candidate set.
If it does not, the frame is weaker than claimed and that is the more important result.

Usage:  .venv/bin/python validation/angle_c/frame_swap.py [--write]
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
    calibrate,
    cluster_subset,
    t_statistic,
)
from punchmark.canonical import (  # noqa: E402
    canonical_json,
    derive_seed,
    write_text_deterministic,
)
from punchmark.detector import build_detector  # noqa: E402
from punchmark.model import CandidateSet  # noqa: E402
from punchmark.sidecar import load_and_attach  # noqa: E402

ARCHIVES = HERE / "archives"
OUT = HERE / "derived" / "frame_swap.json"
SEED = 20260806
TASKS = ("comprehend", "refactor_dev")
SLUG = "meta-llama-Llama-3.3-70B-Instruct-Turbo"
EIGHT = "meta-llama-Meta-Llama-3.1-8B-Instruct-Turbo"
FAR = 0.01
M_EVAL = 50

A = "deepinfra/Llama-3.3-70B"        # the route an archive would declare
B = "together/Llama-3.3-70B"         # the producer that actually served the swap
C8 = "deepinfra/Llama-3.1-8B"        # different-weights control, keeps the set honest
CANDS = CandidateSet((A, B, C8))


def load(provider: str, slug: str, task: str, label: str):
    path = ARCHIVES / provider / f"{task}__{slug}.jsonl.gz"
    if not path.exists():
        return None
    return dataclasses.replace(load_and_attach(read_archive(path), path), route=label)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    detector = build_detector("chargram", view="CANON@1")
    cfg = CalibrationConfig(far_grid=(FAR,), m_grid=(25, M_EVAL), n_null=5000,
                            seed=SEED, min_clusters=8)
    results = {}

    for task in TASKS:
        sets = [load("deepinfra", SLUG, task, A),
                load("together", SLUG, task, B),
                load("deepinfra", EIGHT, task, C8)]
        if any(s is None for s in sets):
            results[task] = {"error": "archive missing"}
            continue

        cal = calibrate(detector, sets, CANDS, cfg)
        by_route = {ss.route: ss for ss in cal.oof_scored}
        thr = {p.route: p.threshold for p in cal.operating_points
               if p.far == FAR and p.m == M_EVAL}

        # The substitution question, in the frame's own terms: provider B's archive,
        # DECLARED as provider A's route, judged against A's calibrated null.
        swapped = by_route[B]
        t_swap = t_statistic(swapped.rows, A, CANDS.routes)
        # Control: provider A's own archive, declared honestly. Should not flag.
        t_honest = t_statistic(by_route[A].rows, A, CANDS.routes)

        # Subsample the statistic so the verdict is not one draw of one number.
        def sub(ss, declared, task=task):
            vals = []
            for i in range(500):
                rng = random.Random(derive_seed("frame", task, declared, ss.source_name,
                                                i, SEED))
                vals.append(t_statistic(cluster_subset(ss.clusters, M_EVAL, rng),
                                        declared, CANDS.routes))
            return vals

        v_swap, v_honest = sub(swapped, A), sub(by_route[A], A)
        t_a = thr.get(A)
        results[task] = {
            "threshold_for_declared_route": t_a,
            "swapped_archive_declared_as_A": {
                "T_whole_set": round(t_swap, 6),
                "T_subsample_mean": round(statistics.fmean(v_swap), 6),
                "share_of_subsamples_below_threshold": (
                    round(sum(1 for v in v_swap if t_a is not None and v < t_a)
                          / len(v_swap), 4) if t_a is not None else None),
                "verdict": ("SUBSTITUTED" if t_a is not None and t_swap < t_a
                            else "not flagged"),
            },
            "honest_archive_declared_as_A": {
                "T_whole_set": round(t_honest, 6),
                "T_subsample_mean": round(statistics.fmean(v_honest), 6),
                "share_of_subsamples_below_threshold": (
                    round(sum(1 for v in v_honest if t_a is not None and v < t_a)
                          / len(v_honest), 4) if t_a is not None else None),
                "verdict": ("SUBSTITUTED" if t_a is not None and t_honest < t_a
                            else "not flagged"),
            },
        }

    doc = {
        "punchmark_schema": "angle_c_frame_swap/v1",
        "seed": SEED,
        "far": FAR,
        "m": M_EVAL,
        "candidate_set": list(CANDS.routes),
        "question": (
            "Does the verdict frame issue SUBSTITUTED on the real cross-provider swap "
            "when the detector's candidate set can express that alternative? The shipped "
            "candidate set cannot, which is why the shipped instrument did not flag it."),
        "results": results,
    }

    for task, r in results.items():
        if "error" in r:
            print(f"{task}: {r['error']}")
            continue
        s, h = r["swapped_archive_declared_as_A"], r["honest_archive_declared_as_A"]
        print(f"\n{task}  (threshold {r['threshold_for_declared_route']})")
        print(f"  provider B declared as A : T={s['T_whole_set']:+.4f}  "
              f"{s['verdict']:12s}  subsamples below threshold {s['share_of_subsamples_below_threshold']}")
        print(f"  provider A declared as A : T={h['T_whole_set']:+.4f}  "
              f"{h['verdict']:12s}  subsamples below threshold {h['share_of_subsamples_below_threshold']}")

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        write_text_deterministic(OUT, canonical_json(doc))
        print(f"\nwrote {OUT.relative_to(ROOT)}")
    else:
        print("\n(dry run; pass --write to record derived/frame_swap.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
