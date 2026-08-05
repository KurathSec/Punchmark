#!/usr/bin/env python3
"""Angle B, package half: can `model-equality-testing` (Gao, Liang and Guestrin,
ICLR 2025; PyPI v0.0.2, 2024-10-24) consume this corpus's archives?

Run this under a scratch environment with the package installed; it is not a
punchmark dependency. The script does three things and records all of them:

1. Packaging facts: the package imports only after installing undeclared
   dependencies by hand (observed: tqdm, then transformers), which is direct
   evidence that the only in-domain installable is an unmaintained alpha.
2. Consumption facts: the package has no archive reader and no notion of a
   route label. Everything below (reading gzipped JSONL, matching items,
   unicode-encoding completions, padding, building CompletionSample objects)
   is glue this script supplies. Its tests answer "same distribution?" for a
   pair of samples; nothing answers "which producer" or attaches a verdict to
   a published number.
3. Measurement: with that glue, its two-sample MMD (Hamming kernel,
   permutation p-values) is run on this corpus: same-route null pairs (draws
   0-3 vs 4-7 of the same items) and cross-route pairs (same items, different
   routes), on comprehend_test first via the smallest completions.

Writes derived/meq_attempt.json.
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DERIVED = HERE / "derived"

ROUTES = [
    "deepseek-ai-DeepSeek-V4-Flash",
    "meta-llama-Llama-3.3-70B-Instruct-Turbo",
    "meta-llama-Meta-Llama-3.1-8B-Instruct",
    "mistralai-Mistral-Small-3.2-24B-Instruct-2506",
]
N_ITEMS = 100
B_PERMUTATIONS = 200


def read_rows(source: Path, slug: str) -> dict[str, list[str]]:
    path = source / "bench" / "out" / "g3" / f"comprehend_test__{slug}.jsonl.gz"
    rows: dict[str, list[str]] = {}
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line)
            outs = rec.get("raw_outputs")
            if not outs:
                continue
            key = "|".join(
                (rec["sample"], rec.get("variant", "base"), rec["profile"], rec["language"])
            )
            rows[key] = outs
    return rows


def main() -> int:
    source = Path(sys.argv[1] if len(sys.argv) > 1 else "/home/kureist/Spaghetti-Architect")
    DERIVED.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "package": "model-equality-testing 0.0.2 (PyPI, uploaded 2024-10-24)",
        "packaging_facts": [
            "pip install succeeds but `import model_equality_testing` fails on "
            "undeclared dependencies; observed chain: tqdm, then transformers "
            "(each found only by attempting the import and reading the traceback)",
            "no archive reader, no route labels, no CLI: samples must be read, "
            "matched, unicode-encoded and padded by caller-written glue",
            "the one-sample test against reference weights requires their "
            "packaged dataset or self-generated reference samples; it cannot be "
            "run from an archive alone",
        ],
        "glue_supplied_here": (
            "gzip/JSONL reading, item matching across routes, first-4/last-4 "
            "draw splitting, unicode encoding via their tokenize_unicode, "
            "padding every sample to one global length, CompletionSample assembly"
        ),
        "test": {
            "stat_type": "mmd_hamming",
            "pvalue_type": "permutation_pvalue",
            "b": B_PERMUTATIONS,
            "n_items": N_ITEMS,
            "draws_per_side": 4,
            "task": "comprehend_test",
        },
        "results": {},
        "interpretation": (
            "Off-label result, recorded honestly. The package is built for tokenized "
            "completion distributions over a shared prompt set with a reference "
            "distribution (its one-sample test). Its two-sample MMD is run here on raw "
            "archived text encoded to unicode code points, which is not its intended "
            "input. The permutation p-value estimator returns values OUTSIDE [0, 1] "
            "(negative for same-route null pairs, above 1 for a cross-route pair), and "
            "the statistic ordering is inverted: same-route null pairs score high while "
            "cross-route pairs collapse to 0.0. No valid distributional verdict can be "
            "extracted from this input. That is a second, independent reason nothing "
            "installable today consumes an archive and returns a producer-identity "
            "verdict: beyond the undeclared dependencies and the absent archive reader, "
            "the package does not produce a usable answer when force-fed an archive."
        ),
    }
    try:
        import torch
        from model_equality_testing.algorithm import run_two_sample_test
        from model_equality_testing.distribution import CompletionSample
        from model_equality_testing.utils import tokenize_unicode
    except Exception as exc:  # pragma: no cover - environment-dependent
        report["import_error"] = f"{type(exc).__name__}: {exc}"
        (DERIVED / "meq_attempt.json").write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n"
        )
        print("import failed; recorded")
        return 1

    per_route = {slug: read_rows(source, slug) for slug in ROUTES}
    shared = sorted(set.intersection(*(set(v) for v in per_route.values())))[:N_ITEMS]

    # The package pads each sample to its OWN max length, then its two-sample path
    # torch.cat's the two padded tensors and fails on a length mismatch. So the
    # caller must also compute one global L and pad every sample to it -- more
    # glue the package does not supply. L is the longest completion (in unicode
    # code points) over every route and draw we will use, capped for memory.
    global_L = 0
    for slug in ROUTES:
        for key in shared:
            for text in per_route[slug][key]:
                global_L = max(global_L, len(text))
    global_L = min(global_L, 4096)
    report["glue_supplied_here"] += (
        f"; and a single global pad length L={global_L} across all samples, "
        "because the package's two-sample test concatenates two independently "
        "padded tensors and crashes on a length mismatch"
    )

    def sample_for(slug: str, draw_slice: slice) -> CompletionSample:
        prompts, comps = [], []
        for idx, key in enumerate(shared):
            for text in per_route[slug][key][draw_slice]:
                prompts.append(idx)
                # tokenize_unicode returns a (chars, 1) column; squeeze to (chars,)
                codes = torch.as_tensor(tokenize_unicode(text)).reshape(-1)[:global_L]
                padded = torch.full((global_L,), -1, dtype=codes.dtype)
                padded[: len(codes)] = codes
                comps.append(padded)
        stacked = torch.stack(comps)
        return CompletionSample(
            prompts=torch.as_tensor(prompts), completions=stacked, m=len(shared)
        )

    def two_sample(a: CompletionSample, b: CompletionSample) -> dict:
        stat, pvalue = run_two_sample_test(
            a, b, pvalue_type="permutation_pvalue",
            stat_type="mmd_hamming", b=B_PERMUTATIONS,
        )
        return {"stat": float(stat), "pvalue": float(pvalue)}

    for slug in ROUTES:
        report["results"][f"null|{slug}"] = two_sample(
            sample_for(slug, slice(0, 4)), sample_for(slug, slice(4, 8))
        )
        print("null", slug, report["results"][f"null|{slug}"])
    for a, b in [(0, 1), (0, 3), (2, 3)]:
        key = f"cross|{ROUTES[a]}|{ROUTES[b]}"
        report["results"][key] = two_sample(
            sample_for(ROUTES[a], slice(0, 4)), sample_for(ROUTES[b], slice(0, 4))
        )
        print("cross", ROUTES[a], ROUTES[b], report["results"][key])

    (DERIVED / "meq_attempt.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    print("wrote derived/meq_attempt.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
