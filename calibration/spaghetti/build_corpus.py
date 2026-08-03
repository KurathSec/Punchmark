#!/usr/bin/env python3
"""Build the reference calibration: MANIFEST, fitted default model, goldens.

Re-runnable by anyone holding the pinned upstream checkout; deterministic
byte-for-byte (PMK-EMIT-001). What it writes:

- ``MANIFEST.json`` -- mode ``manifest`` (PMK-COR-002: no completion text is
  re-published; the manifest pins the upstream commit and per-archive sha256, and
  its own content hash is the corpus identity every ruling cites, PMK-COR-001).
  All 16 archives are pinned; ``role: fit`` marks the 8 dev-split archives the
  calibration is computed from, ``role: heldout`` the 8 test-split archives the
  validation study scores. Thresholds never see a heldout row.
- ``goldens/default.pmk-model.json`` -- the chargram detector fitted on the 8
  fit-role archives, calibrated at the declared grids.
- ``goldens/operating_point.json`` -- the gate baseline derived from that model.
- ``../../src/punchmark/models/default.pmk.json`` -- the same model shipped as
  package data so a bare install can score with ``--model default``.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / "src"))

from punchmark.archive import read_archive  # noqa: E402
from punchmark.calibrate import CalibrationConfig, calibrate  # noqa: E402
from punchmark.canonical import canonical_json, sha256_file, write_text_deterministic  # noqa: E402
from punchmark.corpus import build_manifest, write_manifest  # noqa: E402
from punchmark.detector import build_detector  # noqa: E402
from punchmark.gate import baseline_body  # noqa: E402
from punchmark.model import CandidateSet  # noqa: E402
from punchmark.modelfile import build_doc, write_model  # noqa: E402
from punchmark.power import PowerConfig, power_analysis  # noqa: E402
from punchmark.sidecar import load_and_attach  # noqa: E402
from punchmark.spec import spec_version  # noqa: E402

ROUTES = (
    "deepseek-ai/DeepSeek-V4-Flash",
    "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "meta-llama/Meta-Llama-3.1-8B-Instruct",
    "mistralai/Mistral-Small-3.2-24B-Instruct-2506",
)
UPSTREAM_REPO = "https://github.com/KurathSec/Spaghetti-Architect"

# (relative dir under the checkout, task prefix, role)
GROUPS = [
    ("bench/out/ladder", "comprehend", "fit"),
    ("bench/out/g3", "refactor_dev", "fit"),
    ("bench/out/g3", "comprehend_test", "heldout"),
    ("bench/out/g3", "refactor_test", "heldout"),
]

SEED = 20260803
CAL_CONFIG = CalibrationConfig(
    far_grid=(0.001, 0.005, 0.01, 0.05, 0.1),
    m_grid=(25, 50, 100, 150, 300, 750),
    n_null=4000,
    seed=SEED,
    min_clusters=8,
)
POW_CONFIG = PowerConfig(n_splice=400, power_target=0.8, seed=SEED)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="/home/kureist/Spaghetti-Architect")
    args = parser.parse_args()
    source = Path(args.source)
    candidates = CandidateSet(routes=tuple(sorted(ROUTES)))
    slugs = {route: route.replace("/", "-") for route in ROUTES}

    commit = subprocess.run(
        ["git", "-C", str(source), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()

    sources = []
    fit_sets = []
    for rel_dir, task, role in GROUPS:
        for route in sorted(ROUTES):
            path = source / rel_dir / f"{task}__{slugs[route]}.jsonl.gz"
            if not path.exists():
                print(f"missing archive {path}", file=sys.stderr)
                return 1
            rs = read_archive(path, candidates)
            sources.append(
                {
                    "path": f"{rel_dir}/{path.name}",
                    "sha256": sha256_file(path),
                    "role": role,
                    "rows": len(rs.rows),
                    "stub_records_skipped": rs.n_stub_rows,
                }
            )
            if role == "fit":
                fit_sets.append(load_and_attach(rs, path, HERE / "sidecars"))

    manifest = build_manifest(
        mode="manifest",
        checkout={"repo": UPSTREAM_REPO, "commit": commit},
        sources=sources,
        files=[],
        note=(
            "Reference corpus for the four-route candidate set. Mode 'manifest' per "
            "PMK-COR-002: no completion text is re-published here; rebuild verifies a "
            "local checkout byte-for-byte. role=fit archives (public dev split) are the "
            "only inputs to the shipped calibration; role=heldout archives are reserved "
            "for the validation study and never touch a threshold."
        ),
    )
    write_manifest(HERE, manifest)
    print(f"manifest {manifest.corpus_sha256} ({len(sources)} sources, commit {commit[:12]})")

    detector = build_detector("chargram")
    print("cross-fitting and calibrating on the 8 fit-role archives ...")
    calibration = calibrate(detector, fit_sets, candidates, CAL_CONFIG)
    print(f"  {len(calibration.operating_points)} operating points")
    power = power_analysis(
        calibration.oof_scored, candidates, calibration.operating_points,
        CAL_CONFIG, POW_CONFIG,
    )
    print(f"  {len(power.curve)} curve points, {len(power.power_points)} power points")
    fitted = detector.fit(fit_sets, candidates, SEED)
    doc = build_doc(
        fitted=fitted,
        spec_version=spec_version(),
        calibration_sha256=manifest.corpus_sha256,
        calibration_meta={
            "far_grid": list(CAL_CONFIG.far_grid),
            "m_grid": list(CAL_CONFIG.m_grid),
            "n_null": CAL_CONFIG.n_null,
            "n_splice": POW_CONFIG.n_splice,
            "power_target": POW_CONFIG.power_target,
            "seed": SEED,
            "min_clusters": CAL_CONFIG.min_clusters,
        },
        operating_points=calibration.operating_points,
        curve=power.curve,
        power=power.power_points,
    )
    goldens = HERE / "goldens"
    write_model(goldens / "default.pmk-model.json", doc)
    write_text_deterministic(
        goldens / "operating_point.json", canonical_json(baseline_body(doc))
    )
    shipped = ROOT / "src" / "punchmark" / "models" / "default.pmk.json"
    shipped.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(goldens / "default.pmk-model.json", shipped)
    print(f"model {doc.model_id} -> goldens/ and src/punchmark/models/default.pmk.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
