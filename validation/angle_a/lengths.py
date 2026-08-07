#!/usr/bin/env python3
"""Completion length per task, and what it does and does not explain.

Two questions the write-up left open, both answerable from the committed corpus with no
new data:

  1. The formatting ablation truncates completions to 200 characters. On a task whose
     completions are shorter than that, the truncation is a no-op and the "ablated" view
     is the canonical view. The paper could not say which tasks that applied to, because
     per-task lengths were never measured.

  2. Study C attributes its short/long provider split to text volume. That is a
     two-point observation. Study A holds four routes over two tasks with the same
     length asymmetry, so the same mechanism can be checked against per-row separability
     on a much larger corpus.

The answer to the second turns out to be a distinction rather than a confirmation, which
is why this script exists rather than a sentence asserting the mechanism.

Reads the upstream corpus READ-ONLY. Issues no requests.

Usage:  .venv/bin/python validation/angle_a/lengths.py --source <checkout> [--write]
"""

from __future__ import annotations

import argparse
import gzip
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from punchmark.canonical import canonical_json, write_text_deterministic  # noqa: E402

OUT = HERE / "derived" / "lengths.json"
ABLATION_TRUNCATION = 200      # the ABL@1 view's character cut
SPLITS = (("ladder", "comprehend__*.jsonl.gz"),
          ("g3", "refactor_dev__*.jsonl.gz"),
          ("g3", "comprehend_test__*.jsonl.gz"),
          ("g3", "refactor_test__*.jsonl.gz"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", default="/home/kureist/Spaghetti-Architect")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    src = Path(args.source) / "bench" / "out"

    per_archive: dict[str, dict] = {}
    for sub, pat in SPLITS:
        for path in sorted((src / sub).glob(pat)):
            lens: list[int] = []
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                for line in fh:
                    rec = json.loads(line)
                    lens.extend(len(d) for d in (rec.get("raw_outputs") or []))
            if not lens:
                continue
            task, rest = path.name.split("__", 1)
            per_archive[f"{task}__{rest.replace('.jsonl.gz', '')}"] = {
                "task": task,
                "route_slug": rest.replace(".jsonl.gz", ""),
                "draws": len(lens),
                "median_chars": round(statistics.median(lens), 1),
                "mean_chars": round(statistics.fmean(lens), 1),
                # The share the ablation actually cuts. Where this is ~0 the ABL view
                # is the canonical view and the ablation tested nothing.
                "share_longer_than_ablation_cut": round(
                    sum(1 for x in lens if x > ABLATION_TRUNCATION) / len(lens), 4),
            }

    by_family: dict[str, dict] = {}
    for rec in per_archive.values():
        fam = rec["task"].replace("_test", "").replace("_dev", "")
        b = by_family.setdefault(fam, {"mean_chars": [], "cut_share": []})
        b["mean_chars"].append(rec["mean_chars"])
        b["cut_share"].append(rec["share_longer_than_ablation_cut"])
    families = {
        fam: {
            "mean_chars_min": min(v["mean_chars"]),
            "mean_chars_max": max(v["mean_chars"]),
            "share_longer_than_ablation_cut_min": min(v["cut_share"]),
            "share_longer_than_ablation_cut_max": max(v["cut_share"]),
        }
        for fam, v in sorted(by_family.items())
    }

    doc = {
        "punchmark_schema": "angle_a_lengths/v1",
        "ablation_truncation_chars": ABLATION_TRUNCATION,
        "per_archive": per_archive,
        "by_task_family": families,
        "what_this_settles": (
            "The 200-character ablation removes almost nothing on comprehend and most of "
            "the text on refactor, so the pooled ablated figure is roughly half canonical "
            "view and half a genuine truncation. A pooled ablation number cannot support "
            "a claim about formatting."),
        "what_this_does_not_settle": (
            "Length does not explain per-row separability ACROSS ROUTES: the comprehend "
            "archives span the widest separability range in the corpus at nearly "
            "identical lengths. Length is associated with the PROVIDER contrast in Study "
            "C, where the compared producers are near-identical, and not with the route "
            "contrast, where they are not. The two contrasts should not be pooled."),
    }

    for k, v in sorted(families.items()):
        print(f"{k:12s} mean chars {v['mean_chars_min']:7.1f} to {v['mean_chars_max']:7.1f}"
              f"   share above the {ABLATION_TRUNCATION}-char cut: "
              f"{v['share_longer_than_ablation_cut_min']:.3f} to "
              f"{v['share_longer_than_ablation_cut_max']:.3f}")
    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        write_text_deterministic(OUT, canonical_json(doc))
        print(f"\nwrote {OUT.relative_to(ROOT)}")
    else:
        print("\n(dry run; pass --write to record derived/lengths.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
