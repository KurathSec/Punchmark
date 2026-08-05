"""Exception taxonomy.

Every refusal punchmark issues is one of these, and every message names the fix.
A refusal is exit code 1 at the CLI under fit, score and gate. Under certify every
typed refusal is exit 2 instead, because exit 1 there means exactly one thing: a
measured DOES NOT HOLD (PMK-CRT-001, PMK-GTE-001). Malformed usage and unevaluable
input are always exit 2. None of these is ever allowed to look like a measured
verdict.
"""

from __future__ import annotations


class PunchmarkError(Exception):
    """Base class for every error punchmark raises deliberately."""


class ArchiveError(PunchmarkError):
    """A response archive could not be read (unknown filename shape, malformed row,
    a row that is neither a completion record nor a recognized error stub)."""


class SidecarError(PunchmarkError):
    """The window sidecar is missing, malformed, or disagrees with the archive
    (route/task mismatch against the filename, archive hash mismatch)."""


class FeatureError(PunchmarkError):
    """A feature spec or text view was cited that does not exist, or feature
    extraction was asked to consume anything other than completion text."""


class DetectorError(PunchmarkError):
    """A detector violated its contract (unknown detector id, params that do not
    round-trip, a fit over fewer than two candidates)."""


class CalibrationError(PunchmarkError):
    """Calibration could not produce a null (too few clusters, no same-window
    material, an operating point requested outside the calibrated range)."""


class ModelFileError(PunchmarkError):
    """A fitted-model file is unreadable, has an unknown schema, or fails its
    content hash."""


class RulingError(PunchmarkError):
    """The ruling store violated an invariant (hash mismatch on an existing line,
    a supersedes target that does not exist, an edit to an existing ruling)."""


class CertificateError(PunchmarkError):
    """A certificate could not be assembled from its ruling."""


class GateError(PunchmarkError):
    """The gate could not evaluate its inputs (unreadable baseline, wrong schema,
    empty selection)."""


class CorpusError(PunchmarkError):
    """The calibration corpus failed verification or could not be rebuilt
    (manifest hash mismatch, missing source checkout, wrong source bytes)."""


class SpecError(PunchmarkError):
    """A spec ruling was cited that does not exist or is superseded."""


class SynthError(PunchmarkError):
    """The synthetic archive generator was asked for an impossible configuration."""
