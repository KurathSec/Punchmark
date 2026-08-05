"""Native archive reader: ``<task>__<route-slug>.jsonl.gz``.

The filename IS the producer label (PMK-ARC-001): the route slug was fixed by the
experimenter at collection time and is independent of any text the detector sees.
Nothing in this module ever derives identity from row content.

Tolerance rules, each a spec ruling:
- rows are one of two schemas -- with or without ``tier`` (the native corpus ships
  both; PMK-ARC-003) -- plus API error stubs carrying only
  ``{sample, profile, language}`` and no ``raw_outputs`` (PMK-ARC-002);
- ragged draw counts are tolerated and counted, never silently padded;
- anything else is a typed refusal naming the line, never a KeyError downstream.

The row type carries no logprob, header or timing fields, so the text-only input
restriction is enforced by construction (PMK-ARC-004).
"""

from __future__ import annotations

import gzip
import json
from collections import Counter
from pathlib import Path
from typing import Any

from .canonical import sha256_file
from .errors import ArchiveError
from .model import CandidateSet, ResponseRow, ResponseSet

_ROW_KEYS_FULL = {"sample", "variant", "profile", "language", "intrinsic", "tier", "raw_outputs"}
_ROW_KEYS_NO_TIER = _ROW_KEYS_FULL - {"tier"}
_STUB_KEYS = {"sample", "profile", "language"}


def parse_archive_name(path: Path) -> tuple[str, str]:
    """``<task>__<slug>.jsonl.gz`` -> (task, slug). Refuses any other shape."""
    name = path.name
    if not name.endswith(".jsonl.gz"):
        raise ArchiveError(
            f"{name}: expected a gzipped JSONL archive named <task>__<route-slug>.jsonl.gz"
        )
    stem = name[: -len(".jsonl.gz")]
    if "__" not in stem:
        raise ArchiveError(
            f"{name}: no '__' separator; the filename must carry the task and the route slug "
            "because the filename is the producer label"
        )
    task, slug = stem.split("__", 1)
    if not task or not slug:
        raise ArchiveError(f"{name}: empty task or route slug")
    return task, slug


def route_for_slug(slug: str, candidates: CandidateSet) -> str:
    """Resolve a filename slug back to its declared route via the candidate set's
    own slugs -- the only sanctioned direction (a slug alone cannot say which dash
    was a '/')."""
    by_slug = {s: r for r, s in candidates.slugs.items()}
    if slug not in by_slug:
        known = ", ".join(sorted(by_slug))
        raise ArchiveError(
            f"route slug {slug!r} is not in the candidate set (known slugs: {known}); "
            "add this route to the candidate set the model was fitted with, or score "
            "an archive whose slug is already in it"
        )
    return by_slug[slug]


def _parse_row(raw: dict[str, Any], lineno: int, name: str) -> ResponseRow:
    keys = set(raw)
    if keys == _STUB_KEYS:
        # An API error stub: the collection failed for this item and the collector
        # recorded only its identity. It occupies the item slot and carries zero
        # draws; it is counted, surfaced, and never featurized (PMK-ARC-002).
        return ResponseRow(
            sample=str(raw["sample"]),
            profile=str(raw["profile"]),
            language=str(raw["language"]),
            variant=None,
            tier=None,
            intrinsic=None,
            raw_outputs=(),
            is_stub=True,
        )
    if keys not in (_ROW_KEYS_FULL, _ROW_KEYS_NO_TIER):
        unexpected = keys - _ROW_KEYS_FULL
        missing = _ROW_KEYS_NO_TIER - keys
        raise ArchiveError(
            f"{name}:{lineno}: row keys {sorted(keys)} match neither row schema "
            f"(unexpected: {sorted(unexpected) or '-'}; missing: {sorted(missing) or '-'}) "
            "and are not an error stub; punchmark reads only the native archive shape"
        )
    outputs = raw["raw_outputs"]
    if not isinstance(outputs, list) or not outputs or not all(
        isinstance(o, str) for o in outputs
    ):
        raise ArchiveError(
            f"{name}:{lineno}: raw_outputs must be a non-empty list of strings"
        )
    intrinsic = raw["intrinsic"]
    if not isinstance(intrinsic, dict) or not all(
        isinstance(k, str) and isinstance(v, int) for k, v in intrinsic.items()
    ):
        raise ArchiveError(f"{name}:{lineno}: intrinsic must be a str->int object")
    return ResponseRow(
        sample=str(raw["sample"]),
        profile=str(raw["profile"]),
        language=str(raw["language"]),
        variant=str(raw["variant"]),
        tier=str(raw["tier"]) if "tier" in raw else None,
        intrinsic=dict(intrinsic),
        raw_outputs=tuple(outputs),
        is_stub=False,
    )


def read_archive(path: Path, candidates: CandidateSet | None = None) -> ResponseSet:
    """Read one archive into a ``ResponseSet`` (window attached later by the
    sidecar layer, never here). With ``candidates`` the slug resolves to its
    declared route; without, the slug itself stands as the route label."""
    task, slug = parse_archive_name(path)
    route = route_for_slug(slug, candidates) if candidates is not None else slug
    rows: list[ResponseRow] = []
    seen_keys: set[str] = set()
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                if not line.strip():
                    continue
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ArchiveError(f"{path.name}:{lineno}: not JSON ({exc.msg})") from exc
                if not isinstance(raw, dict):
                    raise ArchiveError(f"{path.name}:{lineno}: row is not an object")
                row = _parse_row(raw, lineno, path.name)
                if not row.is_stub and row.item_key in seen_keys:
                    raise ArchiveError(
                        f"{path.name}:{lineno}: duplicate item {row.item_key}; "
                        "item identity (sample, variant, profile, language) must be unique"
                    )
                if not row.is_stub:
                    seen_keys.add(row.item_key)
                rows.append(row)
    except EOFError as exc:
        raise ArchiveError(
            f"{path}: truncated gzip stream ({exc}); the archive is incomplete"
        ) from exc
    except UnicodeDecodeError as exc:
        raise ArchiveError(f"{path}: not UTF-8 text ({exc})") from exc
    except OSError as exc:
        raise ArchiveError(f"{path}: unreadable ({exc})") from exc
    if not rows:
        raise ArchiveError(f"{path.name}: empty archive")
    return ResponseSet(
        route=route,
        task=task,
        window=None,
        rows=tuple(rows),
        archive_sha256=sha256_file(path),
        source_name=path.name,
    )


def ragged_rows(rs: ResponseSet) -> int:
    """Rows whose draw count differs from the archive's modal k. Counted and
    surfaced (they are a serving event), never padded or dropped here."""
    counts = Counter(len(r.raw_outputs) for r in rs.valid_rows)
    if not counts:
        return 0
    modal_k = counts.most_common(1)[0][0]
    return sum(1 for r in rs.valid_rows if len(r.raw_outputs) != modal_k)


def modal_k(rs: ResponseSet) -> int:
    counts = Counter(len(r.raw_outputs) for r in rs.valid_rows)
    if not counts:
        return 0
    return counts.most_common(1)[0][0]
