#!/usr/bin/env python3
"""Derive the Angle C collection-quality summary from what was actually collected.

Reads only files this directory already owns: the six archives, their window/v1
sidecars, and the per-item response logs. Issues no requests and costs nothing, so it
can be re-run at any time and must reproduce the same numbers from the same archives.

Every collection-quality number quoted in FINDING.md comes from here rather than from a
transcript, because a number that cannot be recomputed cannot be checked.

What it records per archive: row and draw counts, empty and truncated draw counts, the
model string the provider returned, whether any text arrived on a reasoning channel, the
temperature-0 degeneracy profile, the realized fan-out width against June's, the count of
rate-limited retries, and the archive's sha256. It also loads every archive through
punchmark's own reader, so a file that this project could not consume is caught here
rather than at scoring time.

Usage:  .venv/bin/python validation/angle_c/summarize.py [--write]
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from punchmark.archive import read_archive  # noqa: E402
from punchmark.canonical import canonical_json, sha256_file, write_text_deterministic  # noqa: E402

ARCHIVES = HERE / "archives"
OUT = HERE / "derived" / "collection_summary.json"


def summarize_archive(path: Path) -> dict:
    provider = path.parent.name
    sidecar_path = path.with_suffix(path.suffix + ".window.json")
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    collector = sidecar["collector"]

    rows = 0
    k_counts: Counter[int] = Counter()
    distinct_per_row: Counter[int] = Counter()
    empty_draws = 0
    total_chars = 0
    total_draws = 0
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rec = json.loads(line)
            outs = rec["raw_outputs"]
            rows += 1
            k_counts[len(outs)] += 1
            distinct_per_row[len(set(outs))] += 1
            empty_draws += sum(1 for d in outs if not d.strip())
            total_chars += sum(len(d) for d in outs)
            total_draws += len(outs)

    log_path = path.parent / (path.name.replace(".jsonl.gz", "") + ".responses.jsonl")
    finish: Counter[str] = Counter()
    returned: Counter[str] = Counter()
    reasoning_only = 0
    prompt_tokens = completion_tokens = cached_tokens = 0
    truncated_items: list[str] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        for i, d in enumerate(rec["draws"]):
            fr = str(d.get("finish_reason"))
            finish[fr] += 1
            returned[str(d.get("returned_model"))] += 1
            reasoning_only += 1 if d.get("from_reasoning_channel") else 0
            if fr != "stop":
                truncated_items.append(f"{rec['item']} draw {i} ({fr})")
            u = d.get("usage") or {}
            prompt_tokens += int(u.get("prompt_tokens") or 0)
            completion_tokens += int(u.get("completion_tokens") or 0)
            cached_tokens += int(u.get("cached_tokens") or 0)

    # Consumable by this project's own reader, not merely well-formed JSON.
    response_set = read_archive(path)
    reader_rows = len(response_set.rows)
    reader_stubs = sum(1 for r in response_set.rows if r.is_stub)

    return {
        "archive": f"{provider}/{path.name}",
        "sha256": sha256_file(path),
        "provider": provider,
        "route": sidecar["route"],
        "task": sidecar["task"],
        "window": sidecar["window"],
        "rows": rows,
        "draws": total_draws,
        "k_distribution": {str(k): v for k, v in sorted(k_counts.items())},
        "empty_draws": empty_draws,
        "mean_chars_per_draw": round(total_chars / total_draws, 1) if total_draws else 0.0,
        # Temperature 0 does not make draws identical on hosted routes; how far it
        # falls short is the archive's real evidence weight, so it is recorded rather
        # than assumed to be k.
        "distinct_draws_per_row": {str(k): v for k, v in sorted(distinct_per_row.items())},
        "fully_degenerate_rows": distinct_per_row.get(1, 0),
        "finish_reason": dict(finish),
        "truncated_draws": len(truncated_items),
        "truncated_detail": truncated_items,
        "returned_model": dict(returned),
        "returned_model_matches_request": list(returned) == [sidecar["route"]],
        "reasoning_channel_draws": reasoning_only,
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "cached_prompt_tokens": cached_tokens,
        },
        "net_concurrency": collector["net_concurrency"],
        "net_concurrency_requested": collector.get("net_concurrency_requested"),
        "june_net_concurrency": collector["june_net_concurrency"],
        "http_429": collector["http_429"],
        "punchmark_reader": {"rows": reader_rows, "stub_rows": reader_stubs},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="write derived/collection_summary.json")
    args = ap.parse_args()

    paths = sorted(ARCHIVES.glob("*/*.jsonl.gz"))
    if not paths:
        print(f"no archives under {ARCHIVES}", file=sys.stderr)
        return 2
    per_archive = [summarize_archive(p) for p in paths]

    totals = {
        "archives": len(per_archive),
        "rows": sum(a["rows"] for a in per_archive),
        "draws": sum(a["draws"] for a in per_archive),
        "empty_draws": sum(a["empty_draws"] for a in per_archive),
        "truncated_draws": sum(a["truncated_draws"] for a in per_archive),
        "reasoning_channel_draws": sum(a["reasoning_channel_draws"] for a in per_archive),
        "http_429": sum(a["http_429"] for a in per_archive),
        "prompt_tokens": sum(a["usage"]["prompt_tokens"] for a in per_archive),
        "completion_tokens": sum(a["usage"]["completion_tokens"] for a in per_archive),
    }
    widths = {a["net_concurrency"] for a in per_archive}
    totals["single_declared_width"] = sorted(widths)[0] if len(widths) == 1 else None
    totals["all_returned_models_match_request"] = all(
        a["returned_model_matches_request"] for a in per_archive
    )

    doc = {
        "punchmark_schema": "angle_c_collection_summary/v1",
        "note": (
            "Collection quality only. Nothing here is a verdict, a detector score, or a "
            "comparison between routes; it describes how the archives were obtained."
        ),
        "totals": totals,
        "archives": per_archive,
    }

    for a in per_archive:
        print(f"{a['provider']+'/'+a['task']:28s} {a['route'].split('/')[-1][:34]:34s} "
              f"rows={a['rows']:3d} width={a['net_concurrency']:3d} "
              f"429={a['http_429']:3d} trunc={a['truncated_draws']} "
              f"empty={a['empty_draws']} degen={a['fully_degenerate_rows']:2d}/{a['rows']}")
    print()
    print(f"single declared width across all archives: {totals['single_declared_width']}")
    print(f"returned model matched request everywhere: "
          f"{totals['all_returned_models_match_request']}")
    print(f"{totals['draws']} draws, {totals['empty_draws']} empty, "
          f"{totals['truncated_draws']} truncated, {totals['http_429']} rate-limited retries")

    if args.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        write_text_deterministic(OUT, canonical_json(doc))
        print(f"\nwrote {OUT.relative_to(ROOT)}")
    else:
        print("\n(dry run; pass --write to record derived/collection_summary.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
