"""Lowering an emulation plan into simavr's native input.

Spec: "The Emulator Script Carries Only What The Lowering Writes" and
"Simulation Is A Compiler Target".

simavr's native input is a program linked against its library. The program is
fang's runner, `runner/fang_runner.c`, shipped as source; what the lowering
writes is what the runner reads: a configuration of lines from a fixed set,
and the firmware's flash image. A bundle is a function of the plan, the
firmware's bytes and the platform model the plan names: the configuration,
the runner's source, the firmware, its flash image, the plan itself, and a
manifest of digests. Every value written is a validated identifier, an integer
or a file name of the bundle, so no text from a Fang program reaches the
runner unchecked.

The flash image is cut from the ELF here, in Python, rather than by the
runner: the runner then needs no ELF library, and the image is a pure
function of the firmware that is tested without simavr.
"""

from __future__ import annotations

import hashlib
import re
import struct
from importlib import resources
from typing import TYPE_CHECKING, Mapping

from ..serialization import canonical_bytes

if TYPE_CHECKING:
    from ..emulation import EmulationPlan

#: The simavr releases the runner and the ATtiny descriptors were checked
#: against. 1.6, which distributions package, wires the ATtiny24/44/84 compare
#: outputs to the wrong pins (fixed in 1.7); another version is reported
#: unsupported rather than trusted.
SUPPORTED_VERSIONS = frozenset({"1.8"})

#: Why a version is refused where the reason is known.
REFUSED_VERSIONS = {
    "1.6": "it wires the ATtiny24/44/84 compare outputs (OC0A, OC0B, OC1A, OC1B) to PB0, "
    "PB1, PB1 and PB2, where the parts have them on PB2, PA7, PA6 and PA5",
}

#: What the files of a bundle are called.
PLAN = "plan.json"
CONFIG = "run.cfg"
RUNNER = "fang_runner.c"
FIRMWARE = "firmware.elf"
FLASH = "flash.bin"
MANIFEST = "manifest.json"
EVENTS = "events.jsonl"

#: What a run leaves beside its bundle: the runner's output, and how it ended.
LOG = "simavr.log"
OUTCOME = "outcome.json"

#: The configuration's own version, which the runner checks first.
CONFIG_VERSION = "fang-simavr-run 1"

#: An identifier the runner may write into its JSON events unescaped: no
#: quote, backslash, space or control character can be in one.
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_MCU = re.compile(r"[a-z][a-z0-9]{1,31}")
_REGISTER = re.compile(r"[A-Z][A-Z0-9]{0,15}")
_PORT = re.compile(r"[A-Z]")

#: AVR ELF address spaces: flash from 0, then the data space, EEPROM, fuses,
#: lock bits and signature, each at its offset in the linker's address map.
_DATA_SPACE = 0x800000
_EEPROM_SPACE = 0x810000
_FUSE_SPACE = 0x820000
_EM_AVR = 83
_PT_LOAD = 1


class LoweringError(ValueError):
    """The plan or the firmware holds something the lowering will not write."""


def _identifier(text: str, what: str) -> str:
    if not _IDENTIFIER.fullmatch(text):
        raise LoweringError(f"{what} {text!r} is not an identifier the lowering will write")
    return text


def flash_image(firmware: bytes, flash_bytes: int) -> bytes:
    """The bytes an ISP programmer writes into the part's flash, cut from an
    AVR ELF: every loaded segment whose physical address is in flash, at that
    address, the gaps between them erased to 0xFF.

    Refused: anything but a little-endian 32-bit AVR ELF; a segment that runs
    past the part's flash, which the part could not hold; a segment that
    loads into RAM rather than into the flash RAM is initialized from; and an
    EEPROM image, since nothing states that the part's EEPROM is programmed
    with it and the runner does not program it. The fuse, lock and signature
    spaces are not programmed: the fuses are the binding's to state.
    """
    if len(firmware) < 52 or firmware[:4] != b"\x7fELF":
        raise LoweringError("the firmware is not an ELF file")
    if firmware[4] != 1 or firmware[5] != 1:
        raise LoweringError("the firmware is not a little-endian 32-bit ELF, as an AVR one is")
    (machine,) = struct.unpack_from("<H", firmware, 18)
    if machine != _EM_AVR:
        raise LoweringError(f"the firmware is built for ELF machine {machine}, not AVR ({_EM_AVR})")
    (phoff,) = struct.unpack_from("<I", firmware, 28)
    phentsize, phnum = struct.unpack_from("<HH", firmware, 42)
    loaded: list[tuple[int, bytes]] = []
    for index in range(phnum):
        offset = phoff + index * phentsize
        if offset + 32 > len(firmware):
            raise LoweringError("the firmware's program headers run past its end")
        kind, file_offset, _, address, size, _, _, _ = struct.unpack_from("<8I", firmware, offset)
        if kind != _PT_LOAD or size == 0:
            continue
        if file_offset + size > len(firmware):
            raise LoweringError("a segment of the firmware runs past the file's end")
        if _EEPROM_SPACE <= address < _FUSE_SPACE:
            raise LoweringError(
                f"the firmware carries an EEPROM image of {size} bytes; nothing states that "
                "the part's EEPROM is programmed with it, and the runner does not program it"
            )
        if address >= _FUSE_SPACE:
            continue                  # fuses, lock bits, signature: not flash
        if address >= _DATA_SPACE:
            raise LoweringError(
                f"a segment of the firmware loads {size} bytes into RAM at 0x{address - _DATA_SPACE:04X}; "
                "the part starts with nothing in RAM but what its startup code copies from flash"
            )
        if address + size > flash_bytes:
            raise LoweringError(
                f"the firmware loads flash up to 0x{address + size:X}, past the part's "
                f"{flash_bytes} bytes"
            )
        loaded.append((address, firmware[file_offset:file_offset + size]))
    if not loaded:
        raise LoweringError("the firmware loads nothing into flash")
    image = bytearray(b"\xff" * max(address + len(data) for address, data in loaded))
    for address, data in sorted(loaded):
        image[address:address + len(data)] = data
    return bytes(image)


def configuration(plan: "EmulationPlan", model: Mapping) -> str:
    """The runner's configuration: the core, the clock, the run's bound, the
    pins to observe and the registers to watch, in lines of the fixed set the
    runner reads and nothing else."""
    if plan.run_until_ns <= 0:
        raise LoweringError(f"the run lasts {plan.run_until_ns} ns; a run of no time observes nothing")
    if plan.clock is None:
        raise LoweringError("a simavr plan carries its clock; this one carries none")
    if plan.buses or plan.stimuli or plan.faults or plan.watched or plan.registers:
        raise LoweringError(
            "the runner observes pins and nothing else: this plan names a bus, a stimulus, "
            "a fault, a watched peripheral or a register"
        )
    mcu = model["mcu"]
    if not _MCU.fullmatch(mcu):
        raise LoweringError(f"the core {mcu!r} is not a name the lowering will write")
    clock = plan.clock
    lines = [
        CONFIG_VERSION,
        f"mcu {mcu}",
        f"oscillator_hz {int(clock['oscillator_hz'])}",
        f"prescaler {int(clock['prescaler'])}",
        f"prescaler_register 0x{_io_address(clock['prescaler_register']):02X}",
        f"seed {int(plan.seed)}",
        f"run_until_ns {int(plan.run_until_ns)}",
        f"flash {FLASH}",
        f"events {EVENTS}",
        f"target {_identifier(plan.target, 'the target')}",
    ]
    seen: set[str] = set()
    for observation in plan.observations:
        if observation.kind != "gpio":
            raise LoweringError(f"the runner observes pins, not a {observation.kind}")
        entity = _identifier(observation.entity, "an observed signal")
        if entity in seen:
            raise LoweringError(f"{entity} is observed twice; each signal is observed on its one pin")
        seen.add(entity)
        port = observation.emulator
        if not _PORT.fullmatch(port) or not 0 <= int(observation.index) <= 7:
            raise LoweringError(f"the pin {port}{observation.index} is not one the lowering will write")
        lines.append(f"pin {entity} {port} {int(observation.index)}")
    for watch in model.get("watched", ()):
        name = watch["register"]
        if not _REGISTER.fullmatch(name):
            raise LoweringError(f"the register {name!r} is not a name the lowering will write")
        mask = int(watch["mask"], 16)
        if not 0 < mask <= 0xFF:
            raise LoweringError(f"the mask of {name} is {watch['mask']}; it names bits of one byte")
        mode = "write" if watch["every_write"] else "set"
        lines.append(f"watch {name} 0x{_io_address(watch['address']):02X} 0x{mask:02X} {mode}")
    return "\n".join(lines) + "\n"


def _io_address(text: str) -> int:
    """A register's data-space address, refused outside the I/O space the
    runner hooks."""
    address = int(text, 16)
    if not 0x20 <= address <= 0xFF:
        raise LoweringError(f"0x{address:02X} is not an I/O register's data-space address")
    return address


def _digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def runner_source() -> bytes:
    return resources.files("fang.simavr").joinpath("runner", RUNNER).read_bytes()


def bundle(plan: "EmulationPlan", firmware: bytes) -> dict[str, bytes]:
    """Every file of the bundle, by its name inside it.

    A function of the plan, the firmware's bytes and the platform model the
    plan names: the same three give the same bundle, byte for byte.
    """
    from ..emulation import EmulationError, descriptor

    try:
        model = descriptor(plan.platform)
    except EmulationError as exc:
        raise LoweringError(str(exc)) from None
    if model.engine != "simavr":
        raise LoweringError(f"{plan.platform} runs on {model.engine}, not simavr")
    files: dict[str, bytes] = {
        PLAN: canonical_bytes(plan.as_dict()),
        CONFIG: configuration(plan, model.document).encode("utf-8"),
        RUNNER: runner_source(),
        FIRMWARE: firmware,
        FLASH: flash_image(firmware, int(model.document["flash_bytes"])),
    }
    files[MANIFEST] = canonical_bytes(
        {
            "schema": "fang.emulation-bundle/v1",
            "plan": plan.hash,
            "seed": plan.seed,
            "engine": {"name": "simavr", "versions": sorted(SUPPORTED_VERSIONS)},
            "firmware": {"path": plan.firmware_path, "hash": _digest(firmware)},
            "files": {name: _digest(content) for name, content in sorted(files.items())},
        }
    )
    return files
