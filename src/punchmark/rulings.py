"""The ruling store: append-only JSONL with content-hash line integrity.

A ruling is never edited into a new meaning -- it is superseded by a new ruling
that names its predecessor (PMK-RUL-003). ``verify`` re-hashes every line and
checks every ``supersedes`` target exists earlier in the file, so tampering and
retro-editing are detectable by anyone holding the file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .canonical import canonical_line, content_id, fmt_float
from .errors import RulingError
from .model import Ruling

DEFAULT_STORE = Path("punchmark-rulings.jsonl")


def ruling_body(r: Ruling) -> dict[str, Any]:
    """The canonical serialized form of a ruling; the id hashes this body."""
    return {
        "punchmark_schema": "ruling/v1",
        "ruling_id": r.ruling_id,
        "verdict": r.verdict.value,
        "route": r.route,
        "task": r.task,
        "scored_as": r.scored_as,
        "window": None if r.window is None else r.window.as_dict(),
        "archive_sha256": r.archive_sha256,
        "model_id": r.model_id,
        "detector": {"id": r.detector_id, "version": r.detector_version},
        "candidate_set_id": r.candidate_set_id,
        "candidates": list(r.candidates),
        "operating_point": {
            "far": fmt_float(r.far),
            "threshold": None if r.threshold is None else fmt_float(r.threshold),
        },
        "calibration_sha256": r.calibration_sha256,
        "spec_version": r.spec_version,
        "statistic": None if r.statistic is None else fmt_float(r.statistic),
        "per_candidate": {k: fmt_float(v) for k, v in sorted(r.per_candidate.items())},
        "n_items": r.n_items,
        "n_clusters": r.n_clusters,
        "n_stub_rows": r.n_stub_rows,
        "rho_target": fmt_float(r.rho_target),
        "rho_min": None if r.rho_min is None else fmt_float(r.rho_min),
        "reasons": list(r.reasons),
        "supersedes": r.supersedes,
        "does_not_show": list(r.does_not_show),
    }


def verify(path: Path) -> list[dict[str, Any]]:
    """Read and verify the whole store; returns the raw ruling bodies in order."""
    if not path.exists():
        return []
    bodies: list[dict[str, Any]] = []
    seen: set[str] = set()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RulingError(f"{path}: unreadable ({exc})") from exc
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            body = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RulingError(f"{path}:{lineno}: not JSON ({exc.msg})") from exc
        if not isinstance(body, dict) or body.get("punchmark_schema") != "ruling/v1":
            raise RulingError(f"{path}:{lineno}: not a ruling/v1 line")
        rid = body.get("ruling_id")
        expected = content_id(body, "ruling_id", "pmk-r")
        if rid != expected:
            raise RulingError(
                f"{path}:{lineno}: ruling_id {rid} does not match content ({expected}); "
                "the line was edited after it was appended -- rulings are superseded, "
                "never rewritten"
            )
        if rid in seen:
            raise RulingError(f"{path}:{lineno}: duplicate ruling_id {rid}")
        target = body.get("supersedes")
        if target is not None and target not in seen:
            raise RulingError(
                f"{path}:{lineno}: supersedes {target!r} which does not appear earlier "
                "in this store"
            )
        seen.add(str(rid))
        bodies.append(body)
    return bodies


def append(path: Path, ruling: Ruling) -> None:
    """Verify the existing store, then append one ruling."""
    existing = verify(path)
    if ruling.supersedes is not None and all(
        b["ruling_id"] != ruling.supersedes for b in existing
    ):
        raise RulingError(
            f"cannot append: supersedes target {ruling.supersedes!r} is not in the store"
        )
    if any(b["ruling_id"] == ruling.ruling_id for b in existing):
        raise RulingError(
            f"ruling {ruling.ruling_id} is already in the store (identical inputs "
            "reproduce identical ids; there is nothing new to record)"
        )
    body = ruling_body(ruling)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8", newline="") as f:
        f.write(canonical_line(body) + "\n")


def find(path: Path, ruling_id: str) -> dict[str, Any]:
    for body in verify(path):
        if body["ruling_id"] == ruling_id:
            return body
    raise RulingError(f"ruling {ruling_id!r} not found in {path}")
