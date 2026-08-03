"""Versioned text views: the declared normalizations of completion text.

A view id (e.g. ``CANON@1``) is part of every fitted model and every ruling id; a
changed normalization is a new view version, never a silent edit (PMK-FEA-003).
Three views ship:

- ``RAW@1``: the committed string, untouched.
- ``CANON@1``: the primary view -- NFC, one outer code-fence pair stripped,
  whitespace runs collapsed, case PRESERVED (identifier casing is genuine style
  signal in code).
- ``ABL@1``: the recorded formatting-ablation recipe -- all fence lines stripped,
  whitespace collapsed, lowercased, truncated to the first 200 characters. It
  exists so the kill test can ask whether the detector is keying on the prompt
  template's formatting rather than on producer behaviour.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable

from .errors import FeatureError

_FENCE_LINE = re.compile(r"^\s*```[^\n`]*\s*$")
_WS_RUN = re.compile(r"[ \t]+")
_BLANK_RUN = re.compile(r"\n\s*\n+")


def _view_raw(text: str) -> str:
    return text


def _strip_outer_fence(text: str) -> str:
    lines = text.strip().split("\n")
    if len(lines) >= 2 and _FENCE_LINE.match(lines[0]) and _FENCE_LINE.match(lines[-1]):
        return "\n".join(lines[1:-1])
    return text


def _view_canon(text: str) -> str:
    out = unicodedata.normalize("NFC", text)
    out = _strip_outer_fence(out)
    out = _WS_RUN.sub(" ", out)
    out = _BLANK_RUN.sub("\n", out)
    return out.strip()


def _view_abl(text: str) -> str:
    lines = [ln for ln in text.split("\n") if not _FENCE_LINE.match(ln)]
    out = " ".join(" ".join(lines).split())
    return out.lower()[:200]


VIEWS: dict[str, Callable[[str], str]] = {
    "RAW@1": _view_raw,
    "CANON@1": _view_canon,
    "ABL@1": _view_abl,
}


def apply_view(view: str, text: str) -> str:
    try:
        fn = VIEWS[view]
    except KeyError:
        raise FeatureError(
            f"unknown text view {view!r}; shipped views: {sorted(VIEWS)}"
        ) from None
    return fn(text)
