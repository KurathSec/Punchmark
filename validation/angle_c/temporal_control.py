#!/usr/bin/env python3
"""The same-provider control: is the provider signature a provider signature?

Study C reports that a purpose-built discriminator separates two providers serving the
same slug on the long task. Review raised the obvious competing explanation and it has
no answer inside the original design: the two archives were also two separate
collections, so anything that differs between collection batches (queue state, batch
composition, which replica answered) is confounded with the provider.

The control is to run the identical pipeline on two collections of the SAME route from
the SAME provider, in different windows, and ask how well it separates them. If a
same-provider pair separates about as well as the cross-provider pair, the cross-provider
number measures collection conditions rather than providers, and Study C's positive
finding does not stand. If it separates much less, the provider signature survives.

This is the honest form of the test: it can refute the paper's own result, and it is
reported either way.

Usage:  .venv/bin/python validation/angle_c/temporal_control.py [--write]
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
    identify,
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
OUT = HERE / "derived" / "temporal_control.json"
SEED = 20260806
TASKS = ("comprehend", "refactor_dev")
SLUG = "meta-llama-Llama-3.3-70B-Instruct-Turbo"

# Two contrasts, run through identical machinery so the numbers are comparable.
#   PROVIDER  : deepinfra window 1  vs  together window 1     (what Study C claims)
#   TEMPORAL  : deepinfra window 1  vs  deepinfra window 2    (the control)
CONTRASTS = {
    "provider_w1_vs_w1": (("deepinfra", "A"), ("together", "B")),
    "temporal_same_provider_w1_vs_w2": (("deepinfra", "A"), ("deepinfra-w2", "B")),
}


def load(provider: str, task: str, label: str):
    path = ARCHIVES / provider / f"{task}__{SLUG}.jsonl.gz"
    if not path.exists():
        return None
    rs = load_and_attach(read_archive(path), path)
    return dataclasses.replace(rs, route=label)


def rate(ss, cands, m, n_draws, tag) -> float:
    correct = 0
    for i in range(n_draws):
        rng = random.Random(derive_seed("tc", tag, ss.source_name, m, i, SEED))
        if identify(cluster_subset(ss.clusters, m, rng), cands) == ss.route:
            correct += 1
    return correct / n_draws


def run(name: str, pair, cfg, detector) -> dict:
    cands = CandidateSet(("A", "B"))
    out: dict = {"contrast": name, "chance_rate": 0.5, "by_task": {}}
    for task in TASKS:
        sets = [load(prov, task, label) for prov, label in pair]
        if any(s is None for s in sets):
            out["by_task"][task] = {"error": "archive missing"}
            continue
        cal = calibrate(detector, sets, cands, cfg)
        m = min(25, min(len(s.rows) for s in sets))
        rates = {ss.route: round(rate(ss, cands.routes, m, 1000, name), 4)
                 for ss in cal.oof_scored}
        margins = {}
        for ss in cal.oof_scored:
            other = next(c for c in cands.routes if c != ss.route)
            own = statistics.fmean(r.scores[ss.route] for r in ss.rows)
            alt = statistics.fmean(r.scores[other] for r in ss.rows)
            margins[ss.route] = round(own - alt, 6)
        out["by_task"][task] = {
            "subsample_m": m,
            "identification_by_side": rates,
            "mean_identification": round(statistics.fmean(rates.values()), 4),
            "out_of_fold_margins": margins,
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    detector = build_detector("chargram", view="CANON@1")
    cfg = CalibrationConfig(far_grid=(0.01,), m_grid=(25, 50), n_null=2000,
                            seed=SEED, min_clusters=8)

    results = {name: run(name, pair, cfg, detector) for name, pair in CONTRASTS.items()}

    prov = results["provider_w1_vs_w1"]["by_task"]
    temp = results["temporal_same_provider_w1_vs_w2"]["by_task"]
    verdict = {}
    for task in TASKS:
        p = prov.get(task, {}).get("mean_identification")
        t = temp.get(task, {}).get("mean_identification")
        if p is None or t is None:
            continue
        verdict[task] = {
            "provider_pair": p,
            "same_provider_two_windows": t,
            "gap": round(p - t, 4),
            "reading": (
                "cross-provider separation exceeds same-provider-across-windows "
                "separation, so the provider contrast is not explained by collection "
                "batch alone" if p - t > 0.15 else
                "same-provider windows separate comparably, so the cross-provider "
                "number is not distinguishable from a collection-batch effect"),
        }

    doc = {
        "punchmark_schema": "angle_c_temporal_control/v1",
        "seed": SEED,
        "note": ("Binary contrasts through identical machinery. Chance is 0.5. The "
                 "temporal contrast is the same route at the same provider in two "
                 "windows, which is the control the original design lacked."),
        "results": results,
        "verdict_by_task": verdict,
    }

    for name, r in results.items():
        print(f"\n{name}")
        for task in TASKS:
            b = r["by_task"].get(task, {})
            if "error" in b:
                print(f"  {task:14s} {b['error']}")
                continue
            print(f"  {task:14s} mean identification {b['mean_identification']} "
                  f"(chance 0.5)  per side {b['identification_by_side']}")
    print("\nverdict:")
    for task, v in verdict.items():
        print(f"  {task:14s} provider {v['provider_pair']} vs same-provider "
              f"{v['same_provider_two_windows']}  gap {v['gap']:+.4f}")
        print(f"                 {v['reading']}")

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        write_text_deterministic(OUT, canonical_json(doc))
        print(f"\nwrote {OUT.relative_to(ROOT)}")
    else:
        print("\n(dry run; pass --write to record derived/temporal_control.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
