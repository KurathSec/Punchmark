"""Mechanical gate 1: the committed calibration regenerates its committed goldens.

Armed once the calibration commit lands (limen precedent: skipif until then).
Moving a golden requires tools/update_calibration.py --write --confirm-spec-bump
after a real detector-version or spec-MAJOR change; this test is the in-repo
tooth and `punchmark gate` is the downstream one (PMK-GTE-003).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from punchmark.canonical import canonical_json
from punchmark.gate import baseline_body
from punchmark.modelfile import read_model
from punchmark.spec import spec_version

ROOT = Path(__file__).parent.parent
GOLDENS = ROOT / "calibration" / "spaghetti" / "goldens"

pytestmark = pytest.mark.skipif(
    not GOLDENS.exists(),
    reason="no committed calibration goldens yet (they land with the calibration commit)",
)


def test_committed_baseline_matches_committed_model_bytes() -> None:
    doc = read_model(GOLDENS / "default.pmk-model.json")
    committed = (GOLDENS / "operating_point.json").read_text(encoding="utf-8")
    regenerated = canonical_json(baseline_body(doc))
    assert committed == regenerated, (
        "committed operating_point.json does not regenerate from the committed "
        "model; run tools/update_calibration.py --check for the diff, and move "
        "goldens only with --write --confirm-spec-bump"
    )


def test_committed_goldens_carry_the_live_spec_major() -> None:
    baseline = json.loads((GOLDENS / "operating_point.json").read_text())
    assert baseline["spec_major"] == spec_version().split(".")[0], (
        "goldens were produced under a different spec MAJOR; regenerate them "
        "deliberately with the bump they claim"
    )
