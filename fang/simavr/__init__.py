"""simavr as fang's firmware emulator for AVR cores.

Spec: "Simulation Is A Compiler Target", "The Emulator Script Carries Only What
The Lowering Writes" and "The Emulator Is Reported, Never Substituted".

simavr's native input is a program linked against its library, as a `.repl`
and a `.resc` are Renode's. fang ships the source of one such program, the
runner (`runner/fang_runner.c`); the lowering turns an emulation plan into the
configuration it reads and the flash image it loads, and the backend builds
the runner on the host against the installed simavr and runs it as a process
of its own. fang neither links simavr nor distributes a binary linked against
it. Shipped beside them as package data: the runner's source and the model
descriptors (`models/`).
"""

from . import lowering
from .backend import Installation, SimavrBackend, SimavrRun, SimavrUnavailable
from .lowering import SUPPORTED_VERSIONS, LoweringError, bundle, configuration, flash_image

#: The names every engine package gives its backend and its refusal, which
#: `fang.emulation.EmulationTool` reaches the engine through.
Backend = SimavrBackend
Unavailable = SimavrUnavailable

__all__ = [
    "SUPPORTED_VERSIONS",
    "Backend",
    "Installation",
    "LoweringError",
    "SimavrBackend",
    "SimavrRun",
    "SimavrUnavailable",
    "Unavailable",
    "bundle",
    "configuration",
    "flash_image",
    "lowering",
]
