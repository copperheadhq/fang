"""Renode as fang's firmware emulator.

Spec: "Simulation Is A Compiler Target", "The Emulator Script Carries Only What
The Lowering Writes" and "The Emulator Is Reported, Never Substituted".

The lowering turns an emulation plan into Renode's own platform description
and script; the backend runs Renode on a copy of that bundle across a process
boundary. Shipped beside them as package data: the F401 platform description
derived from Renode's (`platforms/`), the probes Renode compiles at load
(`probes/`), and the model descriptors that say what each model covers
(`models/`).
"""

from .backend import RenodeBackend, RenodeRun, RenodeUnavailable
from .lowering import SUPPORTED_VERSIONS, LoweringError, bundle, platform_description, script, seconds

__all__ = [
    "SUPPORTED_VERSIONS",
    "LoweringError",
    "RenodeBackend",
    "RenodeRun",
    "RenodeUnavailable",
    "bundle",
    "platform_description",
    "script",
    "seconds",
]
