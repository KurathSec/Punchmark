"""punchmark: a retrospective producer identifier for hosted LLM routes.

Public facade re-exports only; importing this package touches no file and no
foreign name. Verdicts are statements about the route label as served within a
declared candidate set, never about model weights (PMK-CRT-002).
"""

from ._version import __version__
from .archive import read_archive
from .calibrate import CalibrationConfig, calibrate
from .errors import PunchmarkError
from .model import (
    CandidateSet,
    Certificate,
    DetectorModel,
    FittedModel,
    OperatingPoint,
    PowerPoint,
    ResponseRow,
    ResponseSet,
    Ruling,
    Verdict,
    Window,
)
from .modelfile import ModelDoc, read_model
from .power import PowerConfig, power_analysis
from .score import RulePolicy, rule
from .sidecar import load_sidecar

__all__ = [
    "CalibrationConfig",
    "CandidateSet",
    "Certificate",
    "DetectorModel",
    "FittedModel",
    "ModelDoc",
    "OperatingPoint",
    "PowerConfig",
    "PowerPoint",
    "PunchmarkError",
    "ResponseRow",
    "ResponseSet",
    "Ruling",
    "RulePolicy",
    "Verdict",
    "Window",
    "__version__",
    "calibrate",
    "load_sidecar",
    "power_analysis",
    "read_archive",
    "read_model",
    "rule",
]
