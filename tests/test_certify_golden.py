"""Certificate text and JSON are golden-pinned (PMK-CRT-001/002/003).

The goldens live in tests/goldens/ and are byte-compared: certificate wording is
contract, and the no-weights sentence cannot drift out of it unnoticed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from punchmark.certify import certificate_from_ruling, certificate_json, exit_code_for
from punchmark.errors import CertificateError
from punchmark.model import Verdict
from punchmark.rulings import ruling_body
from tests.test_rulings_store import make_ruling

GOLDENS = Path(__file__).parent / "goldens"

NO_WEIGHTS = (
    "This certifies the route label as served within the named candidate set; "
    "it is not a statement about model weights."
)


def test_holds_certificate_matches_golden_bytes() -> None:
    cert = certificate_from_ruling(ruling_body(make_ruling()))
    assert cert.line == (GOLDENS / "certificate_holds.txt").read_text().rstrip("\n")
    assert certificate_json(cert) == (GOLDENS / "certificate_holds.json").read_text()


def test_substituted_certificate_matches_golden_bytes() -> None:
    ruling = make_ruling(verdict=Verdict.SUBSTITUTED, statistic=-0.9)
    cert = certificate_from_ruling(ruling_body(ruling))
    assert cert.line == (
        (GOLDENS / "certificate_does_not_hold.txt").read_text().rstrip("\n")
    )


def test_undetermined_certificate_names_its_reasons() -> None:
    ruling = make_ruling(
        verdict=Verdict.UNDETERMINED,
        statistic=None,
        threshold=None,
        rho_min=None,
        reasons=("insufficient_items: 3 < floor 25",),
    )
    cert = certificate_from_ruling(ruling_body(ruling))
    assert "IS UNDETERMINED (insufficient_items: 3 < floor 25)" in cert.line


def test_every_certificate_carries_the_no_weights_sentence() -> None:
    """PMK-CRT-002: the sentence is in the line AND the body, on every verdict."""
    for verdict in Verdict:
        ruling = make_ruling(
            verdict=verdict,
            reasons=("r",) if verdict is Verdict.UNDETERMINED else (),
        )
        cert = certificate_from_ruling(ruling_body(ruling))
        assert NO_WEIGHTS in cert.line
        assert cert.body["scope"] == NO_WEIGHTS


def test_certificate_names_candidate_set_in_the_verdict_sentence() -> None:
    cert = certificate_from_ruling(ruling_body(make_ruling()))
    assert "against candidate set pmk-cs-" in cert.line
    assert "(2 routes)" in cert.line


def test_exit_codes_are_tristate() -> None:
    assert exit_code_for(Verdict.SAME_PRODUCER) == 0
    assert exit_code_for(Verdict.SUBSTITUTED) == 1
    assert exit_code_for(Verdict.UNDETERMINED) == 2


def test_malformed_ruling_body_is_refused() -> None:
    with pytest.raises(CertificateError, match="malformed"):
        certificate_from_ruling({"verdict": "SAME-PRODUCER"})


@pytest.mark.parametrize(
    "missing",
    ["verdict", "route", "task", "operating_point", "candidates", "ruling_id",
     "n_items", "n_clusters", "statistic", "candidate_set_id", "detector",
     "model_id", "calibration_sha256", "spec_version"],
)
def test_missing_required_key_is_a_typed_refusal(missing: str) -> None:
    """Every required key is bound inside the malformed-body guard, so a bad body
    raises CertificateError (exit 2 at the CLI) and never a bare KeyError, which
    would escape as exit 1 -- the measured DOES-NOT-HOLD code (PMK-GTE-001)."""
    body = ruling_body(make_ruling())
    del body[missing]
    with pytest.raises(CertificateError):
        certificate_from_ruling(body)
