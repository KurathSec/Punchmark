#!/usr/bin/env python3
"""Does the provider separation survive on first-draw text alone?

The side model's 0.992/0.511 was computed over rows that pool all k=8 draws
(PMK-FEA-002). Review asked whether the long-task separation rides on the
draw-multiplicity channel — how often a temperature-0 endpoint repeats itself across
draws is a serving property, and pooling draws lets it into the counts — rather than
on what any single response says. The test: rerun the identical side-model pipeline
with every row truncated to raw_outputs[0], the closest analogue of per-response
classification. Same candidate frame, same calibration config, same subsample seeds
(the seed stream picks clusters, not text, so the draws pair exactly with the
committed run).

If 0.992 survives, the long-task signal lives in the response text itself. If it
collapses, the committed number is a statement about serving behaviour across draws
and the paper must say so.

Reconciliation: the full-draw pipeline is run first and its three-way diagonals must
match the committed c2_confusion exactly.

Reads the purchased archives only; issues no requests.

Usage:  .venv/bin/python validation/angle_c/first_draw.py [--write]
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from evaluate import (  # noqa: E402
    SIDE_CANDIDATES,
    confusion,
    load_purchased,
    subsample_identification,
)

from punchmark.calibrate import CalibrationConfig, calibrate  # noqa: E402
from punchmark.canonical import canonical_json, write_text_deterministic  # noqa: E402
from punchmark.detector import build_detector  # noqa: E402
from punchmark.model import ResponseRow  # noqa: E402

OUT = HERE / "derived" / "first_draw_side_model.json"
SEED = 20260806
TASKS = ("comprehend", "refactor_dev")
L70 = ("deepinfra/Llama-3.3-70B-Instruct-Turbo", "together/Llama-3.3-70B-Instruct-Turbo")


def first_draw_only(rs):
    rows = tuple(
        ResponseRow(sample=r.sample, profile=r.profile, language=r.language,
                    variant=r.variant, tier=r.tier, intrinsic=r.intrinsic,
                    raw_outputs=r.raw_outputs[:1], is_stub=r.is_stub)
        for r in rs.rows
    )
    return dataclasses.replace(rs, rows=rows)


def side_model_run(purchased) -> tuple[dict, dict]:
    """The committed c2 pipeline: calibrate, then per-archive three-way subsample
    identification and the seed-matched confusion matrix at m=min(25, rows), 1000
    draws, tag 'main' (the committed seed stream, so full-draw and first-draw runs
    use identical cluster draws)."""
    detector = build_detector("chargram", view="CANON@1")
    cal_cfg = CalibrationConfig(far_grid=(0.001, 0.005, 0.01, 0.05, 0.1),
                                m_grid=(25, 50), n_null=5000, seed=SEED,
                                min_clusters=8)
    cal = calibrate(detector, purchased, SIDE_CANDIDATES, cal_cfg)
    rates = {}
    for ss in cal.oof_scored:
        m = min(25, sum(len(v) for v in ss.clusters.values()))
        rates[f"{ss.route}|{ss.task}"] = round(
            subsample_identification(ss, m, 1000, "main"), 4
        )
    return rates, confusion(cal.oof_scored)


def binary_pair_mean(conf: dict, task: str) -> float:
    """The committed renormalisation: each 70B row of the confusion matrix
    renormalised over the two 70B labels (the 8B control column dropped), then the
    mean of the two -- the derivation behind the paper's 0.992/0.511."""
    vals = []
    for r in L70:
        row = conf[f"{r}|{task}"]["identified_as"]
        self_mass = row[r]
        other = next(x for x in L70 if x != r)
        vals.append(self_mass / (self_mass + row[other]))
    return round(sum(vals) / len(vals), 4)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    eval_doc = json.loads(
        (HERE / "derived" / "angle_c_evaluation.json").read_text(encoding="utf-8")
    )
    committed = eval_doc["c2_identification_side_model"]["per_archive"]
    committed_conf = eval_doc["c2_confusion"]

    purchased = load_purchased()

    full, full_conf = side_model_run(purchased)
    for key, want in committed.items():
        if full[key] != want["subsample_identification_rate"]:
            raise SystemExit(f"reconciliation failed at {key}: {full[key]} vs "
                             f"{want['subsample_identification_rate']}")
    for key, want in committed_conf.items():
        if full_conf[key]["identified_as"] != want["identified_as"]:
            raise SystemExit(f"confusion reconciliation failed at {key}")
    print("reconciled: full-draw rates and confusion match the committed c2")

    fd, fd_conf = side_model_run([first_draw_only(rs) for rs in purchased])
    print("\nthree-way subsample identification, chance 0.3333:")
    print(f"{'cell':55s} {'all draws':>9s} {'first draw':>10s}")
    for key in sorted(full):
        print(f"  {key:53s} {full[key]:9.4f} {fd[key]:10.4f}")

    pair_summary = {}
    for task in TASKS:
        pair_summary[task] = {
            "all_draws": {r: full[f"{r}|{task}"] for r in L70},
            "first_draw": {r: fd[f"{r}|{task}"] for r in L70},
            "binary_pair_mean_all_draws": binary_pair_mean(full_conf, task),
            "binary_pair_mean_first_draw": binary_pair_mean(fd_conf, task),
        }
        print(f"  {task}: binary pair mean {pair_summary[task]['binary_pair_mean_all_draws']} "
              f"(all draws) -> {pair_summary[task]['binary_pair_mean_first_draw']} "
              f"(first draw), chance 0.5")

    body = {
        "punchmark_schema": "angle_c_first_draw_side_model/v1",
        "seed": SEED,
        "question": (
            "does the long-task provider separation survive when every row is "
            "truncated to its first draw, i.e. when the draw-multiplicity channel "
            "is removed?"
        ),
        "reconciliation": {"full_draw_rates_and_confusion_match_committed_c2": True},
        "note": (
            "identical pipeline, candidate frame, calibration config and subsample "
            "seed stream as the committed c2; the only change is raw_outputs[:1] "
            "per row. Three-way rates have chance 0.3333; the binary pair means "
            "are the committed renormalisation (each 70B confusion row over the "
            "two 70B labels, 8B column dropped), chance 0.5"
        ),
        "three_way_identification": {
            "all_draws": full,
            "first_draw": fd,
        },
        "confusion_first_draw": fd_conf,
        "load_bearing_pair": pair_summary,
    }

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        write_text_deterministic(OUT, canonical_json(body))
        print(f"\nwrote {OUT.relative_to(ROOT)}")
    else:
        print("\n(dry run; pass --write to record derived/first_draw_side_model.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
