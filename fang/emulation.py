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

from .provenance import Provenance
from .serialization import content_hash
from .traits import Trait
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


# --------------------------------------------------------------------------
# Bindings
# --------------------------------------------------------------------------


@dataclass
class EmulationModel(Trait):
    """A component's emulation model: the descriptor fang ships for it.

    Its own protocol rather than `Simulatable`'s, because the trait registry
    holds one trait per protocol for an entity, so a part could otherwise not
    carry a SPICE model and an emulation model at once, and the SPICE plan
    would read an emulation model as one it cannot use.
    """

    protocol = "emulation_model"
    source: str = ""
    provenance: Provenance = field(default_factory=Provenance)


@dataclass
class Firmware(Trait):
    """The firmware a component runs: a file relative to the project root, and
    the target it was built for. Its digest is never part of the snapshot;
    each run records it on its evidence."""

    protocol = "firmware"
    path: str = ""
    target: str = ""


# --------------------------------------------------------------------------
# Compiling a question into a plan
# --------------------------------------------------------------------------

_PROBE = re.compile(r"[^A-Za-z0-9_]")


def _probe_name(text: str) -> str:
    """A Renode identifier for a probe. Prefixed so it can never redefine one of
    the platform's own peripherals, whose names share the namespace."""
    return "fang_" + _PROBE.sub("_", text)


def _refuse(message: str, code: str) -> EmulationError:
    return EmulationError(message, code=code)


def _quantity_from(payload: Mapping[str, Any]) -> Quantity:
    return Quantity.from_dict(payload) if hasattr(Quantity, "from_dict") else _rebuild_quantity(payload)


def _rebuild_quantity(payload: Mapping[str, Any]) -> Quantity:
    kind = payload.get("kind", "scalar")
    unit = payload["unit"]
    if kind == "scalar":
        return Quantity.scalar(Decimal(payload["value"]), unit)
    if kind == "range":
        return Quantity.range(Decimal(payload["min"]), Decimal(payload["max"]), unit)
    raise EmulationError(f"a {kind} quantity cannot be used here", code="quantity")


def _nanoseconds(quantity: Quantity) -> int:
    low, high = quantity.interval()
    if low != high:
        raise _refuse(f"a time in a scenario is one instant, not {quantity}", "quantity")
    return int((Decimal(low) * _NS).to_integral_value())


def compile_plan(snapshot, question, *, traits) -> EmulationPlan:
    """An emulation question as a plan, or a refusal naming what is missing.

    `question` carries `id`, `verifies` and `data`, the canonical question
    dictionary its declaration stored. Everything else comes from the snapshot
    and the traits: the target and its firmware, the scope, every bus with its
    controller, pins, selectors and addresses, every observation point, and
    every stimulus and fault checked against the model it names. Nothing is
    defaulted, and no part falls back to a generic model.
    """
    from collections import defaultdict

    from .compatibility import resolve_address
    from .entities import Component, Connection, Interface, Pin, Port
    from .interfaces import CATALOGUE
    from .netlist import infer_nets

    entities = snapshot.entities
    data = question.data
    scenario = data.get("scenario", {})
    surfaces = data.get("surfaces", {})

    # -- the target --------------------------------------------------------
    platforms = []
    for entity_id in traits.entities_with("emulation_model"):
        model = descriptor(traits.get(entity_id, "emulation_model").source)
        if model.kind == "renode_platform":
            platforms.append(entity_id)
    bound = set(traits.entities_with("firmware"))
    candidates = [p for p in platforms if p in bound] or platforms
    if not candidates:
        raise _refuse("no component carries a platform emulation model to run firmware on", "target")
    if len(candidates) > 1:
        raise _refuse(
            "more than one component carries a platform emulation model and firmware: "
            + ", ".join(sorted(candidates)),
            "target",
        )
    target = candidates[0]
    platform = descriptor(traits.get(target, "emulation_model").source)
    binding = traits.get(target, "firmware")
    firmware_path = scenario.get("firmware") or (binding.path if binding else None)
    if not firmware_path:
        raise _refuse(f"no firmware is bound to {_path(entities, target)} and the question names none", "firmware")
    firmware_target = binding.target if binding else platform.document["target"]
    if firmware_target != platform.document["target"]:
        raise _refuse(
            f"the firmware was built for {firmware_target!r} and the platform model "
            f"describes {platform.document['target']!r}",
            "firmware",
        )

    # -- the graph, indexed -------------------------------------------------
    pins = {e.id: e for e in entities.values() if isinstance(e, Pin)}
    ports = {e.id: e for e in entities.values() if isinstance(e, Port)}
    interfaces = {e.id: e for e in entities.values() if isinstance(e, Interface)}
    connections = sorted((e for e in entities.values() if isinstance(e, Connection)), key=lambda c: c.id)
    lowered: dict[str, list] = defaultdict(list)
    for connection in connections:
        if connection.derived_from_interface:
            lowered[connection.derived_from_interface].append(connection)
    port_links = [c for c in connections if c.source in ports and c.target in ports]

    def interface_type(port):
        entity = interfaces.get(port.interface)
        return entity.interface_type if entity is not None else ""

    def target_pin(connection) -> str | None:
        for end in (connection.source, connection.target):
            pin = pins.get(end)
            if pin is not None and pin.owner == target:
                return end
        return None

    def mapped(pin_id: str) -> tuple[str, int]:
        vendor = pins[pin_id].vendor_name
        where = platform.document["pins"].get(vendor)
        if where is None:
            raise _refuse(
                f"the platform model maps no emulator pin for {vendor}; a port is never "
                "derived from a pin's name or pad number",
                "pin",
            )
        return where["port"], int(where["index"])

    def lowered_target_pins(port_id: str) -> list[tuple[str, str]]:
        found = []
        for link in port_links:
            if port_id not in (link.source, link.target):
                continue
            for connection in lowered.get(link.id, ()):
                pin = target_pin(connection)
                if pin is not None:
                    found.append((pin, str(connection.identity.path).rsplit(".", 1)[-1]))
        return found

    abstracted = {entry["component"]: entry["name"] for entry in data.get("abstracted", ())}

    # -- what the question names --------------------------------------------
    records = {entry["name"]: entry for entry in data.get("measures", ())}
    devices_named: set[str] = set()
    signal_surfaces: dict[str, str] = {}
    uart_surfaces: dict[str, str] = {}
    bus_ports_named: set[str] = set()

    def resolved(name: str) -> Mapping[str, Any]:
        found = surfaces.get(name)
        if found is None:
            raise _refuse(f"the question names {name!r}, which was not resolved", "surface")
        return found

    def note_match(match: Mapping[str, Any]) -> None:
        where = resolved(match["surface"])
        if match["kind"] in ("i2c.read", "i2c.write"):
            devices_named.add(where["component"])
        elif match["kind"] in ("gpio.rise", "gpio.fall"):
            signal_surfaces[match["surface"]] = where["port"]
        elif match["kind"] == "uart.line":
            uart_surfaces[match["surface"]] = where["port"]

    for entry in records.values():
        record = entry["measure"]
        kind = record["kind"]
        if kind in ("emulation.first_at", "emulation.count"):
            note_match(record["match"])
        elif kind == "emulation.latency":
            note_match(record["from"])
            note_match(record["to"])
        elif kind == "emulation.uart_value":
            uart_surfaces[record["surface"]] = resolved(record["surface"])["port"]
        elif kind == "emulation.pin_config":
            bus_ports_named.add(resolved(record["surface"])["port"])
        else:
            raise _refuse(f"{entry['name']} is measured by {kind!r}, which no emulation measure is", "measure")
    for stimulus in scenario.get("stimuli", ()):
        devices_named.add(resolved(stimulus["surface"])["component"])
    absent = set()
    declared_faults: list[tuple[str, str]] = []
    for fault in scenario.get("faults", ()):
        component = resolved(fault["surface"])["component"]
        devices_named.add(component)
        declared_faults.append((component, fault["kind"]))
        if fault["kind"] == "absent":
            absent.add(component)

    # -- buses ---------------------------------------------------------------
    buses: list[PlanBus] = []
    models: list[dict] = [_model_record(target, platform)]
    device_descriptors: dict[str, Descriptor] = {}
    for port in sorted((p for p in ports.values() if p.owner == target), key=lambda p: p.id):
        if interface_type(port) != "i2c":
            continue
        peers = []
        for link in port_links:
            if port.id not in (link.source, link.target):
                continue
            other = ports[link.target if link.source == port.id else link.source]
            if other.owner != target and interface_type(other) == "i2c":
                peers.append((link, other))
        if not peers:
            continue
        on_bus = {other.owner for _, other in peers}
        if not (on_bus & devices_named) and port.id not in bus_ports_named:
            continue
        if not port.peripheral:
            raise _refuse(f"{_path(entities, port.id)} names no peripheral instance", "bus")
        emulator = platform.document["peripherals"].get(port.peripheral)
        if emulator is None:
            raise _refuse(f"the platform model has no {port.peripheral}", "bus")
        spec = CATALOGUE.get("i2c")
        plan_pins: dict[str, PlanPin] = {}
        for link, _ in peers:
            for connection in lowered.get(link.id, ()):
                pin = target_pin(connection)
                if pin is None or pin in plan_pins:
                    continue
                signal = str(connection.identity.path).rsplit(".", 1)[-1]
                emulator_port, index = mapped(pin)
                selector = connection.selectors.get(pin, {}).get("selector")
                plan_pins[pin] = PlanPin(
                    pin, pins[pin].vendor_name, signal, selector,
                    spec.signal(signal).open_drain, emulator_port, index,
                )
        plan_devices = []
        for _, other in sorted(peers, key=lambda pair: pair[1].owner):
            component = other.owner
            trait = traits.get(component, "emulation_model")
            if trait is None:
                if component in abstracted:
                    continue
                raise _refuse(
                    f"{_path(entities, component)} is on {port.peripheral} with no emulation "
                    "model and is not listed as abstracted",
                    "scope",
                )
            model = descriptor(trait.source)
            device_descriptors[component] = model
            address = resolve_address(snapshot, other)
            if address is None or not address.known or address.quantity is None:
                reason = getattr(address, "rationale", None) or "it declares no address"
                raise _refuse(f"the address of {_path(entities, component)} is not known: {reason}", "address")
            low, high = address.quantity.interval()
            if low != high:
                raise _refuse(f"the address of {_path(entities, component)} is a range", "address")
            plan_devices.append(
                PlanDevice(component, _probe_name(_path(entities, component).rsplit(".", 1)[-1]),
                           model.id, model.document["renode_type"], int(low), component in absent)
            )
            models.append(_model_record(component, model))
        buses.append(PlanBus(port.id, port.peripheral, emulator,
                             tuple(plan_pins[p] for p in sorted(plan_pins, key=lambda p: pins[p].vendor_name)),
                             tuple(plan_devices)))

    on_a_bus = {d.component for b in buses for d in b.devices}
    for component in sorted(devices_named - on_a_bus):
        raise _refuse(f"the question names {_path(entities, component)}, which is on no bus the plan reaches", "scope")
    for component, kind in sorted(declared_faults):
        model = device_descriptors.get(component)
        if model is None or kind not in model.faults:
            raise _refuse(
                f"the model of {_path(entities, component)} does not support the fault {kind!r}; "
                "one fault mechanism never stands in for another",
                "fault",
            )

    # -- observations --------------------------------------------------------
    observations: list[PlanObservation] = []
    touched: set[str] = {p.pin for b in buses for p in b.pins}
    for surface, port_id in sorted(signal_surfaces.items()):
        found = lowered_target_pins(port_id)
        if len(found) != 1:
            raise _refuse(f"{surface} lands on {len(found)} pins of the target; an edge is observed on one", "surface")
        pin, _ = found[0]
        emulator_port, index = mapped(pin)
        touched.add(pin)
        observations.append(PlanObservation(_probe_name(surface), "gpio", port_id, surface, emulator_port, index))
    for surface, port_id in sorted(uart_surfaces.items()):
        port = ports[port_id]
        emulator = platform.document["peripherals"].get(port.peripheral or "")
        if emulator is None:
            raise _refuse(f"{surface} names no UART the platform model has", "surface")
        touched.update(pin for pin, _ in lowered_target_pins(port_id))
        observations.append(PlanObservation(_probe_name(surface), "uart", port_id, surface, emulator))

    # -- the scope -----------------------------------------------------------
    modelled = set(traits.entities_with("emulation_model"))
    in_scope: set[str] = set()
    for net in infer_nets(entities):
        if not touched & set(net):
            continue
        for pin in net:
            owner = pins[pin].owner if pin in pins else None
            if owner and owner != target:
                in_scope.add(owner)
    for component in sorted(in_scope):
        if component not in modelled and component not in abstracted:
            raise _refuse(
                f"{_path(entities, component)} shares a net with a pin the question touches, "
                "carries no emulation model, and is not listed as abstracted",
                "scope",
            )

    # -- registers, watches, stimuli -----------------------------------------
    registers: dict[tuple[str, str], PlanRegister] = {}
    for bus in buses:
        for pin in bus.pins:
            table = platform.document["gpio"][pin.port]
            names = ("MODER", "OTYPER", "AFRL" if pin.index < 8 else "AFRH")
            for name in names:
                entry = table["registers"][name]
                registers[(pin.port, name)] = PlanRegister(
                    target, pin.port, name, int(table["base"], 16) + int(entry["offset"], 16),
                    int(entry["reset"], 16), bool(entry["stored"]),
                )
    watched = tuple(PlanWatch(_probe_name(f"{b.emulator}_warnings"), b.emulator, b.port) for b in buses)

    stimuli = []
    assumptions = [f"the core runs at {platform.document['core_clock_hz']} Hz, as the platform model assumes"]
    for stimulus in scenario.get("stimuli", ()):
        component = resolved(stimulus["surface"])["component"]
        model = device_descriptors.get(component)
        name = stimulus["input"]
        if model is None or name not in model.inputs:
            raise _refuse(f"the model of {_path(entities, component)} accepts no input {name!r}", "stimulus")
        quantity = _quantity_from(stimulus["quantity"])
        try:
            converted, _ = quantity.converted_to(model.inputs[name]["unit"])
        except Exception as exc:
            raise _refuse(
                f"{stimulus['surface']}.{name} takes {model.inputs[name]['unit']}, not {quantity}", "stimulus"
            ) from exc
        device = next(d for b in buses for d in b.devices if d.component == component)
        at = _nanoseconds(_quantity_from(stimulus["at"]))
        stimuli.append(PlanStimulus(at, component, device.probe, name, model.inputs[name]["property"],
                                    format(converted.value.normalize(), "f"), model.inputs[name]["unit"]))
        assumptions.append(f"{stimulus['surface']}.{name} is {quantity} from {_quantity_from(stimulus['at'])}")

    if "run_until" not in scenario:
        raise _refuse("the question names no run duration, and none is assumed", "duration")
    run_until_ns = _nanoseconds(_quantity_from(scenario["run_until"]))

    # -- measures ------------------------------------------------------------
    def match_record(match: Mapping[str, Any]) -> dict:
        where = resolved(match["surface"])
        entity = where["component"] if match["kind"] in ("i2c.read", "i2c.write") else where["port"]
        out = {"kind": match["kind"], "entity": entity}
        if match.get("detail"):
            out["detail"] = dict(match["detail"])
        return out

    measures: dict[str, dict] = {}
    for name, entry in sorted(records.items()):
        record = entry["measure"]
        kind = record["kind"].removeprefix("emulation.")
        if kind in ("first_at", "count"):
            out = {"kind": kind, "matches": [match_record(record["match"])]}
            if record.get("within_ns"):
                out["within_ns"] = list(record["within_ns"])
        elif kind == "latency":
            out = {"kind": kind, "matches": [match_record(record["from"]), match_record(record["to"])]}
        elif kind == "uart_value":
            out = {"kind": kind, "entity": resolved(record["surface"])["port"],
                   "prefix": record["prefix"], "unit": record["unit"]}
        else:
            out = {"kind": kind, "entity": resolved(record["surface"])["port"]}
        measures[name] = out

    gaps = set(platform.not_modelled)
    expected = list(platform.expected_warnings)
    for model in device_descriptors.values():
        gaps.update(model.not_modelled)
        expected.extend(model.expected_warnings)
    for component, name in abstracted.items():
        gaps.add(f"{name} is abstracted, not modelled")

    return EmulationPlan(
        question=question.id,
        requirement=question.verifies,
        snapshot=snapshot.hash,
        machine="board",
        platform=platform.id,
        platform_file=platform.document["platform_file"],
        recorder_port=platform.document["recorder_port"],
        target=target,
        firmware_path=firmware_path,
        firmware_target=firmware_target,
        core_clock_hz=int(platform.document["core_clock_hz"]),
        seed=int(scenario.get("seed", 0)),
        run_until_ns=run_until_ns,
        buses=tuple(buses),
        observations=tuple(observations),
        watched=watched,
        registers=tuple(registers[k] for k in sorted(registers)),
        stimuli=tuple(stimuli),
        faults=tuple({"kind": f["kind"], "component": resolved(f["surface"])["component"]}
                     for f in scenario.get("faults", ())),
        measures=measures,
        models=tuple(sorted(models, key=lambda m: m["component"])),
        abstracted=tuple(sorted(abstracted.values())),
        assumptions=tuple(assumptions),
        coverage_gaps=tuple(sorted(gaps)),
        expected_warnings=tuple(expected),
    )


def _path(entities, entity_id: str) -> str:
    entity = entities.get(entity_id)
    path = getattr(getattr(entity, "identity", None), "path", None)
    return str(path) if path is not None else entity_id


def _model_record(component: str, model: Descriptor) -> dict:
    return {
        "component": component,
        "descriptor": model.id,
        "qualification": model.qualification,
        "provenance": dict(model.provenance),
    }
