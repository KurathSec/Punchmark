#!/usr/bin/env python3
"""Angle B, archive-side half: can the archive-only channel carry the signal that
published work obtained from crafted probes and chat text?

The closest published figure is llm-idiosyncrasies' 97.1% five-way per-response
producer classification on chat text (ICML 2025, trained classifier, free
sampling). This study asks the analogous question of this corpus: per-ROW
producer classification accuracy, four-way, on held-out code-task archives,
using the shipped closed-form chargram model. The settings differ in domain
(code, not chat), candidate count (4, not 5), sampling (temperature 0), and
classifier family, so the published number is a reference point and never a
target to beat. What matters is the order of magnitude: does a single archived
row carry producer signal comparable to a single chat response?

Two variants per archive:
- pooled: the row's draws pooled as shipped (PMK-FEA-002);
- first_draw: only raw_outputs[0], the closest match to per-response
  classification.

Writes derived/per_row_identification.json. The model-equality-testing package
attempt (the other half of Angle B) is meq_probe.py, which runs in its own
scratch environment because that package is not a punchmark dependency.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from punchmark.archive import read_archive  # noqa: E402
from punchmark.canonical import canonical_json, write_text_deterministic  # noqa: E402
from punchmark.detector import fitted_from_params  # noqa: E402
from punchmark.model import CandidateSet, ResponseRow  # noqa: E402
from punchmark.modelfile import read_model  # noqa: E402
from punchmark.sidecar import load_and_attach  # noqa: E402

CAL_DIR = ROOT / "calibration" / "spaghetti"
DERIVED = HERE / "derived"

ROUTES = (
    "deepseek-ai/DeepSeek-V4-Flash",
    "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "meta-llama/Meta-Llama-3.1-8B-Instruct",
    "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
)
CANDIDATES = CandidateSet(routes=tuple(sorted(ROUTES)))
HELDOUT = [("bench/out/g3", "comprehend_test", "comprehend"),
           ("bench/out/g3", "refactor_test", "refactor_dev")]


def first_draw_only(row: ResponseRow) -> ResponseRow:
    return ResponseRow(
        sample=row.sample, profile=row.profile, language=row.language,
        variant=row.variant, tier=row.tier, intrinsic=row.intrinsic,
        raw_outputs=row.raw_outputs[:1], is_stub=row.is_stub,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="/home/kureist/Spaghetti-Architect")
    args = parser.parse_args()
    source = Path(args.source)
    DERIVED.mkdir(parents=True, exist_ok=True)

    doc = read_model(CAL_DIR / "goldens" / "default.pmk-model.json")
    fitted = fitted_from_params(doc.detector_id, doc.candidates, doc.params, doc.view)

    per_archive: dict[str, dict[str, object]] = {}
    totals = {"pooled": [0, 0], "first_draw": [0, 0]}
    for rel_dir, task, model_task in HELDOUT:
        for route in sorted(ROUTES):
            path = source / rel_dir / f"{task}__{route.replace('/', '-')}.jsonl.gz"
            rs = read_archive(path, CANDIDATES)
            rs = load_and_attach(rs, path, CAL_DIR / "sidecars")
            rows = rs.valid_rows
            entry: dict[str, object] = {"task": task, "route": route, "n_rows": len(rows)}
            for variant, prepared in (
                ("pooled", list(rows)),
                ("first_draw", [first_draw_only(r) for r in rows]),
            ):
                scored = fitted.score_rows(prepared, model_task)
                correct = sum(
                    1 for s in scored if max(s, key=lambda c: s[c]) == route
                )
                entry[f"acc_{variant}"] = round(correct / len(rows), 4)
                totals[variant][0] += correct
                totals[variant][1] += len(rows)
            per_archive[rs.source_name] = entry

    pooled_all = {v: round(c / n, 4) for v, (c, n) in totals.items()}
    by_task = {}
    for task in ("comprehend_test", "refactor_test"):
        accs = [e["acc_first_draw"] for e in per_archive.values() if e["task"] == task]
        by_task[task] = round(statistics.fmean(accs), 4)

    body = {
        "question": (
            "per-row producer classification on held-out archives: does one "
            "archived row carry producer signal comparable to one chat response "
            "in the published per-response setting?"
        ),
        "reference_point": {
            "figure": "97.1% five-way per-response accuracy on chat text",
            "source": "llm-idiosyncrasies (ICML 2025)",
            "non_comparability": (
                "different domain (code vs chat), candidate count (4 vs 5), "
                "sampling (temperature 0 vs free), and classifier family "
                "(closed-form multinomial vs trained classifier); a reference "
                "point, never a target"
            ),
        },
        "chance_level": 0.25,
        "per_archive": per_archive,
        "pooled": pooled_all,
        "first_draw_by_task_mean": by_task,
        "model_id": doc.model_id,
    }
    write_text_deterministic(DERIVED / "per_row_identification.json", canonical_json(body))
    print(f"pooled per-row accuracy: {pooled_all}")
    for name, e in sorted(per_archive.items()):
        print(f"  {e['acc_first_draw']:.4f} first-draw  {e['acc_pooled']:.4f} pooled  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
