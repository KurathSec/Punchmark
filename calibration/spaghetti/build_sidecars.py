#!/usr/bin/env python3
"""Derive the committed window sidecars for the 16 reference archives.

The upstream checkout's per-run records (``bench/out/subagent/*.json``, gitignored
upstream and local-only) carry ``env.timestamp_utc`` for each (task, route, split)
run. This script brackets them into per-collection windows and writes one
``window/v1`` sidecar per archive into ``sidecars/`` -- which is then the durable,
committed record; the script exists so the derivation is inspectable and re-runnable
by anyone holding the same local records.

Derivation, declared in every sidecar it writes:
- a group window is [min, max] over the four routes' run timestamps of that
  (task, split) collection;
- ``env.timestamp_utc`` is a run-COMPLETION time, so collection began somewhat
  before the bracket's start;
- two dev-comprehend runs have no finalize record and contribute their partial
  checkpoint's file mtime instead (marked in ``derived_from``).

Sidecars bind to archive bytes (PMK-SDC-003), so this script re-hashes the
archives from the checkout; it never writes into the checkout (PMK-SDC-001 --
the window is declared HERE, beside the manifest, not inferred at read time).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from punchmark.canonical import canonical_json, sha256_file, write_text_deterministic  # noqa: E402

ROUTES = {
    "deepseek-ai-DeepSeek-V4-Flash": "deepseek-ai/DeepSeek-V4-Flash",
    "meta-llama-Llama-3.3-70B-Instruct-Turbo": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "meta-llama-Meta-Llama-3.1-8B-Instruct": "meta-llama/Meta-Llama-3.1-8B-Instruct",
    "mistralai-Mistral-Small-3.2-24B-Instruct-2506": "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
}

# (archive dir, archive task prefix, finalize pattern, partial-checkpoint pattern)
GROUPS = [
    ("ladder", "comprehend", "comprehend__{slug}.json", "comprehend__{slug}.partial.jsonl"),
    ("g3", "comprehend_test", "comprehend__{slug}__test.json", None),
    ("g3", "refactor_dev", "refactor__{slug}.json", None),
    ("g3", "refactor_test", "refactor__{slug}__test.json", None),
]

DERIVATION = (
    "group window = [min, max] over the four routes' run timestamps for this "
    "(task, split) collection; env.timestamp_utc is a run-completion time, so "
    "collection began somewhat before the bracket start; entries marked "
    "partial-mtime contribute their checkpoint file's mtime because no finalize "
    "record exists"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        default="/home/kureist/Spaghetti-Architect",
        help="local checkout holding bench/out/{g3,ladder} and bench/out/subagent",
    )
    args = parser.parse_args()
    source = Path(args.source)
    subagent = source / "bench" / "out" / "subagent"
    out_dir = Path(__file__).parent / "sidecars"
    if not subagent.exists():
        print(
            f"{subagent} not found: the per-run records are local-only collection "
            "artifacts. The committed sidecars in sidecars/ remain the durable record.",
            file=sys.stderr,
        )
        return 1

    written = 0
    for archive_dir, task, finalize_pat, partial_pat in GROUPS:
        stamps: list[str] = []
        derived_from: list[dict[str, str]] = []
        for slug in ROUTES:
            finalize = subagent / finalize_pat.format(slug=slug)
            if finalize.exists():
                record = json.load(open(finalize, encoding="utf-8"))
                stamp = str(record["env"]["timestamp_utc"])
                stamps.append(stamp)
                derived_from.append(
                    {"file": finalize.name, "kind": "finalize env.timestamp_utc", "utc": stamp}
                )
                continue
            partial = subagent / partial_pat.format(slug=slug) if partial_pat else None
            if partial is not None and partial.exists():
                stamp = datetime.fromtimestamp(partial.stat().st_mtime, UTC).isoformat()
                stamps.append(stamp)
                derived_from.append(
                    {"file": partial.name, "kind": "partial-mtime", "utc": stamp}
                )
                continue
            print(f"no run record for ({task}, {slug}); refusing", file=sys.stderr)
            return 1
        window = {"start_utc": min(stamps), "end_utc": max(stamps)}

        for slug, route in ROUTES.items():
            archive = source / "bench" / "out" / archive_dir / f"{task}__{slug}.jsonl.gz"
            if not archive.exists():
                print(f"missing archive {archive}", file=sys.stderr)
                return 1
            body = {
                "punchmark_schema": "window/v1",
                "archive": archive.name,
                "archive_sha256": sha256_file(archive),
                "route": route,
                "task": task,
                "window": window,
                "collector": {
                    "provider": "DeepInfra (one OpenAI-compatible endpoint for all four routes)",
                    "k": 8,
                    "temperature": 0.0,
                    "max_tokens": 2048,
                    "window_derivation": DERIVATION,
                    "derived_from": derived_from,
                },
                "declared_by": "calibration/spaghetti/build_sidecars.py",
            }
            write_text_deterministic(
                out_dir / f"{archive.name}.window.json", canonical_json(body)
            )
            written += 1
    print(f"wrote {written} sidecars to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
