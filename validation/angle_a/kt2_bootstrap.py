#!/usr/bin/env python3
"""A cluster bootstrap on the false-alarm rate, replacing an inverted band.

KT2 judges each cell's per-ruling flag rate against a binomial band. Review pointed out
that the band is wrong twice over: the 5000 rulings come from 2500 complementary
split-halves of one archive, so they are nowhere near 5000 independent trials, and no
multiplicity adjustment is applied. The write-up answered by inverting the band to ask at
what effective sample size each exceedance stops clearing, then comparing that to the 74
clusters an archive contains.

That answer is ad hoc, it requires choosing between two readings of the inversion, and
the smallest exceedance survives it by 5%. The direct analysis is available and needs no
new data: resample the archive's clusters with replacement, recompute the flag rate on
each resample, and read a percentile interval off the result. The cluster is the
resampling unit the design already uses everywhere else, so this measures the dependence
rather than bounding it by assumption.

Reads the upstream corpus READ-ONLY and issues no requests.

Usage:
  .venv/bin/python validation/angle_a/kt2_bootstrap.py --source <checkout> [--write]
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from run import (  # noqa: E402
    CANDIDATES,
    FAR,
    SEED,
    load_archives,
    score_all,
)

from punchmark.calibrate import lookup_threshold, split_half, t_statistic  # noqa: E402
from punchmark.canonical import (  # noqa: E402
    canonical_json,
    derive_seed,
    write_text_deterministic,
)
from punchmark.detector import fitted_from_params  # noqa: E402
from punchmark.modelfile import read_model  # noqa: E402

OUT = HERE / "derived" / "kt2_bootstrap.json"
SHIPPED = ROOT / "calibration" / "spaghetti" / "goldens" / "default.pmk-model.json"
N_BOOT = 400           # cluster resamples per cell
N_SPLITS = 250         # split-halves per resample; 2 rulings each
DECLARED = FAR


def flag_rate(clusters: dict, task: str, route: str, doc, tag: str,
              n_splits: int) -> float:
    """Per-ruling flag rate over n_splits cluster-respecting split-halves."""
    flags = n = 0
    for i in range(n_splits):
        rng = random.Random(derive_seed("kt2boot-split", tag, i, SEED))
        for half in split_half(clusters, rng):
            op = lookup_threshold(doc.operating_points, task, route, FAR, len(half))
            if op is None:
                continue
            n += 1
            flags += int(t_statistic(half, route, CANDIDATES.routes) < op.threshold)
    return flags / n if n else 0.0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default="/home/kureist/Spaghetti-Architect")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    doc = read_model(SHIPPED)
    fitted = fitted_from_params(doc.detector_id, doc.candidates, doc.params, doc.view)
    archives = load_archives(Path(args.source))
    tables = score_all(fitted, archives)
    heldout = [rs.source_name for rs in archives["heldout"]]

    per_cell = {}
    for name in sorted(heldout):
        ss = tables[name]
        clusters = ss.clusters
        names = sorted(clusters)
        point = flag_rate(clusters, ss.task, ss.route, doc, f"{name}|point", N_SPLITS)

        draws = []
        for b in range(N_BOOT):
            rng = random.Random(derive_seed("kt2boot-cluster", name, b, SEED))
            picked = [rng.choice(names) for _ in names]
            resampled = {f"{c}#{j}": clusters[c] for j, c in enumerate(picked)}
            draws.append(flag_rate(resampled, ss.task, ss.route, doc,
                                   f"{name}|{b}", max(20, N_SPLITS // 10)))
        # Duplicate-free variant. Bootstrapping a SPLIT-HALF statistic has a
        # pathology: a cluster drawn twice can land in opposite halves, making the two
        # halves artificially similar, depressing T's spread and so depressing the flag
        # rate. That biases the lower tail toward zero, which is exactly the tail the
        # conclusion depends on. Subsampling k of the 74 clusters WITHOUT replacement
        # has no duplicates and so no such bias, at the cost of describing a smaller
        # archive than the real one.
        sub = []
        k = int(0.7 * len(names))
        for b in range(N_BOOT):
            rng = random.Random(derive_seed("kt2boot-sub", name, b, SEED))
            picked = rng.sample(names, k)
            sub.append(flag_rate({c: clusters[c] for c in picked},
                                 ss.task, ss.route, doc, f"{name}|s{b}",
                                 max(20, N_SPLITS // 10)))
        sub.sort()
        s_lo = sub[int(0.025 * len(sub))]
        s_hi = sub[min(len(sub) - 1, int(0.975 * len(sub)))]

        draws.sort()
        lo = draws[int(0.025 * len(draws))]
        hi = draws[min(len(draws) - 1, int(0.975 * len(draws)))]
        per_cell[name] = {
            "n_clusters": len(names),
            "point_flag_rate": round(point, 5),
            "bootstrap_ci95": [round(lo, 5), round(hi, 5)],
            "ci_lower_exceeds_declared_far": lo > DECLARED,
            "subsample_k_of_n": [k, len(names)],
            "subsample_ci95": [round(s_lo, 5), round(s_hi, 5)],
            "subsample_ci_lower_exceeds_declared_far": s_lo > DECLARED,
            "n_boot": N_BOOT,
        }
        print(f"  {name[:52]:52s} rate={point:.4f} "
              f"boot=[{lo:.4f},{hi:.4f}] sub=[{s_lo:.4f},{s_hi:.4f}] "
              f"sub_lower>far: {s_lo > DECLARED}")

    exceeding = sorted(k for k, v in per_cell.items()
                       if v["ci_lower_exceeds_declared_far"])
    doc_out = {
        "punchmark_schema": "angle_a_kt2_bootstrap/v1",
        "declared_far": DECLARED,
        "n_boot": N_BOOT,
        "resampling_unit": "cluster (base sample), resampled with replacement",
        "note": ("Replaces the inverted binomial band with a direct cluster bootstrap. "
                 "A cell is called failing when the 2.5th percentile of its bootstrap "
                 "distribution lies above the declared false-alarm rate, which needs no "
                 "effective-sample-size assumption and no choice between inversions."),
        "per_cell": per_cell,
        "cells_whose_ci_excludes_the_declared_far": exceeding,
        "n_cells_failing": len(exceeding),
    }
    print(f"\ncells whose 95% CI lower bound exceeds the declared {DECLARED}: "
          f"{len(exceeding)} of {len(per_cell)}")
    for k in exceeding:
        print(f"  {k}")

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        write_text_deterministic(OUT, canonical_json(doc_out))
        print(f"\nwrote {OUT.relative_to(ROOT)}")
    else:
        print("\n(dry run; pass --write to record derived/kt2_bootstrap.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
