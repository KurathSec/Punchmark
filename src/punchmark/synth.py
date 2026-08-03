"""Planted-truth synthetic archives: the known-answer harness.

Generates archives in the exact native shape -- ``<task>__<slug>.jsonl.gz`` plus a
``window/v1`` sidecar each -- for invented routes whose 'style' is planted by
construction: each route draws its completions from a vocabulary that mixes a
shared common pool with a route-specific pool at a declared ``separation`` rate.
At separation 0 the routes are byte-indistinguishable by design; at 1 they are
trivially separable. Every test that claims the pipeline can identify a producer
runs against this harness, where the truth is planted rather than assumed.

Determinism: every stream is seeded via ``canonical.derive_seed`` (PMK-EMIT-003);
identical arguments give byte-identical archives.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from .canonical import (
    canonical_json,
    derive_seed,
    sha256_file,
    write_gzip_deterministic,
    write_text_deterministic,
)
from .errors import SynthError

_PROFILES = ("minimal", "standard", "max")
_LANGUAGES = ("python", "go")
_COMMON = [
    "return", "value", "count", "total", "index", "buffer", "result", "state",
    "config", "input", "output", "status", "record", "field", "table", "queue",
]
_WINDOW = {"start_utc": "2026-01-01T00:00:00+00:00", "end_utc": "2026-01-01T01:00:00+00:00"}


@dataclass(frozen=True, slots=True)
class SynthSpec:
    routes: tuple[str, ...]
    tasks: tuple[str, ...]
    n_clusters: int
    k: int
    separation: float
    seed: int

    @property
    def items_per_archive(self) -> int:
        return self.n_clusters * len(_PROFILES) * len(_LANGUAGES)


def default_routes(n: int) -> tuple[str, ...]:
    if not 2 <= n <= 26:
        raise SynthError("synth supports 2..26 routes")
    return tuple(f"synth/route-{chr(ord('a') + i)}" for i in range(n))


def _route_vocab(route: str, seed: int) -> list[str]:
    rng = random.Random(derive_seed("synth-vocab", route, seed))
    return [
        "".join(rng.choice("abcdefghijklmnopqrstuvwxyz") for _ in range(rng.randint(4, 9)))
        for _ in range(24)
    ]


def _completion(rng: random.Random, own: list[str], separation: float) -> str:
    words: list[str] = []
    for _ in range(rng.randint(8, 20)):
        pool = own if rng.random() < separation else _COMMON
        words.append(rng.choice(pool))
    return " ".join(words)


def generate(out_dir: Path, spec: SynthSpec) -> list[Path]:
    """Write one archive + sidecar per (task, route); returns the archive paths."""
    if spec.n_clusters < 2:
        raise SynthError("need at least 2 clusters (calibration resamples by cluster)")
    if spec.k < 1:
        raise SynthError("k must be >= 1")
    if not 0.0 <= spec.separation <= 1.0:
        raise SynthError("separation must be in [0, 1]")
    if len(set(spec.routes)) != len(spec.routes) or len(spec.routes) < 2:
        raise SynthError("routes must be >= 2 distinct names")
    out_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for task in spec.tasks:
        for route in spec.routes:
            own = _route_vocab(route, spec.seed)
            lines: list[str] = []
            for c in range(spec.n_clusters):
                sample = f"s{c:03d}"
                for profile in _PROFILES:
                    for language in _LANGUAGES:
                        rng = random.Random(
                            derive_seed("synth-item", task, route, sample, profile,
                                        language, spec.seed)
                        )
                        base = _completion(rng, own, spec.separation)
                        draws = [base]
                        for _ in range(spec.k - 1):
                            # temperature-0-like degeneracy: most extra draws repeat
                            if rng.random() < 0.8:
                                draws.append(base)
                            else:
                                draws.append(_completion(rng, own, spec.separation))
                        row = {
                            "sample": sample,
                            "variant": "base",
                            "profile": profile,
                            "language": language,
                            "intrinsic": {"n_ops": 1 + c % 5},
                            "tier": "A",
                            "raw_outputs": draws,
                        }
                        lines.append(json.dumps(row, sort_keys=True))
            slug = route.replace("/", "-")
            archive_path = out_dir / f"{task}__{slug}.jsonl.gz"
            write_gzip_deterministic(archive_path, ("\n".join(lines) + "\n").encode("utf-8"))
            sidecar_body = {
                "punchmark_schema": "window/v1",
                "archive": archive_path.name,
                "archive_sha256": sha256_file(archive_path),
                "route": route,
                "task": task,
                "window": dict(_WINDOW),
                "collector": {"provider": "synthetic", "k": spec.k, "temperature": 0.0},
                "declared_by": "punchmark synth",
            }
            write_text_deterministic(
                archive_path.with_name(archive_path.name + ".window.json"),
                canonical_json(sidecar_body),
            )
            paths.append(archive_path)
    return paths
