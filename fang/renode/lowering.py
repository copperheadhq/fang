"""Lowering an emulation plan into Renode's native input.

Spec: "The Emulator Script Carries Only What The Lowering Writes" and "Simulation
Is A Compiler Target".

A bundle is a function of the plan alone: the platform description (the
shipped F401 platform, then the probes the plan names), the script, the probes'
C# source, the firmware, the plan itself, and a manifest of digests. Only
commands from the fixed set below are written, every value is a validated
identifier or a decimal string, and no text from a Fang program reaches
Renode's monitor or its Python.

Two facts about Renode shape what is written, both found by running it:
durations are read by an unanchored pattern with no units, so "100ms" would be
a hundred seconds and every duration is written as decimal seconds; and the
launcher runs from Renode's install directory, so every file is named as
`$ORIGIN/...`, relative to the script.
"""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from importlib import resources
from typing import TYPE_CHECKING, Mapping

from ..serialization import canonical_bytes

if TYPE_CHECKING:
    from ..emulation import EmulationPlan

#: The Renode release the lowering was checked against. Another version is
#: reported unsupported rather than given a script whose meaning may have moved.
SUPPORTED_VERSIONS = frozenset({"1.17.0"})

#: Names the platform description and the script may contain: Renode
#: identifiers, nothing a monitor would interpret.
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")

#: What the plan, the probes and the event file are called inside a bundle.
PLAN = "plan.json"
PLATFORM = "platform.repl"
SCRIPT = "run.resc"
PROBES = "fang_probes.cs"
FIRMWARE = "firmware.elf"
MANIFEST = "manifest.json"
EVENTS = "events.jsonl"


class LoweringError(ValueError):
    """The plan holds something the lowering will not write."""


def seconds(nanoseconds: int) -> str:
    """A duration as decimal seconds, the only form Renode reads correctly.

    `TimeInterval` parses with an unanchored pattern and no units, so "100ms"
    is a hundred seconds; "0.1" is a tenth of one.
    """
    if nanoseconds < 0:
        raise LoweringError(f"a duration cannot be negative: {nanoseconds} ns")
    value = Decimal(nanoseconds).scaleb(-9).normalize()
    text = format(value, "f")
    return text


def _identifier(name: str, what: str) -> str:
    if not _IDENTIFIER.fullmatch(name):
        raise LoweringError(f"{what} {name!r} is not an identifier the lowering will write")
    return name


def _quoted(text: str, what: str) -> str:
    """A string argument for the monitor, refused if it could escape its quotes."""
    if any(c in text for c in '"\\\n\r') or not text.isprintable():
        raise LoweringError(f"{what} {text!r} contains characters the lowering will not write")
    return f'"{text}"'


def _package_text(*parts: str) -> str:
    return resources.files("fang.renode").joinpath(*parts).read_text(encoding="utf-8")


def _distinct_probes(plan: "EmulationPlan") -> None:
    """Refuse two probes of one name: Renode would refuse the second as
    already declared, after the run had started."""
    names = [device.probe for bus in plan.buses for device in bus.devices if not device.absent]
    names += [watch.probe for watch in plan.watched]
    names += [observation.probe for observation in plan.observations]
    seen: set[str] = set()
    for name in names:
        if name in seen:
            raise LoweringError(f"two probes are named {name!r}; each probe needs a name of its own")
        seen.add(name)


def platform_description(plan: "EmulationPlan") -> str:
    """The board overlay: the shipped platform, then each probe the plan names."""
    _distinct_probes(plan)
    recorder_port = _identifier(plan.recorder_port, "the recorder's port")
    lines = [f'using "{plan.platform_file.rsplit("/", 1)[-1]}"', ""]
    lines += [f"recorder: Fang.EventRecorder @ {recorder_port}", ""]
    for bus in plan.buses:
        controller = _identifier(bus.emulator, "a bus controller")
        for device in bus.devices:
            if device.absent:
                continue
            lines += [
                f"{_identifier(device.probe, 'a device probe')}: Fang.I2CProbe @ {controller} 0x{device.address:02X}",
                "    recorder: recorder",
                f"    model: {_quoted(device.renode_type, 'a model type')}",
                f"    source: {_quoted(device.component, 'an entity id')}",
                "",
            ]
    for watch in plan.watched:
        lines += [
            f"{_identifier(watch.probe, 'a warning probe')}: Fang.WarningProbe @ {recorder_port}",
            "    recorder: recorder",
            f"    target: {_identifier(watch.emulator, 'a watched peripheral')}",
            f"    source: {_quoted(watch.entity, 'an entity id')}",
            "",
        ]
    for observation in plan.observations:
        probe = _identifier(observation.probe, "an observation probe")
        if observation.kind == "gpio":
            port = _identifier(observation.emulator, "a GPIO port")
            lines += [
                f"{probe}: Fang.GpioProbe @ {recorder_port}",
                "    recorder: recorder",
                f"    source: {_quoted(observation.entity, 'an entity id')}",
                "",
                f"{port}:",
                f"    {int(observation.index)} -> {probe}@0",
                "",
            ]
        elif observation.kind == "uart":
            lines += [
                f"{probe}: Fang.UartProbe @ {recorder_port}",
                "    recorder: recorder",
                f"    uart: {_identifier(observation.emulator, 'a UART')}",
                f"    source: {_quoted(observation.entity, 'an entity id')}",
                "",
            ]
        else:
            raise LoweringError(f"an observation of kind {observation.kind!r} has no probe")
    return "\n".join(lines).rstrip("\n") + "\n"


def script(plan: "EmulationPlan") -> str:
    """The run: seed first, the platform, the watchpoints, the firmware, the
    stimulus segments, the read-backs, and an explicit end."""
    recorder = f"sysbus.{_identifier(plan.recorder_port, 'the recorder port')}.recorder"
    lines = [
        f"emulation SetSeed {int(plan.seed)}",
        f"include $ORIGIN/{PROBES}",
        f"mach create {_quoted(_identifier(plan.machine, 'the machine'), 'the machine')}",
        f"machine LoadPlatformDescription $ORIGIN/{PLATFORM}",
        f"{recorder} Open $ORIGIN/{EVENTS}",
    ]
    for register in plan.registers:
        lines.append(
            f"{recorder} WatchWrites {_quoted(register.source, 'an entity id')} "
            f"{_quoted(_identifier(register.peripheral, 'a peripheral'), 'a peripheral')} "
            f"{_quoted(_identifier(register.register, 'a register'), 'a register')} "
            f"0x{register.address:08X}"
        )
    lines.append(f"sysbus LoadELF $ORIGIN/{FIRMWARE}")

    controllers = {
        device.probe: bus.emulator
        for bus in plan.buses
        for device in bus.devices
        if not device.absent
    }
    now = 0
    for stimulus in sorted(plan.stimuli, key=lambda s: (s.at_ns, s.probe, s.property)):
        if stimulus.at_ns < now:
            raise LoweringError("stimuli are applied in time order")
        if stimulus.at_ns > plan.run_until_ns:
            raise LoweringError(
                f"a stimulus at {stimulus.at_ns} ns falls after the run ends at "
                f"{plan.run_until_ns} ns"
            )
        if stimulus.at_ns > now:
            lines.append(f'emulation RunFor "{seconds(stimulus.at_ns - now)}"')
            now = stimulus.at_ns
        controller = controllers.get(stimulus.probe)
        if controller is None:
            raise LoweringError(f"a stimulus names {stimulus.probe!r}, which is not on a bus")
        lines.append(
            f"sysbus.{_identifier(controller, 'a controller')}."
            f"{_identifier(stimulus.probe, 'a device probe')} SetInput "
            f"{_quoted(_identifier(stimulus.property, 'an input'), 'an input')} "
            f"{_quoted(_decimal_text(stimulus.value), 'a value')}"
        )
    if plan.run_until_ns > now:
        lines.append(f'emulation RunFor "{seconds(plan.run_until_ns - now)}"')

    for register in plan.registers:
        if register.stored:
            lines.append(
                f"{recorder} Snapshot {_quoted(register.source, 'an entity id')} "
                f"{_quoted(register.peripheral, 'a peripheral')} "
                f"{_quoted(register.register, 'a register')} 0x{register.address:08X}"
            )
    lines += [f'{recorder} Finish "completed"', "quit"]
    return "\n".join(lines) + "\n"


def _decimal_text(value: str) -> str:
    try:
        parsed = Decimal(value)
    except Exception as exc:  # decimal.InvalidOperation
        raise LoweringError(f"{value!r} is not a decimal value") from exc
    if not parsed.is_finite():
        raise LoweringError(f"{value!r} is not a finite value")
    return format(parsed, "f")


def _digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def bundle(plan: "EmulationPlan", firmware: bytes) -> dict[str, bytes]:
    """Every file of the bundle, by its name inside it.

    A function of the plan and the firmware's bytes: the same two give the same
    bundle, byte for byte.
    """
    files: dict[str, bytes] = {
        PLAN: canonical_bytes(plan.as_dict()),
        PLATFORM: platform_description(plan).encode("utf-8"),
        SCRIPT: script(plan).encode("utf-8"),
        PROBES: _package_text("probes", "fang_probes.cs").encode("utf-8"),
        plan.platform_file.rsplit("/", 1)[-1]: _package_text(*plan.platform_file.split("/")).encode("utf-8"),
        FIRMWARE: firmware,
    }
    files[MANIFEST] = canonical_bytes(
        {
            "schema": "fang.emulation-bundle/v1",
            "plan": plan.hash,
            "seed": plan.seed,
            "engine": {"name": "renode", "versions": sorted(SUPPORTED_VERSIONS)},
            "firmware": {"path": plan.firmware_path, "hash": _digest(firmware)},
            "files": {name: _digest(content) for name, content in sorted(files.items())},
        }
    )
    return files


def digests(files: Mapping[str, bytes]) -> dict[str, str]:
    return {name: _digest(content) for name, content in sorted(files.items())}
