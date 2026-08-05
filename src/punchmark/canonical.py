"""Canonical serialization: the byte-stability contract.

Every committed artifact (fitted-model file, ruling line, certificate, manifest,
golden) is produced through this module, and regeneration must be byte-identical
(spec ruling PMK-EMIT-001). The rules:

- floats pass ``fmt_float`` (round half-even to 6 places, ``-0.0`` normalized);
  NaN and infinities raise -- upstream code must have turned them into
  null-with-reason before serialization;
- ``json.dumps(sort_keys=True, indent=2, ensure_ascii=True)`` plus a trailing newline;
- gzip written with ``mtime=0`` and no embedded filename;
- content ids are sha256 over the canonical bytes with the id field removed, so a
  document can carry its own address (PMK-EMIT-002);
- every seed is derived from labelled parts, never from the clock (PMK-EMIT-003).
"""

from __future__ import annotations

import gzip
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .errors import SerializationError


def fmt_float(x: float) -> float:
    """Normalize a float for serialization: round half-even to 6 places, kill -0.0."""
    if math.isnan(x) or math.isinf(x):
        raise SerializationError(
            f"non-finite float {x!r} reached serialization; the caller must record it as "
            "null with a reason instead of a number"
        )
    return round(x, 6) + 0.0


def canonical_json(body: Any) -> str:
    """The canonical text form: sorted keys, 2-space indent, ASCII, trailing newline."""
    return json.dumps(body, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def canonical_line(body: Any) -> str:
    """The canonical single-line form used for JSONL stores: sorted keys, no indent."""
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def content_id(body: dict[str, Any], id_field: str, prefix: str) -> str:
    """Content address of a document: ``<prefix>-<sha256/16>`` over the canonical
    single-line bytes with ``id_field`` removed (PMK-EMIT-002)."""
    stripped = {k: v for k, v in body.items() if k != id_field}
    digest = hashlib.sha256(canonical_line(stripped).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:16]}"


def sha256_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"


def derive_seed(*parts: str | int) -> int:
    """Deterministic seed from labelled parts (PMK-EMIT-003).

    No stochastic procedure in punchmark may seed itself from the clock; every seed
    derives from labelled parts (the procedure name, the scope it runs in, an index,
    and the caller's seed) hashed with sha256.
    """
    text = "|".join(str(p) for p in parts)
    return int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8], "big")


def write_text_deterministic(path: Path, text: str) -> None:
    """Write UTF-8 text with LF endings exactly as given."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def write_gzip_deterministic(path: Path, data: bytes) -> None:
    """Write a gzip member with mtime=0 and no embedded filename, so identical data
    gives identical bytes regardless of where or when it is written.

    Scope of the guarantee: bytes are stable per zlib build. A different zlib
    (e.g. zlib-ng) may compress identical data differently, which is why byte-compared
    artifacts are the JSON documents, while committed .gz files are pinned by hash in
    a manifest and never regenerated in CI.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as raw:
        with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as gz:
            gz.write(data)
