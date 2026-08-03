#!/usr/bin/env python3
"""The drift-gate tool: check or (deliberately) move the committed calibration goldens.

--check   regenerate the baseline from the committed model and byte-compare; also
          verify the corpus manifest self-hash. Exit 0 current / 1 drifted / 2 nothing
          committed yet (unevaluable, distinct from pass: PMK-GTE-002).
--write   rewrite goldens from the committed model. Refused unless --confirm-spec-bump
          is also given: a golden moves only together with a declared detector-version
          or spec-MAJOR change (PMK-GTE-003), and the flag is your written confirmation
          that one happened. A gutted goldens dir is refused rather than regenerated.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from punchmark.canonical import canonical_json, write_text_deterministic  # noqa: E402
from punchmark.corpus import read_manifest  # noqa: E402
from punchmark.gate import baseline_body  # noqa: E402
from punchmark.modelfile import read_model  # noqa: E402

CORPUS = ROOT / "calibration" / "spaghetti"
GOLDENS = CORPUS / "goldens"
MODEL = GOLDENS / "default.pmk-model.json"
BASELINE = GOLDENS / "operating_point.json"


def check() -> int:
    if not GOLDENS.exists():
        print("no committed calibration goldens yet; nothing to check (unevaluable)")
        return 2
    if not MODEL.exists() or not BASELINE.exists():
        print(
            "goldens directory exists but is incomplete; a gutted baseline is refused "
            "-- restore it from git, never regenerate it to make this pass",
            file=sys.stderr,
        )
        return 1
    doc = read_model(MODEL)
    regenerated = canonical_json(baseline_body(doc))
    committed = BASELINE.read_text(encoding="utf-8")
    if committed != regenerated:
        print(
            "operating_point.json does not regenerate from the committed model.\n"
            "If this move is deliberate (detector version or spec MAJOR changed), run\n"
            "  tools/update_calibration.py --write --confirm-spec-bump\n"
            "in the same commit as the change it declares. Otherwise revert.",
            file=sys.stderr,
        )
        return 1
    manifest = read_manifest(CORPUS)  # self-hash verified on read
    if doc.calibration_sha256 != manifest.corpus_sha256:
        print(
            f"model pins corpus {doc.calibration_sha256} but the committed manifest is "
            f"{manifest.corpus_sha256}; the model and the corpus moved apart",
            file=sys.stderr,
        )
        return 1
    print("calibration goldens are current")
    return 0


def write(confirmed: bool) -> int:
    if not confirmed:
        print(
            "refusing to move goldens without --confirm-spec-bump: an operating point "
            "moves only with a declared detector-version or spec-MAJOR change "
            "(PMK-GTE-003)",
            file=sys.stderr,
        )
        return 1
    if not MODEL.exists():
        print(f"no committed model at {MODEL}; commit the calibration first", file=sys.stderr)
        return 1
    doc = read_model(MODEL)
    write_text_deterministic(BASELINE, canonical_json(baseline_body(doc)))
    print(f"wrote {BASELINE}")
    return 0


def main() -> int:
    args = set(sys.argv[1:])
    if "--check" in args:
        return check()
    if "--write" in args:
        return write("--confirm-spec-bump" in args)
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
