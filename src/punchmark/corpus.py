"""The calibration corpus: identified by its MANIFEST, not by shipped bytes.

The shipped mode is manifest + local rebuild (PMK-COR-002): the manifest pins the
upstream checkout commit and the sha256 of every source archive, and
``punchmark corpus rebuild --corpus <dir> --source <checkout>`` verifies the local
bytes against those pins. No completion text rides in this repository: the corpus
identity every ruling cites (PMK-COR-001) is the content hash of the manifest
itself, and that hash is exactly as binding over a manifest as over a copy.

``raw`` and ``features`` modes exist in code and are exercised synthetically so
the machinery is proven, but the shipped manifest for the reference corpus uses
neither (the second-disclosure decision recorded in PMK-COR-002).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .canonical import canonical_json, content_id, sha256_file, write_text_deterministic
from .errors import CorpusError

SCHEMA = "corpus/v1"
MANIFEST_NAME = "MANIFEST.json"
MODES = ("manifest", "raw", "features")


@dataclass(frozen=True)
class Manifest:
    manifest_id: str
    mode: str
    checkout: dict[str, str]
    sources: tuple[dict[str, Any], ...]
    files: tuple[dict[str, str], ...]
    note: str

    @property
    def corpus_sha256(self) -> str:
        """The calibration identity rulings pin (PMK-COR-001)."""
        return self.manifest_id


def _body(m: Manifest) -> dict[str, Any]:
    return {
        "punchmark_schema": SCHEMA,
        "manifest_id": m.manifest_id,
        "mode": m.mode,
        "checkout": dict(m.checkout),
        "sources": [dict(s) for s in m.sources],
        "files": [dict(f) for f in m.files],
        "note": m.note,
    }


def build_manifest(
    mode: str,
    checkout: dict[str, str],
    sources: list[dict[str, Any]],
    files: list[dict[str, str]],
    note: str,
) -> Manifest:
    if mode not in MODES:
        raise CorpusError(f"unknown corpus mode {mode!r}; modes: {list(MODES)}")
    if not sources:
        raise CorpusError("a corpus manifest with no sources identifies nothing")
    if mode == "manifest" and files:
        raise CorpusError("manifest mode ships no files; the files list must be empty")
    draft = Manifest(
        manifest_id="",
        mode=mode,
        checkout=checkout,
        sources=tuple(sources),
        files=tuple(files),
        note=note,
    )
    manifest_id = content_id(_body(draft), "manifest_id", "pmk-cor")
    return Manifest(
        manifest_id=manifest_id,
        mode=mode,
        checkout=checkout,
        sources=tuple(sources),
        files=tuple(files),
        note=note,
    )


def write_manifest(corpus_dir: Path, manifest: Manifest) -> None:
    write_text_deterministic(corpus_dir / MANIFEST_NAME, canonical_json(_body(manifest)))


def read_manifest(corpus_dir: Path) -> Manifest:
    path = corpus_dir / MANIFEST_NAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CorpusError(f"{path}: unreadable ({exc})") from exc
    except json.JSONDecodeError as exc:
        raise CorpusError(f"{path}: not JSON ({exc.msg})") from exc
    if not isinstance(raw, dict) or raw.get("punchmark_schema") != SCHEMA:
        raise CorpusError(f"{path}: not a {SCHEMA} manifest")
    manifest = Manifest(
        manifest_id=str(raw.get("manifest_id", "")),
        mode=str(raw.get("mode", "")),
        checkout=dict(raw.get("checkout", {})),
        sources=tuple(raw.get("sources", [])),
        files=tuple(raw.get("files", [])),
        note=str(raw.get("note", "")),
    )
    if manifest.mode not in MODES:
        raise CorpusError(f"{path}: unknown mode {manifest.mode!r}")
    expected = content_id(_body(manifest), "manifest_id", "pmk-cor")
    if manifest.manifest_id != expected:
        raise CorpusError(
            f"{path}: manifest_id {manifest.manifest_id} does not match content "
            f"({expected}); the manifest was edited after it was written"
        )
    return manifest


def verify_shipped(corpus_dir: Path, manifest: Manifest) -> list[str]:
    """Verify every shipped file (raw/features modes) against its pinned hash."""
    lines: list[str] = [f"corpus {manifest.corpus_sha256} mode={manifest.mode}"]
    for entry in manifest.files:
        path = corpus_dir / entry["path"]
        if not path.exists():
            raise CorpusError(f"shipped file missing: {entry['path']}")
        actual = sha256_file(path)
        if actual != entry["sha256"]:
            raise CorpusError(
                f"{entry['path']}: sha256 {actual} != pinned {entry['sha256']}"
            )
        lines.append(f"ok shipped {entry['path']}")
    if manifest.mode == "manifest":
        lines.append(f"nothing shipped by design; {len(manifest.sources)} sources pinned")
    return lines


def verify_sources(manifest: Manifest, source_root: Path) -> list[str]:
    """The rebuild: verify the local checkout's bytes against the pinned hashes.
    This IS the manifest-mode rebuild -- when every pinned source matches, the
    local corpus is bit-for-bit the one the shipped calibration was fitted on."""
    if not source_root.exists():
        raise CorpusError(
            f"source checkout {source_root} does not exist; clone "
            f"{manifest.checkout.get('repo', '<the pinned repo>')} at commit "
            f"{manifest.checkout.get('commit', '<pinned>')} and point --source at it"
        )
    lines: list[str] = []
    for entry in manifest.sources:
        path = source_root / entry["path"]
        if not path.exists():
            raise CorpusError(
                f"source archive missing from checkout: {entry['path']} "
                f"(expected under {source_root})"
            )
        actual = sha256_file(path)
        if actual != entry["sha256"]:
            raise CorpusError(
                f"{entry['path']}: sha256 {actual} != pinned {entry['sha256']}; "
                "this checkout does not contain the calibration bytes (wrong commit?)"
            )
        lines.append(f"ok source {entry['path']}")
    lines.append(f"rebuild verified: {len(manifest.sources)} source archives match their pins")
    return lines
