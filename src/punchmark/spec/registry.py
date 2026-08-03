"""Registry of spec rulings: numbered design decisions with immutable meaning.

Every load-bearing choice in punchmark is a numbered ruling in ``rulings/*.toml``,
cited from the code that implements it and from the tests that pin it. A ruling
is never edited to mean something else; it is superseded (status change plus a
new ruling), and the rulings-spec version moves. ``require(id)`` is the runtime
citation: it returns the ruling and refuses superseded or unknown ids.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from ..errors import SpecError


@dataclass(frozen=True, slots=True)
class Decision:
    id: str
    title: str
    text: str
    status: str  # "active" | "superseded"


@lru_cache(maxsize=1)
def _load() -> tuple[str, dict[str, Decision]]:
    root = resources.files("punchmark.spec.rulings")
    index = tomllib.loads(root.joinpath("index.toml").read_text(encoding="utf-8"))
    version = str(index["version"])
    decisions: dict[str, Decision] = {}
    for entry in root.iterdir():
        if not entry.name.endswith(".toml") or entry.name == "index.toml":
            continue
        data = tomllib.loads(entry.read_text(encoding="utf-8"))
        for raw in data.get("ruling", []):
            decision = Decision(
                id=str(raw["id"]),
                title=str(raw["title"]),
                text=str(raw["text"]),
                status=str(raw.get("status", "active")),
            )
            if decision.id in decisions:
                raise SpecError(f"duplicate spec ruling id {decision.id}")
            decisions[decision.id] = decision
    return version, decisions


def spec_version() -> str:
    return _load()[0]


def all_decisions() -> tuple[Decision, ...]:
    return tuple(sorted(_load()[1].values(), key=lambda d: d.id))


def require(ruling_id: str) -> Decision:
    """Cite a ruling at runtime; refuses unknown or superseded ids."""
    decisions = _load()[1]
    if ruling_id not in decisions:
        raise SpecError(f"unknown spec ruling {ruling_id!r}")
    decision = decisions[ruling_id]
    if decision.status != "active":
        raise SpecError(f"spec ruling {ruling_id} is {decision.status}; cite its successor")
    return decision
