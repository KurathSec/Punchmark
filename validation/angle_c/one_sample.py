#!/usr/bin/env python3
"""Is the closed-set limit a property of the regime, or of a margin statistic?

The paper's organizing claim is that a retrospective auditor cannot flag a producer its
candidate set does not name. Review objected that this is definitional rather than
measured: the set statistic is a MARGIN, l(r0) minus the best competitor in C, and a
margin cannot respond to an alternative outside C. No experiment is needed to know that.

The objection names the test that would settle it. Drop the competitor set entirely and
use a ONE-SAMPLE fit statistic: the mean length-normalised log-likelihood of the archive
under the declared route alone, calibrated against that route's own split-half null. Such
a test flags any departure from r0 whether or not the substitute is enumerated.

  If it flags the cross-provider swap, then the closed-set limit is a property of this
  paper's statistic and not of the retrospective regime, and the organizing claim has to
  be narrowed to say so.

  If it does not flag, the limit survives a formulation designed to escape it, and the
  claim is empirical rather than definitional.

Either answer changes the paper. Reads the purchased archives only; issues no requests.

Usage:  .venv/bin/python validation/angle_c/one_sample.py [--write]
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
from punchmark.calibrate import crossfit_scored, split_half  # noqa: E402
from punchmark.canonical import (  # noqa: E402
    canonical_json,
    derive_seed,
    write_text_deterministic,
)
from punchmark.detector import build_detector  # noqa: E402
from punchmark.model import CandidateSet  # noqa: E402
from punchmark.sidecar import load_and_attach  # noqa: E402

ARCHIVES = HERE / "archives"
OUT = HERE / "derived" / "one_sample.json"
SEED = 20260806
TASKS = ("comprehend", "refactor_dev")
SLUG = "meta-llama-Llama-3.3-70B-Instruct-Turbo"
EIGHT = "meta-llama-Meta-Llama-3.1-8B-Instruct-Turbo"
FAR = 0.01
N_NULL = 5000

A = "deepinfra/Llama-3.3-70B"     # the declared route
B = "together/Llama-3.3-70B"      # the producer that actually served the swap
C8 = "deepinfra/Llama-3.1-8B"     # different weights, a positive control for the test
W2 = "deepinfra-w2"               # same route, same provider, second window


def load(provider: str, slug: str, task: str, label: str):
    path = ARCHIVES / provider / f"{task}__{slug}.jsonl.gz"
    if not path.exists():
        return None
    return dataclasses.replace(load_and_attach(read_archive(path), path), route=label)


def fit_stat(rows, declared: str) -> float:
    """One-sample fit: mean length-normalised log-likelihood under the declared route.

    No competitor appears anywhere in this quantity. That is the point.
    """
    return statistics.fmean(r.scores[declared] for r in rows)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    detector = build_detector("chargram", view="CANON@1")
    results = {}

    for task in TASKS:
        # The fitted reference for the declared route has to come from material
        # independent of anything under test, so the candidate set here exists only to
        # give the detector something to fit; the statistic uses one route's column.
        sets = [load("deepinfra", SLUG, task, A), load("together", SLUG, task, B),
                load("deepinfra", EIGHT, task, C8), load(W2, SLUG, task, "w2/Llama-3.3-70B")]
        sets = [s for s in sets if s is not None]
        if len(sets) < 3:
            results[task] = {"error": "archives missing"}
            continue
        cands = CandidateSet(tuple(sorted(s.route for s in sets)))
        scored = {s.route: s for s in crossfit_scored(detector, sets, cands, SEED)}

        # Null: split-halves of the DECLARED route's own archive, one-sample statistic.
        base = scored[A]
        null = []
        for i in range(N_NULL):
            rng = random.Random(derive_seed("onesample-null", task, i, SEED))
            for half in split_half(base.clusters, rng):
                null.append(fit_stat(half, A))
        null.sort()
        thr = null[max(0, int(FAR * len(null)) - 1)]

        row = {"threshold_at_far": round(thr, 6),
               "null_mean": round(statistics.fmean(null), 6),
               "null_sd": round(statistics.stdev(null), 6),
               "n_null": len(null), "archives": {}}
        for label, ss in sorted(scored.items()):
            stat = fit_stat(ss.rows, A)   # every archive judged AS IF it were route A
            row["archives"][label] = {
                "one_sample_stat_under_declared_route": round(stat, 6),
                "below_threshold": stat < thr,
                "verdict": "SUBSTITUTED" if stat < thr else "not flagged",
            }
        results[task] = row

    swap_flagged = {t: r["archives"][B]["below_threshold"]
                    for t, r in results.items() if "error" not in r}
    doc = {
        "punchmark_schema": "angle_c_one_sample/v1",
        "seed": SEED, "far": FAR,
        "statistic": ("mean length-normalised log-likelihood under the DECLARED route "
                      "only; no competitor set enters the statistic"),
        "question": ("Does a competitor-free formulation flag the cross-provider swap "
                     "that the margin statistic structurally cannot?"),
        "results": results,
        "cross_provider_swap_flagged_by_one_sample_test": swap_flagged,
    }

    for task, r in results.items():
        if "error" in r:
            print(f"{task}: {r['error']}")
            continue
        print(f"\n{task}  threshold {r['threshold_at_far']:+.4f} "
              f"(null mean {r['null_mean']:+.4f}, sd {r['null_sd']:.4f})")
        for label, v in r["archives"].items():
            mark = "  <-- the swap" if label == B else ""
            print(f"   {label:34s} stat={v['one_sample_stat_under_declared_route']:+.4f} "
                  f"{v['verdict']:12s}{mark}")

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        write_text_deterministic(OUT, canonical_json(doc))
        print(f"\nwrote {OUT.relative_to(ROOT)}")
    else:
        print("\n(dry run; pass --write to record derived/one_sample.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
