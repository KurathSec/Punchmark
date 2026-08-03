"""The certificate emitter: one line of text plus a machine-readable document,
always derived from exactly one ruling (PMK-CRT-001).

The wording rules are rulings, not style: the certificate certifies the ROUTE
LABEL as served, never the weights (PMK-CRT-002), and every verdict is relative
to a closed candidate set (PMK-CRT-003). The tri-state maps to exit codes at the
CLI: HOLDS 0, DOES NOT HOLD 1, UNDETERMINED 2 -- an undetermined certificate can
never read as success.
"""

from __future__ import annotations

from typing import Any

from .canonical import canonical_json, content_id
from .errors import CertificateError
from .model import Certificate, Verdict

_SCOPE_SENTENCE = (
    "This certifies the route label as served within the named candidate set; "
    "it is not a statement about model weights."
)


def _task_text(body: dict[str, Any]) -> str:
    scored_as = body.get("scored_as")
    task = body["task"]
    return f"task {task}, scored as {scored_as}" if scored_as else f"task {task}"


def _window_text(body: dict[str, Any]) -> str:
    window = body.get("window")
    if not window:
        return "window UNDECLARED"
    return f"window {window['start_utc']}..{window['end_utc']}"


def certificate_from_ruling(body: dict[str, Any]) -> Certificate:
    """Build the certificate for one verified ruling body."""
    try:
        verdict = Verdict(body["verdict"])
        route = body["route"]
        task = body["task"]
        far = body["operating_point"]["far"]
        n_routes = len(body["candidates"])
        ruling_id = body["ruling_id"]
    except (KeyError, ValueError, TypeError) as exc:
        raise CertificateError(f"ruling body is malformed ({exc!r})") from exc

    if verdict is Verdict.SAME_PRODUCER:
        clause = (
            f"HOLDS at false-alarm rate {far}"
            + (
                f"; minimum resolvable substituted fraction {body['rho_min']}"
                if body.get("rho_min") is not None
                else ""
            )
        )
    elif verdict is Verdict.SUBSTITUTED:
        clause = (
            f"DOES NOT HOLD at false-alarm rate {far}: statistic "
            f"{body['statistic']} fell below the calibrated threshold "
            f"{body['operating_point']['threshold']}"
        )
    else:
        reasons = "; ".join(body.get("reasons", [])) or "unspecified"
        clause = f"IS UNDETERMINED ({reasons})"

    cert_body: dict[str, Any] = {
        "punchmark_schema": "certificate/v1",
        "certificate_id": "",
        "ruling_id": ruling_id,
        "verdict": verdict.value,
        "route": route,
        "task": task,
        "scored_as": body.get("scored_as"),
        "window": body.get("window"),
        "operating_point": body["operating_point"],
        "candidate_set_id": body["candidate_set_id"],
        "candidates": body["candidates"],
        "model_id": body["model_id"],
        "detector": body["detector"],
        "calibration_sha256": body["calibration_sha256"],
        "spec_version": body["spec_version"],
        "rho_target": body.get("rho_target"),
        "rho_min": body.get("rho_min"),
        "scope": _SCOPE_SENTENCE,
        "does_not_show": body.get("does_not_show", []),
    }
    cert_id = content_id(cert_body, "certificate_id", "pmk-c")
    cert_body["certificate_id"] = cert_id

    line = (
        f"punchmark certificate {cert_id}: producer identity of route {route} "
        f"({_task_text(body)}, {_window_text(body)}) {clause} against candidate set "
        f"{body['candidate_set_id']} ({n_routes} routes). {_SCOPE_SENTENCE} "
        f"[detector {body['detector']['id']} v{body['detector']['version']}; "
        f"model {body['model_id']}; ruling {ruling_id}]"
    )
    return Certificate(certificate_id=cert_id, ruling_id=ruling_id, line=line, body=cert_body)


def certificate_json(cert: Certificate) -> str:
    return canonical_json(dict(cert.body))


def exit_code_for(verdict: Verdict) -> int:
    """Tri-state exit discipline: 0 HOLDS / 1 DOES NOT HOLD / 2 UNDETERMINED."""
    if verdict is Verdict.SAME_PRODUCER:
        return 0
    if verdict is Verdict.SUBSTITUTED:
        return 1
    return 2
