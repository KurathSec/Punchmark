#!/usr/bin/env python3
"""Where do the misassigned rows go? The four-way per-row confusion matrix.

per_row_identification.json records one cell below chance: DeepSeek-V4-Flash on
comprehend_test identifies per-row at 0.2065 first-draw against a 0.25 chance rate.
Review asked whether that cell has the same structure as the side-model's below-chance
cell in Angle C, where the misses concentrated on a single near-identical twin (there,
0.858 of the together archive's misses landed on the same-slug deepinfra label). The
candidate mechanism here is the byte-identity floor: on the comprehend dev split,
841 of 1500 shared items produce a byte-identical first draw across DeepSeek and
Llama-3.3-70B (census.json), so a per-row classifier may be collapsing those two
classes rather than spreading error uniformly.

run.py computes the predicted label and immediately collapses it to a correct-counter,
so the full matrix requires this re-scoring pass: same shipped model, same archives,
same first-draw/pooled variants. Reconciliation: each diagonal rate must equal the
committed acc_* values in per_row_identification.json exactly.

Zero API calls: reads the sibling checkout's held-out archives and the shipped model.

Usage:  .venv/bin/python validation/angle_b/confusion.py [--source PATH] [--write]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(HERE))

from run import CANDIDATES, HELDOUT, ROUTES, first_draw_only  # noqa: E402

from punchmark.archive import read_archive  # noqa: E402
from punchmark.canonical import canonical_json, write_text_deterministic  # noqa: E402
from punchmark.detector import fitted_from_params  # noqa: E402
from punchmark.modelfile import read_model  # noqa: E402
from punchmark.sidecar import load_and_attach  # noqa: E402

CAL_DIR = ROOT / "calibration" / "spaghetti"
OUT = HERE / "derived" / "per_row_confusion.json"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default=str(ROOT.parent / "Spaghetti-Architect"))
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    source = Path(args.source)

    committed = json.loads(
        (HERE / "derived" / "per_row_identification.json").read_text(encoding="utf-8")
    )["per_archive"]

    doc = read_model(CAL_DIR / "goldens" / "default.pmk-model.json")
    fitted = fitted_from_params(doc.detector_id, doc.candidates, doc.params, doc.view)

    per_archive = {}
    for rel_dir, task, model_task in HELDOUT:
        for route in sorted(ROUTES):
            path = source / rel_dir / f"{task}__{route.replace('/', '-')}.jsonl.gz"
            rs = read_archive(path, CANDIDATES)
            rs = load_and_attach(rs, path, CAL_DIR / "sidecars")
            rows = rs.valid_rows
            entry = {"task": task, "route": route, "n_rows": len(rows)}
            for variant, prepared in (
                ("pooled", list(rows)),
                ("first_draw", [first_draw_only(r) for r in rows]),
            ):
                counts = dict.fromkeys(CANDIDATES.routes, 0)
                for s in fitted.score_rows(prepared, model_task):
                    counts[max(s, key=lambda c: s[c])] += 1
                diag = round(counts[route] / len(rows), 4)
                want = committed[rs.source_name][f"acc_{variant}"]
                if diag != want:
                    raise SystemExit(
                        f"reconciliation failed {rs.source_name}/{variant}: "
                        f"diagonal {diag} vs committed {want}"
                    )
                entry[f"identified_as_{variant}"] = {
                    r: round(c / len(rows), 4) for r, c in counts.items()
                }
            per_archive[rs.source_name] = entry

    # The reviewed cell, read out explicitly.
    cell = per_archive["comprehend_test__deepseek-ai-DeepSeek-V4-Flash.jsonl.gz"]
    fd = cell["identified_as_first_draw"]
    miss_mass = 1.0 - fd["deepseek-ai/DeepSeek-V4-Flash"]
    onto_70b = fd["meta-llama/Llama-3.3-70B-Instruct-Turbo"]
    share = round(onto_70b / miss_mass, 4)

    body = {
        "punchmark_schema": "angle_b_per_row_confusion/v1",
        "question": (
            "does the below-chance cell (DeepSeek on comprehend_test, 0.2065 "
            "first-draw) collapse onto one near-identical class, as Angle C's "
            "below-chance cell does, or spread its error uniformly?"
        ),
        "reconciliation": {"diagonals_match_per_row_identification": True},
        "chance_level": 0.25,
        "per_archive": per_archive,
        "reviewed_cell": {
            "archive": "comprehend_test__deepseek-ai-DeepSeek-V4-Flash.jsonl.gz",
            "first_draw_row": fd,
            "miss_mass": round(miss_mass, 4),
            "share_of_misses_onto_llama70b": share,
            "context": (
                "on the comprehend dev split 841 of 1500 shared items produce a "
                "byte-identical first draw across DeepSeek and Llama-3.3-70B "
                "(census.json), so collapse onto the 70B label is the predicted "
                "structure"
            ),
        },
        "model_id": doc.model_id,
    }

    for name, e in sorted(per_archive.items()):
        fd_row = e["identified_as_first_draw"]
        pretty = "  ".join(f"{r.split('/')[-1][:14]}={v:.3f}" for r, v in fd_row.items())
        print(f"{name.split('.jsonl')[0][:52]:52s} {pretty}")
    print(f"\nreviewed cell: miss mass {body['reviewed_cell']['miss_mass']}, "
          f"share onto Llama-70B {share}")

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        write_text_deterministic(OUT, canonical_json(body))
        print(f"wrote {OUT.relative_to(ROOT)}")
    else:
        print("(dry run; pass --write to record derived/per_row_confusion.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
