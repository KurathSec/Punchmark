"""Caller-written window metadata: ``<archive-filename>.window.json``.

The collection window is by-construction metadata the CALLER declares; punchmark
never infers time from content (PMK-SDC-001). The sidecar must agree with the
archive it describes: the route must slug-match the filename (the filename is the
oracle; disagreement is a refusal, PMK-SDC-002) and the archive hash must match
the bytes (PMK-SDC-003), so a sidecar cannot be quietly re-pointed at different
data.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .canonical import canonical_json
from .errors import SidecarError
from .model import ResponseSet, Window

SCHEMA = "window/v1"


@dataclass(frozen=True, slots=True)
class Sidecar:
    archive: str
    archive_sha256: str
    route: str
    task: str
    window: Window
    collector: dict[str, Any]


def default_sidecar_path(archive_path: Path) -> Path:
    return archive_path.with_name(archive_path.name + ".window.json")


def _parse_utc(label: str, value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SidecarError(f"window.{label} {value!r} is not ISO-8601") from exc
    if parsed.tzinfo is None:
        raise SidecarError(f"window.{label} {value!r} carries no timezone; declare UTC explicitly")
    return value


def example_sidecar(rs: ResponseSet, route: str) -> str:
    """The exact JSON a refusing error message tells the caller to write."""
    body = {
        "punchmark_schema": SCHEMA,
        "archive": rs.source_name,
        "archive_sha256": rs.archive_sha256,
        "route": route,
        "task": rs.task,
        "window": {
            "start_utc": "2026-01-01T00:00:00+00:00",
            "end_utc": "2026-01-01T00:00:00+00:00",
        },
        "collector": {},
        "declared_by": "caller",
    }
    return canonical_json(body)


def load_sidecar(path: Path) -> Sidecar:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SidecarError(f"{path}: unreadable ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise SidecarError(f"{path}: not JSON ({exc.msg})") from exc
    if not isinstance(raw, dict) or raw.get("punchmark_schema") != SCHEMA:
        raise SidecarError(
            f"{path}: not a {SCHEMA} sidecar; regenerate it (punchmark prints the exact "
            "shape when a sidecar is missing)"
        )
    for key in ("archive", "archive_sha256", "route", "task", "window"):
        if key not in raw:
            raise SidecarError(f"{path}: missing required field {key!r}")
    window = raw["window"]
    if not isinstance(window, dict) or set(window) != {"start_utc", "end_utc"}:
        raise SidecarError(f"{path}: window must be exactly {{start_utc, end_utc}}")
    start = _parse_utc("start_utc", str(window["start_utc"]))
    end = _parse_utc("end_utc", str(window["end_utc"]))
    if datetime.fromisoformat(end) < datetime.fromisoformat(start):
        raise SidecarError(f"{path}: window ends before it starts")
    collector = raw.get("collector", {})
    if not isinstance(collector, dict):
        raise SidecarError(f"{path}: collector must be an object")
    return Sidecar(
        archive=str(raw["archive"]),
        archive_sha256=str(raw["archive_sha256"]),
        route=str(raw["route"]),
        task=str(raw["task"]),
        window=Window(start_utc=start, end_utc=end),
        collector=collector,
    )


def attach(rs: ResponseSet, sc: Sidecar) -> ResponseSet:
    """Validate the sidecar against the archive and return the windowed set.

    The route check runs on slugs: the sidecar declares the full route name
    (with '/'), the filename carries its slugged form. The sidecar may therefore
    RESOLVE a slug to a route, but never contradict it.
    """
    if sc.archive != rs.source_name:
        raise SidecarError(
            f"sidecar names archive {sc.archive!r} but was applied to {rs.source_name!r}"
        )
    if sc.archive_sha256 != rs.archive_sha256:
        raise SidecarError(
            f"sidecar pins archive_sha256 {sc.archive_sha256} but the bytes on disk hash to "
            f"{rs.archive_sha256}; the sidecar does not describe this archive"
        )
    if sc.task != rs.task:
        raise SidecarError(
            f"sidecar declares task {sc.task!r} but the filename carries {rs.task!r}; "
            "the filename is the oracle and the sidecar must agree with it"
        )
    slug_of_declared = sc.route.replace("/", "-")
    # rs.route is either the resolved route (candidates supplied) or the raw slug.
    if rs.route not in (sc.route, slug_of_declared) and rs.route.replace("/", "-") != slug_of_declared:
        raise SidecarError(
            f"sidecar declares route {sc.route!r} whose slug {slug_of_declared!r} does not "
            f"match the archive's label {rs.route!r}; the filename is the oracle"
        )
    return ResponseSet(
        route=sc.route,
        task=rs.task,
        window=sc.window,
        rows=rs.rows,
        archive_sha256=rs.archive_sha256,
        source_name=rs.source_name,
    )


def load_and_attach(
    rs: ResponseSet, archive_path: Path, sidecar_dir: Path | None = None
) -> ResponseSet:
    """Attach the sidecar for an archive path, refusing with the exact JSON to
    write when it is absent.

    Lookup order: ``<sidecar_dir>/<archive-name>.window.json`` first (so sidecars
    for archives in a read-only checkout can live elsewhere, e.g. committed beside
    the calibration manifest), then beside the archive itself.
    """
    candidates = []
    if sidecar_dir is not None:
        candidates.append(sidecar_dir / (archive_path.name + ".window.json"))
    candidates.append(default_sidecar_path(archive_path))
    for path in candidates:
        if path.exists():
            return attach(rs, load_sidecar(path))
    looked = " or ".join(str(p) for p in candidates)
    raise SidecarError(
        f"no window sidecar at {looked}; the collection window is caller-declared "
        "by-construction metadata and is never inferred from content. Write this "
        f"file (with the real window):\n{example_sidecar(rs, rs.route)}"
    )
