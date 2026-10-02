"""Firmware emulation: compiled firmware run against the board a program describes.

Spec: "Firmware Is Bound And Its Digest Is Evidence", "Emulation Models Declare
What They Cover", "Emulation Questions Are Declared", "The Emulation Plan
Resolves Everything Before Anything Runs", "Observation Comes From Probes, Not
From The Firmware's Report", "Pin Configuration Is Measured", "Absence Is An
Observation; An Incomplete Run Is Not", "Emulation Runs Are Deterministic And
Identified", and "The Emulate Command".

An emulation question is a verification question whose method is emulation
and whose level is behavioural. It compiles into a plan in which every bus,
pin, selector and address is already resolved from the graph; the plan lowers
into the emulator's own input (`fang.renode`); the emulator's probes record
what devices, pins and UARTs were observed doing; and the measures here turn
that record into `Decimal` quantities for the verification runner to take back
through the commit gate.

Three rules keep a measure honest about what a run could see. An event that
did not occur in a run that completed was observed not to occur before the
run's end, and is measured as the half-open range after it, so interval
comparison decides exactly what was observed. A run that ended on a timeout or
a crash measures nothing. And a warning from a model that its descriptor does
not expect withdraws every measure over that model's events.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal
from functools import lru_cache
from importlib import resources
from typing import Any, Mapping, Sequence

from .serialization import content_hash
from .units import Quantity

#: Billionths of a second in one: event times are integer nanoseconds.
_NS = Decimal(1_000_000_000)

INFINITY = Decimal("Infinity")


# --------------------------------------------------------------------------
# Descriptors
# --------------------------------------------------------------------------


class EmulationError(ValueError):
    """An emulation question that cannot be planned, named rather than guessed."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Descriptor:
    """What one emulation model stands for and covers. Data, shipped with fang."""

    id: str
    kind: str
    document: Mapping[str, Any]

    @property
    def qualification(self) -> str:
        return self.document["qualification"]

    @property
    def not_modelled(self) -> tuple[str, ...]:
        return tuple(self.document.get("not_modelled", ()))

    @property
    def faults(self) -> tuple[str, ...]:
        return tuple(self.document.get("faults", ()))

    @property
    def inputs(self) -> Mapping[str, Mapping[str, str]]:
        return self.document.get("inputs", {})

    @property
    def expected_warnings(self) -> tuple[Mapping[str, str], ...]:
        return tuple(self.document.get("expected_warnings", ()))

    @property
    def provenance(self) -> Mapping[str, str]:
        return self.document.get("provenance", {})


@lru_cache(maxsize=1)
def descriptors() -> Mapping[str, Descriptor]:
    """Every descriptor fang ships, by its id."""
    found: dict[str, Descriptor] = {}
    folder = resources.files("fang.renode").joinpath("models")
    for entry in sorted(folder.iterdir(), key=lambda e: e.name):
        if not entry.name.endswith(".json"):
            continue
        document = json.loads(entry.read_text(encoding="utf-8"))
        found[document["id"]] = Descriptor(document["id"], document["kind"], document)
    return found


def descriptor(source: str) -> Descriptor:
    """The descriptor a model names. There is no generic model to fall back to."""
    try:
        return descriptors()[source]
    except KeyError:
        raise EmulationError(
            f"no emulation model descriptor {source!r} is shipped; a part with no "
            "descriptor is refused rather than given a generic model",
            code="model",
        ) from None


# --------------------------------------------------------------------------
# The plan
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanPin:
    pin: str
    vendor: str
    signal: str
    selector: str | None
    open_drain: bool
    port: str
    index: int

    def as_dict(self) -> dict:
        out = {
            "pin": self.pin,
            "vendor": self.vendor,
            "signal": self.signal,
            "open_drain": self.open_drain,
            "emulator": {"port": self.port, "index": self.index},
        }
        if self.selector is not None:
            out["selector"] = self.selector
        return out


@dataclass(frozen=True)
class PlanDevice:
    component: str
    probe: str
    model: str
    renode_type: str
    address: int
    absent: bool = False

    def as_dict(self) -> dict:
        return {
            "component": self.component,
            "probe": self.probe,
            "model": self.model,
            "renode_type": self.renode_type,
            "address": self.address,
            "absent": self.absent,
        }


@dataclass(frozen=True)
class PlanBus:
    port: str
    instance: str
    emulator: str
    pins: tuple[PlanPin, ...]
    devices: tuple[PlanDevice, ...]

    def as_dict(self) -> dict:
        return {
            "port": self.port,
            "instance": self.instance,
            "emulator": self.emulator,
            "pins": [p.as_dict() for p in self.pins],
            "devices": [d.as_dict() for d in self.devices],
        }


@dataclass(frozen=True)
class PlanObservation:
    probe: str
    kind: str                         # gpio, uart
    entity: str
    surface: str
    emulator: str
    index: int | None = None

    def as_dict(self) -> dict:
        out = {
            "probe": self.probe,
            "kind": self.kind,
            "entity": self.entity,
            "surface": self.surface,
            "emulator": self.emulator,
        }
        if self.index is not None:
            out["index"] = self.index
        return out


@dataclass(frozen=True)
class PlanWatch:
    probe: str
    emulator: str
    entity: str

    def as_dict(self) -> dict:
        return {"probe": self.probe, "emulator": self.emulator, "entity": self.entity}


@dataclass(frozen=True)
class PlanRegister:
    source: str
    peripheral: str
    register: str
    address: int
    reset: int
    stored: bool

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "peripheral": self.peripheral,
            "register": self.register,
            "address": f"0x{self.address:08X}",
            "reset": f"0x{self.reset:08X}",
            "stored": self.stored,
        }


@dataclass(frozen=True)
class PlanStimulus:
    at_ns: int
    component: str
    probe: str
    input: str
    property: str
    value: str                        # a decimal string, in the model's unit
    unit: str

    def as_dict(self) -> dict:
        return {
            "at_ns": self.at_ns,
            "component": self.component,
            "probe": self.probe,
            "input": self.input,
            "property": self.property,
            "value": self.value,
            "unit": self.unit,
        }


@dataclass(frozen=True)
class EmulationPlan:
    """An emulation question compiled against a snapshot, with every reference
    resolved. Canonical, and identified by the hash of its canonical form; the
    snapshot hash is recorded beside it and is not part of that identity."""

    question: str
    requirement: str
    snapshot: str
    machine: str
    platform: str
    platform_file: str
    recorder_port: str
    target: str
    firmware_path: str
    firmware_target: str
    core_clock_hz: int
    seed: int
    run_until_ns: int
    buses: tuple[PlanBus, ...] = ()
    observations: tuple[PlanObservation, ...] = ()
    watched: tuple[PlanWatch, ...] = ()
    registers: tuple[PlanRegister, ...] = ()
    stimuli: tuple[PlanStimulus, ...] = ()
    faults: tuple[Mapping[str, str], ...] = ()
    measures: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    models: tuple[Mapping[str, Any], ...] = ()
    abstracted: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    coverage_gaps: tuple[str, ...] = ()
    expected_warnings: tuple[Mapping[str, str], ...] = ()

    def identity(self) -> dict:
        """The plan without the snapshot hash: what its identity covers."""
        return {
            "schema": "fang.emulation/v1",
            "question": self.question,
            "requirement": self.requirement,
            "machine": self.machine,
            "platform": {
                "model": self.platform,
                "file": self.platform_file,
                "recorder_port": self.recorder_port,
                "core_clock_hz": self.core_clock_hz,
            },
            "target": {
                "component": self.target,
                "firmware": {"path": self.firmware_path, "target": self.firmware_target},
            },
            "seed": self.seed,
            "run_until_ns": self.run_until_ns,
            "buses": [b.as_dict() for b in self.buses],
            "observations": [o.as_dict() for o in self.observations],
            "watched": [w.as_dict() for w in self.watched],
            "registers": [r.as_dict() for r in self.registers],
            "stimuli": [s.as_dict() for s in self.stimuli],
            "faults": [dict(f) for f in self.faults],
            "measures": {name: dict(m) for name, m in self.measures.items()},
            "models": [dict(m) for m in self.models],
            "abstracted": list(self.abstracted),
            "assumptions": list(self.assumptions),
            "coverage_gaps": list(self.coverage_gaps),
            "expected_warnings": [dict(w) for w in self.expected_warnings],
        }

    @property
    def hash(self) -> str:
        return content_hash(self.identity())

    def as_dict(self) -> dict:
        out = self.identity()
        out["plan"] = self.hash
        out["snapshot"] = self.snapshot
        return out

    def device(self, component: str) -> PlanDevice | None:
        for bus in self.buses:
            for device in bus.devices:
                if device.component == component:
                    return device
        return None

    def bus_of(self, component: str) -> PlanBus | None:
        for bus in self.buses:
            if any(device.component == component for device in bus.devices):
                return bus
        return None


# --------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Event:
    seq: int
    t_ns: int
    source: str
    type: str
    payload: Mapping[str, Any]


@dataclass(frozen=True)
class RunRecord:
    """The events of one run and how the run ended."""

    events: tuple[Event, ...]
    outcome: str                      # completed, timeout, crashed

    @property
    def completed(self) -> bool:
        return self.outcome == "completed" and any(e.type == "run.end" for e in self.events)

    @property
    def end_ns(self) -> int:
        ends = [e.t_ns for e in self.events if e.type == "run.end"]
        if ends:
            return ends[-1]
        return self.events[-1].t_ns if self.events else 0


def read_events(data: bytes) -> tuple[Event, ...]:
    """The event record, one JSON object per line, checked to be in order."""
    events: list[Event] = []
    for number, line in enumerate(data.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            # The last line of a run that was killed can be cut off.
            if number == len(data.decode("utf-8").splitlines()):
                break
            raise
        event = Event(int(raw["seq"]), int(raw["t_ns"]), raw["source"], raw["type"], raw.get("payload", {}))
        if events and (event.seq <= events[-1].seq or event.t_ns < events[-1].t_ns):
            raise ValueError(f"event {event.seq} is out of order in the record")
        events.append(event)
    return tuple(events)


def run_record(data: bytes, outcome: str) -> RunRecord:
    return RunRecord(read_events(data), outcome)


# --------------------------------------------------------------------------
# Matches and measures, as a program declares them
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Match:
    """Which events a measure counts, named by part surface."""

    kind: str                         # i2c.read, i2c.write, gpio.rise, gpio.fall, uart.line
    surface: str
    detail: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        out = {"kind": self.kind, "surface": self.surface}
        if self.detail:
            out["detail"] = dict(self.detail)
        return out


def I2CRead(device: str, register: int | None = None) -> Match:
    return Match("i2c.read", device, {"register": register} if register is not None else {})


def I2CWrite(device: str, data: Sequence[int] | None = None) -> Match:
    return Match("i2c.write", device, {"data": list(data)} if data is not None else {})


def Rises(surface: str) -> Match:
    return Match("gpio.rise", surface)


def Falls(surface: str) -> Match:
    return Match("gpio.fall", surface)


def UartLine(uart: str, contains: str | None = None) -> Match:
    return Match("uart.line", uart, {"contains": contains} if contains is not None else {})


@dataclass(frozen=True)
class MeasureSpec:
    """One measure over events, declared by surface and resolved by the plan."""

    kind: str                         # first_at, count, latency, uart_value, pin_config
    matches: tuple[Match, ...] = ()
    options: Mapping[str, Any] = field(default_factory=dict)

    def surfaces(self) -> tuple[str, ...]:
        named = [m.surface for m in self.matches]
        if "port" in self.options:
            named.append(self.options["port"])
        if "uart" in self.options:
            named.append(self.options["uart"])
        return tuple(named)


def _window_ns(within: Sequence[Quantity] | None) -> tuple[int, int] | None:
    if within is None:
        return None
    start, end = within
    return (_to_ns(start), _to_ns(end))


def _to_ns(quantity: Quantity) -> int:
    low, high = quantity.interval()
    if low != high:
        raise EmulationError(f"a window bound is a single time, not {quantity}")
    return int((Decimal(low) * _NS).to_integral_value())


def FirstAt(match: Match) -> MeasureSpec:
    return MeasureSpec("first_at", (match,))


def Count(match: Match, *, within: Sequence[Quantity] | None = None) -> MeasureSpec:
    window = _window_ns(within)
    return MeasureSpec("count", (match,), {"within_ns": list(window)} if window else {})


def Latency(from_: Match, to: Match) -> MeasureSpec:
    return MeasureSpec("latency", (from_, to))


def UartValue(uart: str, *, prefix: str, unit: Any) -> MeasureSpec:
    return MeasureSpec("uart_value", (), {"uart": uart, "prefix": prefix, "unit": str(unit)})


def PinConfig(port: str) -> MeasureSpec:
    return MeasureSpec("pin_config", (), {"port": port})


# --------------------------------------------------------------------------
# Measuring a run
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Measured:
    """One measure's value, or the reason it has none."""

    name: str
    quantity: Quantity | None
    reason: str | None = None
    firmware_report: bool = False


def _matches(event: Event, match: Mapping[str, Any]) -> bool:
    kind = match["kind"]
    source = match["entity"]
    if event.source != source:
        return False
    detail = match.get("detail", {})
    if kind == "i2c.read":
        return event.type == "i2c.read"
    if kind == "i2c.write":
        if event.type != "i2c.write":
            return False
        return "data" not in detail or list(event.payload.get("data", ())) == list(detail["data"])
    if kind == "gpio.rise":
        return event.type == "gpio.edge" and event.payload.get("level") == 1
    if kind == "gpio.fall":
        return event.type == "gpio.edge" and event.payload.get("level") == 0
    if kind == "uart.line":
        if event.type != "uart.line":
            return False
        contains = detail.get("contains")
        return contains is None or contains in event.payload.get("text", "")
    raise ValueError(f"no match of kind {kind!r}")


def _seconds(nanoseconds: int) -> Decimal:
    return Decimal(nanoseconds) / _NS


def _after_end(record: RunRecord, since_ns: int = 0) -> Quantity:
    """Not observed before the run's end: the half-open range after it."""
    return Quantity.range(_seconds(record.end_ns - since_ns), INFINITY, "s")


def withdrawals(record: RunRecord, plan: EmulationPlan) -> dict[str, str]:
    """Sources whose model warned of something its descriptor does not expect."""
    patterns = [re.compile(w["pattern"]) for w in plan.expected_warnings]
    withdrawn: dict[str, str] = {}
    for event in record.events:
        if event.type != "model.warning":
            continue
        text = event.payload.get("text", "")
        if any(p.search(text) for p in patterns):
            continue
        withdrawn.setdefault(event.source, text)
    return withdrawn


def coverage_gaps_observed(record: RunRecord, plan: EmulationPlan) -> tuple[str, ...]:
    """The expected warnings that occurred, as the coverage gaps they stand for."""
    gaps = set()
    for event in record.events:
        if event.type != "model.warning":
            continue
        for warning in plan.expected_warnings:
            if re.search(warning["pattern"], event.payload.get("text", "")):
                gaps.add(warning["gap"])
    return tuple(sorted(gaps))


def measure(plan: EmulationPlan, record: RunRecord) -> tuple[Measured, ...]:
    """Every measure the plan declares, over one run's record."""
    if not record.completed:
        reason = (
            "the run ended on a timeout" if record.outcome == "timeout" else "the run did not complete"
        )
        return tuple(Measured(name, None, reason) for name in sorted(plan.measures))
    withdrawn = withdrawals(record, plan)
    out = []
    for name in sorted(plan.measures):
        spec = plan.measures[name]
        sources = {m["entity"] for m in spec.get("matches", ())}
        for source in list(sources):
            bus = plan.bus_of(source)
            if bus is not None:
                sources.add(bus.port)
        warned = sorted(s for s in sources if s in withdrawn)
        if warned:
            out.append(Measured(name, None, f"withdrawn: {warned[0]} warned: {withdrawn[warned[0]]}"))
            continue
        out.append(_measure_one(name, spec, plan, record))
    return tuple(out)


def _measure_one(name: str, spec: Mapping[str, Any], plan: EmulationPlan, record: RunRecord) -> Measured:
    kind = spec["kind"]
    events = record.events
    if kind == "first_at":
        match = spec["matches"][0]
        hit = next((e for e in events if _matches(e, match)), None)
        if hit is None:
            return Measured(name, _after_end(record))
        return Measured(name, Quantity.scalar(_seconds(hit.t_ns), "s"))
    if kind == "count":
        match = spec["matches"][0]
        window = spec.get("within_ns")
        if window is None:
            count = sum(1 for e in events if _matches(e, match))
            return Measured(name, Quantity.scalar(count, "1"))
        start, end = window
        count = sum(1 for e in events if _matches(e, match) and start <= e.t_ns < end)
        if end > record.end_ns:
            # The window reaches past the run's end, so what was seen is a lower
            # bound: more could have followed.
            return Measured(name, Quantity.range(count, INFINITY, "1"))
        return Measured(name, Quantity.scalar(count, "1"))
    if kind == "latency":
        start_match, end_match = spec["matches"]
        first = next((e for e in events if _matches(e, start_match)), None)
        if first is None:
            return Measured(name, None, "the event it is measured from did not occur")
        after = next((e for e in events if e.t_ns >= first.t_ns and e.seq > first.seq and _matches(e, end_match)), None)
        if after is None:
            return Measured(name, _after_end(record, first.t_ns))
        return Measured(name, Quantity.scalar(_seconds(after.t_ns - first.t_ns), "s"))
    if kind == "uart_value":
        uart = spec["entity"]
        prefix = spec["prefix"]
        for event in events:
            if event.type != "uart.line" or event.source != uart:
                continue
            text = event.payload.get("text", "")
            if text.startswith(prefix):
                number = re.match(r"-?\d+(\.\d+)?", text[len(prefix):])
                if number is None:
                    return Measured(name, None, f"the line {text!r} carries no number after {prefix!r}", True)
                return Measured(name, Quantity.scalar(Decimal(number.group(0)), spec["unit"]), None, True)
        return Measured(name, None, f"no line beginning {prefix!r} was printed before the run's end", True)
    if kind == "pin_config":
        return Measured(name, Quantity.scalar(pin_mismatches(plan, record, spec["entity"]), "1"))
    raise ValueError(f"no measure of kind {kind!r}")


_MODE_ALTERNATE = 0b10


def _selector_number(selector: str | None) -> int | None:
    if selector is None:
        return None
    found = re.fullmatch(r"AF(\d+)", selector)
    return int(found.group(1)) if found else None


def register_values(plan: EmulationPlan, record: RunRecord) -> dict[tuple[str, str], int]:
    """Each watched register's final value: read back where the model stores it,
    otherwise the firmware's last write to it, otherwise its reset value."""
    values: dict[tuple[str, str], int] = {}
    written: dict[tuple[str, str], int] = {}
    read_back: dict[tuple[str, str], int] = {}
    for event in record.events:
        if event.type not in ("register.write", "register.snapshot"):
            continue
        key = (event.payload["peripheral"], event.payload["register"])
        value = int(event.payload["value"], 16)
        (written if event.type == "register.write" else read_back)[key] = value
    for register in plan.registers:
        key = (register.peripheral, register.register)
        if register.stored and key in read_back:
            values[key] = read_back[key]
        elif key in written:
            values[key] = written[key]
        else:
            values[key] = register.reset
    return values


def pin_mismatches(plan: EmulationPlan, record: RunRecord, port: str) -> int:
    """Pins of a bus configured otherwise than the board requires: mode,
    selector, and output type, which an unstored register gives only by its
    writes."""
    values = register_values(plan, record)
    wrong = 0
    for bus in plan.buses:
        if bus.port != port:
            continue
        for pin in bus.pins:
            mode = (values.get((pin.port, "MODER"), 0) >> (2 * pin.index)) & 0b11
            afr = "AFRL" if pin.index < 8 else "AFRH"
            af = (values.get((pin.port, afr), 0) >> (4 * (pin.index % 8))) & 0xF
            otype = (values.get((pin.port, "OTYPER"), 0) >> pin.index) & 1
            expected_af = _selector_number(pin.selector)
            if (
                mode != _MODE_ALTERNATE
                or (expected_af is not None and af != expected_af)
                or otype != (1 if pin.open_drain else 0)
            ):
                wrong += 1
    return wrong
