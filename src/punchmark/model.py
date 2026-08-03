"""Shared frozen types: the vocabulary of the whole tool.

No I/O and no policy lives here. ``ResponseSet`` is what readers produce and what
detectors consume; ``FittedModel`` is the seam between the detector and everything
downstream (calibration, scoring, rulings). The detector never sees a file path and
the readers never see a feature (ARCHITECTURE.md section 2).
"""

from __future__ import annotations

import enum
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from .canonical import content_id


class Verdict(enum.Enum):
    """The three-zone ruling. UNDETERMINED is first-class (PMK-RUL-001): it is what
    a passing statistic means when the archive could not have resolved the requested
    substitution anyway, and it is never a rounding of the other two."""

    SAME_PRODUCER = "SAME-PRODUCER"
    SUBSTITUTED = "SUBSTITUTED"
    UNDETERMINED = "UNDETERMINED"


@dataclass(frozen=True, slots=True)
class ResponseRow:
    """One archive line. ``raw_outputs`` is the ONLY field feature extraction may
    consume (PMK-FEA-001); everything else is identity and bookkeeping.

    ``variant``/``tier``/``intrinsic`` are optional because the native corpus ships
    two row schemas (ladder rows carry no tier) plus API error stubs that carry only
    ``{sample, profile, language}`` and no completions at all (PMK-ARC-002/003).
    """

    sample: str
    profile: str
    language: str
    variant: str | None
    tier: str | None
    intrinsic: Mapping[str, int] | None
    raw_outputs: tuple[str, ...]
    is_stub: bool

    @property
    def item_key(self) -> str:
        """Canonical item identity within one archive: (sample, variant, profile,
        language). Namespaced by the caller with task/split when joined across
        archives -- never joined on bare sample name across splits (re-mint hazard)."""
        return "|".join((self.sample, self.variant or "base", self.profile, self.language))

    @property
    def cluster(self) -> str:
        """The resampling cluster unit (PMK-CAL-001): the base sample name. A
        sample's variants, profiles and languages share program content and move
        together in every split, subsample and splice."""
        return self.sample


@dataclass(frozen=True, slots=True)
class Window:
    """A collection window, ISO-8601 UTC, always caller-declared via the sidecar
    (PMK-SDC-001): punchmark never infers time from content."""

    start_utc: str
    end_utc: str

    def as_dict(self) -> dict[str, str]:
        return {"start_utc": self.start_utc, "end_utc": self.end_utc}


@dataclass(frozen=True, slots=True)
class ResponseSet:
    """One archive, read: the primary unit of analysis (route name, task, window).

    ``route`` comes from the archive FILENAME, the by-construction label
    (PMK-ARC-001). ``window`` is None when no sidecar was supplied; scoring without
    a window refuses any cross-date semantics (PMK-SDC-001).
    """

    route: str
    task: str
    window: Window | None
    rows: tuple[ResponseRow, ...]
    archive_sha256: str
    source_name: str

    @property
    def valid_rows(self) -> tuple[ResponseRow, ...]:
        return tuple(r for r in self.rows if not r.is_stub and r.raw_outputs)

    @property
    def n_stub_rows(self) -> int:
        return sum(1 for r in self.rows if r.is_stub)

    @property
    def clusters(self) -> tuple[str, ...]:
        seen: dict[str, None] = {}
        for r in self.valid_rows:
            seen.setdefault(r.cluster, None)
        return tuple(seen)


@dataclass(frozen=True, slots=True)
class CandidateSet:
    """The closed candidate route set a verdict is relative to. Every identity in a
    ruling means route-as-served-by-provider, never weights (PMK-CRT-002); a
    SAME-PRODUCER verdict is 'best match within this set', not an identity proof
    (PMK-CRT-003)."""

    routes: tuple[str, ...]

    def __post_init__(self) -> None:
        if tuple(sorted(self.routes)) != self.routes:
            object.__setattr__(self, "routes", tuple(sorted(self.routes)))

    @property
    def candidate_set_id(self) -> str:
        return content_id({"routes": list(self.routes)}, "candidate_set_id", "pmk-cs")

    @property
    def slugs(self) -> dict[str, str]:
        """route -> archive-filename slug (``/`` becomes ``-``)."""
        return {r: r.replace("/", "-") for r in self.routes}


@dataclass(frozen=True, slots=True)
class OperatingPoint:
    """A calibrated decision threshold: the deliverable, not a detail. ``far`` is
    the declared false-substitution-alarm rate; ``threshold`` is the empirical
    far-quantile of the same-route within-window null of the set statistic T at set
    size ``m``, for one DECLARED route (PMK-CAL-004, PMK-CAL-006): pooling nulls
    across routes would let one inseparable pair's noise widen every route's
    threshold and silently spend power that the separated pairs actually have."""

    task: str
    route: str
    far: float
    m: int
    threshold: float
    n_null: int


@dataclass(frozen=True, slots=True)
class PowerPoint:
    """Minimum resolvable substituted fraction for one ordered candidate pair at
    one set size (output (d)): the number that makes a null legible as a power
    limit rather than as reassurance (PMK-POW-003)."""

    task: str
    declared: str
    substitute: str
    m: int
    far: float
    power_target: float
    rho_min: float | None  # None: not resolvable even at rho=1.0 on the grid


@runtime_checkable
class FittedModel(Protocol):
    """The fitted detector seam. Implementations never touch files and never import
    readers (PMK-DET-001); params are plain data that round-trip exactly."""

    @property
    def detector_id(self) -> str: ...
    @property
    def detector_version(self) -> str: ...
    @property
    def feature_spec(self) -> str: ...
    @property
    def view(self) -> str: ...
    @property
    def candidates(self) -> CandidateSet: ...
    @property
    def tasks(self) -> tuple[str, ...]: ...

    def score_rows(
        self, rows: Sequence[ResponseRow], task: str
    ) -> list[dict[str, float]]:
        """Per-row, per-candidate normalized log-likelihoods l_i(r). One row is one
        evidence unit regardless of its draw count (PMK-FEA-002)."""
        ...

    def to_params(self) -> dict[str, object]: ...


@runtime_checkable
class DetectorModel(Protocol):
    """A fittable detector family."""

    @property
    def detector_id(self) -> str: ...
    @property
    def detector_version(self) -> str: ...

    def fit(
        self, train: Sequence[ResponseSet], candidates: CandidateSet, seed: int
    ) -> FittedModel: ...


@dataclass(frozen=True, slots=True)
class Ruling:
    """One immutable verdict: the unit the store appends and the certificate cites.
    ``ruling_id`` pins the contractual four -- detector version, candidate set,
    operating point, calibration corpus hash (PMK-RUL-004) -- plus the archive and
    spec version, so an identical re-run reproduces the identical id."""

    ruling_id: str
    verdict: Verdict
    route: str
    task: str
    window: Window | None
    archive_sha256: str
    model_id: str
    detector_id: str
    detector_version: str
    candidate_set_id: str
    candidates: tuple[str, ...]
    far: float
    threshold: float | None
    calibration_sha256: str
    spec_version: str
    statistic: float | None
    per_candidate: Mapping[str, float]
    n_items: int
    n_clusters: int
    n_stub_rows: int
    rho_target: float
    rho_min: float | None
    scored_as: str | None = None
    reasons: tuple[str, ...] = field(default_factory=tuple)
    supersedes: str | None = None
    does_not_show: tuple[str, ...] = ("NO_WEIGHTS_CLAIM", "NO_CAUSE_CLAIM", "CLOSED_SET")


@dataclass(frozen=True, slots=True)
class Certificate:
    """The one-line certificate plus its machine form, always derived from exactly
    one ruling (PMK-CRT-001)."""

    certificate_id: str
    ruling_id: str
    line: str
    body: Mapping[str, object]
