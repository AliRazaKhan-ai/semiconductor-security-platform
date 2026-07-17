"""Purpose: Export the production hybrid PUF simulator public API.
Directory: app/hardware/puf.
Dependencies: adapter, configuration, schemas, simulator, verifier.
Connection: Pipeline, terminal CLI, tests, and future service composition import from this package.
"""

from app.hardware.puf.adapter import PUFAdapter
from app.hardware.puf.config import PUFConfig, load_puf_config
from app.hardware.puf.schemas import (
    AuthenticationResult,
    EnrollmentProfile,
    PUFChallenge,
    PUFEnvironment,
    PUFResponse,
)
from app.hardware.puf.simulator import ChallengeFactory, HybridPUFSimulator

__all__ = [
    "AuthenticationResult",
    "ChallengeFactory",
    "EnrollmentProfile",
    "HybridPUFSimulator",
    "PUFAdapter",
    "PUFChallenge",
    "PUFConfig",
    "PUFEnvironment",
    "PUFResponse",
    "load_puf_config",
]
