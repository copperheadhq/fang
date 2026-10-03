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
from typing import Any, ClassVar, Mapping, Sequence

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
    def engine(self) -> str:
        """The emulator that runs this model: a question on it runs there."""
        return self.document["engine"]

    @property
    def is_platform(self) -> bool:
        """Whether this is a platform model, one firmware runs on."""
        return self.kind.endswith("_platform")

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


#: The packages whose `models/` hold the descriptors each emulator runs.
ENGINE_PACKAGES = ("fang.renode", "fang.simavr")


@lru_cache(maxsize=1)
def descriptors() -> Mapping[str, Descriptor]:
    """Every descriptor fang ships, by its id, from every engine's package."""
    return read_descriptors(resources.files(p).joinpath("models") for p in ENGINE_PACKAGES)


def read_descriptors(folders) -> dict[str, Descriptor]:
    """The descriptors in `folders`, refusing an id shipped twice: a model
    named by its id must name one model, whichever package it came from."""
    found: dict[str, Descriptor] = {}
    for folder in folders:
        for entry in sorted(folder.iterdir(), key=lambda e: e.name):
            if not entry.name.endswith(".json"):
                continue
            document = json.loads(entry.read_text(encoding="utf-8"))
            if document["id"] in found:
                raise EmulationError(
                    f"two emulation model descriptors are shipped as {document['id']!r}; "
                    "a model is named by its id, so the id names one",
                    code="model",
                )
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


#: The schema a plan is written in. v2 dropped the snapshot from the plan
#: (it changed with every unrelated design change, and the plan is hashed into
#: the job); a consumer of v1 refuses a v2 plan by this label instead of failing
#: on the missing field.
PLAN_SCHEMA = "fang.emulation/v2"

#: The schema of a plan that carries a clock, which v3 added for a part whose
#: fuses set it. A plan is written in the oldest schema that carries it, so a
#: plan with no clock is v2, byte for byte and hash for hash as before, and a
#: v2 consumer refuses a v3 plan by its label rather than run it at the wrong
#: clock.
CLOCKED_PLAN_SCHEMA = "fang.emulation/v3"
READABLE_PLAN_SCHEMAS = frozenset({"fang.emulation/v1", PLAN_SCHEMA, CLOCKED_PLAN_SCHEMA})


@dataclass(frozen=True)
class EmulationPlan:
    """An emulation question compiled against a snapshot, with every reference
    resolved. Canonical, and identified by the hash of its canonical form; the
    snapshot hash is held beside it and is not part of that identity, nor of
    its canonical form, so no file of a run's bundle carries it."""

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
    #: The clock, for a part whose fuses set it: the oscillator, the prescaler
    #: the fuses set at reset, the fuses and where they came from, and the
    #: register through which the firmware may change the prescaler. None for
    #: a platform model that assumes one clock.
    clock: Mapping[str, Any] | None = None
    #: The schema the plan was written in: the current one for a plan fang
    #: compiles, and whatever a bundle's plan says for one read back, so a
    #: v1 plan keeps the identity and hash it was written with.
    schema: str = PLAN_SCHEMA

    def identity(self) -> dict:
        """The plan without the snapshot hash: what its identity covers."""
        return {
            "schema": self.schema,
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
        } | ({"clock": dict(self.clock)} if self.clock is not None else {})

    @property
    def hash(self) -> str:
        return content_hash(self.identity())

    def as_dict(self) -> dict:
        """The plan as its bundle carries it: its identity and its hash.

        The snapshot hash is left out. It covers every entity and the
        checkout's path, so a bundle carrying it would change with any
        unrelated edit, and the job hashed over the bundle with it (RFC 12
        section 12.8 keeps the snapshot's own hash out of a job's identity).
        The job names its snapshot beside its hash, as `Job.snapshot`.
        """
        out = self.identity()
        out["plan"] = self.hash
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
    """A read of a device, matched by the device alone. The probes record a
    read's bytes and not the register it follows, so a plan refuses a match
    that names one rather than counting every read as that register's."""
    return Match("i2c.read", device, {"register": register} if register is not None else {})


def I2CWrite(device: str, data: Sequence[int] | None = None) -> Match:
    return Match("i2c.write", device, {"data": list(data)} if data is not None else {})


def Rises(surface: str) -> Match:
    return Match("gpio.rise", surface)


def Falls(surface: str) -> Match:
    return Match("gpio.fall", surface)


def UartLine(uart: str, contains: str | None = None) -> Match:
    return Match("uart.line", uart, {"contains": contains} if contains is not None else {})


#: The details each kind of match is filtered by. A detail outside these
#: would be carried into the plan and read by nothing, so the match would
#: count every event of its kind; the plan refuses it instead.
_DETAILS: Mapping[str, frozenset[str]] = {
    "i2c.read": frozenset(),
    "i2c.write": frozenset({"data"}),
    "gpio.rise": frozenset(),
    "gpio.fall": frozenset(),
    "uart.line": frozenset({"contains"}),
}


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


def _expected_of(plan: EmulationPlan, source: str) -> tuple[Mapping[str, str], ...]:
    """The warnings expected of the model that raised one recorded under
    `source`: a device's probe records its own model's warnings under the
    device, and every other source is a peripheral of the platform, watched
    under its bus. Another descriptor's patterns never excuse a warning, and
    an entry naming no descriptor is expected of none."""
    device = plan.device(source)
    model = device.model if device is not None else plan.platform
    return tuple(w for w in plan.expected_warnings if w.get("model") == model)


def _expected_matches(plan: EmulationPlan, event: Event) -> tuple[Mapping[str, str], ...]:
    text = event.payload.get("text", "")
    return tuple(w for w in _expected_of(plan, event.source) if re.search(w["pattern"], text))


def withdrawals(record: RunRecord, plan: EmulationPlan) -> dict[str, str]:
    """Sources whose model warned of something its descriptor does not expect."""
    withdrawn: dict[str, str] = {}
    for event in record.events:
        if event.type != "model.warning" or _expected_matches(plan, event):
            continue
        withdrawn.setdefault(event.source, event.payload.get("text", ""))
    return withdrawn


def coverage_gaps_observed(record: RunRecord, plan: EmulationPlan) -> tuple[str, ...]:
    """The expected warnings that occurred, as the coverage gaps they stand for."""
    gaps = set()
    for event in record.events:
        if event.type != "model.warning":
            continue
        gaps.update(warning["gap"] for warning in _expected_matches(plan, event))
    return tuple(sorted(gaps))


def measure(plan: EmulationPlan, record: RunRecord) -> tuple[Measured, ...]:
    """Every measure the plan declares, over one run's record."""
    if not record.completed:
        reason = (
            "the run ended on a timeout" if record.outcome == "timeout" else "the run did not complete"
        )
        return tuple(Measured(name, None, reason) for name in sorted(plan.measures))
    withdrawn = withdrawals(record, plan)
    if plan.target in withdrawn:
        # Everything the run observed rests on the platform model, so a warning
        # it does not expect withdraws every measure, whichever pin it is over.
        reason = f"withdrawn: {plan.target} warned: {withdrawn[plan.target]}"
        return tuple(Measured(name, None, reason) for name in sorted(plan.measures))
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


def _duty(spec: Mapping[str, Any], record: RunRecord) -> Quantity:
    """The fraction of a window a pin spent at a level, decided only over the
    part of the window the run observed.

    A pin's history is its `gpio.edge` events, each the level it was driven
    to, and its `gpio.release` events, after which it is driven to neither.
    Before its first event nothing says what it did, and after the run's end
    nothing could, so those parts of the window are unobserved, and the
    measure is the interval every level they could have held spans: a scalar
    where the whole window was observed.
    """
    start, end = (int(bound) for bound in spec["within_ns"])
    level, entity = int(spec["level"]), spec["entity"]
    run_end = record.end_ns
    changes = [
        (event.t_ns, event.payload.get("level") if event.type == "gpio.edge" else None)
        for event in record.events
        if event.source == entity and event.type in ("gpio.edge", "gpio.release")
    ]

    def overlap(a: int, b: int) -> int:
        return max(0, min(b, end) - max(a, start))

    held = sum(
        overlap(t, until)
        for (t, state), (until, _) in zip(changes, changes[1:] + [(run_end, None)])
        if state == level
    )
    first = changes[0][0] if changes else run_end
    unobserved = overlap(start, first) + overlap(max(run_end, start), end)
    length = Decimal(end - start)
    if not unobserved:
        return Quantity.scalar(Decimal(held) / length, "1")
    return Quantity.range(Decimal(held) / length, Decimal(held + unobserved) / length, "1")


def _measure_one(name: str, spec: Mapping[str, Any], plan: EmulationPlan, record: RunRecord) -> Measured:
    kind = spec["kind"]
    events = record.events
    if kind == "duty":
        return Measured(name, _duty(spec, record))
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
                # The whole token or nothing: `1.2e3` read as `1.2` would be a
                # wrong value, not a missing one, so a number is read with its
                # exponent and anything numeric left after it refuses the line.
                number = re.match(r"[-+]?\d+(\.\d+)?([eE][-+]?\d+)?(?![\w.])", text[len(prefix):])
                if number is None:
                    return Measured(
                        name, None,
                        f"the line {text!r} carries no number fang reads whole after {prefix!r}",
                        True,
                    )
                return Measured(name, Quantity.scalar(Decimal(number.group(0)), spec["unit"]), None, True)
        return Measured(name, None, f"no line beginning {prefix!r} was printed before the run's end", True)
    if kind == "pin_config":
        unread = _unread_selectors(plan, spec["entity"])
        if unread:
            vendor, selector = unread[0]
            return Measured(
                name, None,
                f"the selector {selector!r} on {vendor} is not one the platform model reads, "
                "so the pin's alternate function cannot be compared",
            )
        return Measured(name, Quantity.scalar(pin_mismatches(plan, record, spec["entity"]), "1"))
    raise ValueError(f"no measure of kind {kind!r}")


_MODE_ALTERNATE = 0b10

#: How the platform's GPIO reads a selector: an alternate function, AF0 to
#: AF15, the value of the pin's four-bit field in AFRL or AFRH.
_ALTERNATE = re.compile(r"AF(\d+)")


def _selector_number(selector: str | None) -> int | None:
    """The alternate function a selector names, or None for one the platform
    does not read. A plan refuses a selector this cannot read, and a pin
    configuration over one has no value, so a pin is never let through
    unchecked."""
    if selector is None:
        return None
    found = _ALTERNATE.fullmatch(selector)
    if found is None or int(found.group(1)) > 0xF:
        return None
    return int(found.group(1))


def _unread_selectors(plan: EmulationPlan, port: str) -> list[tuple[str, str]]:
    """A bus's pins whose selector the platform does not read, with it."""
    return [
        (pin.vendor, pin.selector)
        for bus in plan.buses
        if bus.port == port
        for pin in bus.pins
        if pin.selector is not None and _selector_number(pin.selector) is None
    ]


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
    """The firmware a component runs: a file relative to the program that
    declares the part, as a SPICE model's path is, and the target it was
    built for. Its digest is never part of the snapshot; each run records it
    on its evidence."""

    protocol = "firmware"
    path: str = ""
    target: str = ""
    #: The fuses the part is programmed with, where its platform model says
    #: they set its clock: `"factory"`, or the bytes by name. A question may
    #: state its own, which win.
    fuses: Any = None

    def __post_init__(self) -> None:
        from .lang import _caller_location

        self.fuses = declared_fuses(self.fuses, location=_caller_location(3))

    def as_dict(self) -> dict:
        out = super().as_dict()
        if self.fuses is None:
            # Unstated is absent, not a value; a binding written before fuses
            # existed serializes as it always has.
            out.pop("fuses")
        return out


#: The fuse bytes of an AVR part, as a binding or a question names them.
FUSE_BYTES = ("low", "high", "extended")

#: Fuses stated as the values the part ships with, which its descriptor holds.
FACTORY = "factory"


def declared_fuses(fuses, *, location=None):
    """Fuses as a binding or a question states them, as canonical data:
    `"factory"`, or each byte named as `0xNN`; None where none are stated.

    Refused where they are declared if they are neither, name a byte no AVR
    part has, or give a value that is no byte. Which values a part's model
    covers is the plan's to decide, against its descriptor.
    """
    from .diagnostics import SIM_EMULATION_CLOCK, error

    if fuses is None or fuses == FACTORY:
        return fuses
    if not isinstance(fuses, Mapping) or not fuses:
        raise error(
            SIM_EMULATION_CLOCK,
            f"fuses are {FACTORY!r}, or the bytes {', '.join(FUSE_BYTES)} by name, not {fuses!r}",
            location=location,
        )
    stated = {}
    for name, value in fuses.items():
        if name not in FUSE_BYTES:
            raise error(
                SIM_EMULATION_CLOCK,
                f"{name!r} is no fuse byte; an AVR part's are {', '.join(FUSE_BYTES)}",
                location=location,
            )
        if isinstance(value, str) and re.fullmatch(r"0x[0-9A-Fa-f]{2}", value):
            value = int(value, 16)       # the canonical form, read back
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 0xFF:
            raise error(
                SIM_EMULATION_CLOCK,
                f"the {name} fuse is {value!r}; a fuse byte is a whole number from 0x00 to 0xFF",
                location=location,
            )
        stated[name] = f"0x{value:02X}"
    return {name: stated[name] for name in FUSE_BYTES if name in stated}


# --------------------------------------------------------------------------
# Compiling a question into a plan
# --------------------------------------------------------------------------

_PROBE = re.compile(r"[^A-Za-z0-9_]")


def _probe_name(text: str) -> str:
    """A Renode identifier for a probe, from a whole path or surface name, so
    `a.env` and `b.env` are two probes. Prefixed so it can never redefine one
    of the platform's own peripherals, whose names share the namespace. Two
    names can still meet (`a.b_c` and `a_b.c`); the lowering refuses that."""
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

    def model_of(component: str) -> Descriptor:
        """The descriptor a part's model names, or a refusal naming the part."""
        source = traits.get(component, "emulation_model").source
        try:
            return descriptor(source)
        except EmulationError:
            raise _refuse(
                f"the emulation model of {_path(entities, component)} names {source!r}, a "
                "descriptor fang does not ship; a part with no descriptor is refused rather "
                "than given a generic model",
                "model",
            ) from None

    # -- the target --------------------------------------------------------
    platforms = []
    for entity_id in sorted(traits.entities_with("emulation_model")):
        model = model_of(entity_id)
        if model.is_platform:
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
    platform = model_of(target)
    # The question was routed by the emulator it recorded at elaboration; the
    # target resolved here must be one that emulator runs. A question recorded
    # before emulators were is Renode's, as every such question was.
    recorded = data.get("engine", "renode")
    if recorded != platform.engine:
        raise _refuse(
            f"the question was recorded for {recorded}, and the platform model of "
            f"{_path(entities, target)}, {platform.id}, runs on {platform.engine}; a "
            "question runs only on the emulator its target's platform model names",
            "target",
        )
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
    # A part whose fuses set its clock runs at the clock its stated fuses give;
    # any other platform model assumes one.
    clock = None
    if "clock" in platform.document:
        clock = _resolve_clock(
            platform,
            scenario.get("fuses"),
            binding.fuses if binding else None,
            _path(entities, target),
        )
        core_clock_hz = clock["oscillator_hz"] // clock["prescaler"]
    else:
        core_clock_hz = int(platform.document["core_clock_hz"])

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
        """The target's pins a port's links lower onto, each once: a signal
        with two loads is two links onto the same pin."""
        found: dict[str, str] = {}
        for link in port_links:
            if port_id not in (link.source, link.target):
                continue
            for connection in lowered.get(link.id, ()):
                pin = target_pin(connection)
                if pin is not None:
                    found.setdefault(pin, str(connection.identity.path).rsplit(".", 1)[-1])
        return list(found.items())

    abstracted = {entry["component"]: entry["name"] for entry in data.get("abstracted", ())}

    # -- what the question names --------------------------------------------
    records = {entry["name"]: entry for entry in data.get("measures", ())}
    devices_named: set[str] = set()
    signal_surfaces: dict[str, str] = {}
    uart_surfaces: dict[str, str] = {}
    pin_config_surfaces: dict[str, str] = {}

    def resolved(name: str) -> Mapping[str, Any]:
        found = surfaces.get(name)
        if found is None:
            raise _refuse(f"the question names {name!r}, which was not resolved", "surface")
        return found

    def note_match(match: Mapping[str, Any]) -> None:
        if match["kind"] not in _DETAILS:
            raise _refuse(f"{match['kind']!r} is no kind of emulation match", "measure")
        unread = sorted(set(match.get("detail", {})) - _DETAILS[match["kind"]])
        if unread:
            raise _refuse(
                f"the {match['kind']} match on {match['surface']} names {', '.join(unread)}, "
                f"which no measure filters on: it would count every {match['kind']} on "
                f"{match['surface']}, so it is refused rather than ignored",
                "measure",
            )
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
            pin_config_surfaces[record["surface"]] = resolved(record["surface"])["port"]
        elif kind == "emulation.duty":
            # A level is held on a pin, so the surface is observed as one.
            signal_surfaces[record["surface"]] = resolved(record["surface"])["port"]
        else:
            raise _refuse(f"{entry['name']} is measured by {kind!r}, which no emulation measure is", "measure")
    for stimulus in scenario.get("stimuli", ()):
        devices_named.add(resolved(stimulus["surface"])["component"])
    bus_ports_named = set(pin_config_surfaces.values())
    absent = set()
    declared_faults: list[tuple[str, str]] = []
    for fault in scenario.get("faults", ()):
        component = resolved(fault["surface"])["component"]
        devices_named.add(component)
        declared_faults.append((component, fault["kind"]))
        if fault["kind"] == "absent":
            absent.add(component)

    # An absent device has no probe: nothing it is asked is recorded, so a
    # match over it would read the same whatever the firmware did, and a
    # stimulus on it would have nothing to set. Both are refused rather than
    # measured as an observation that cannot happen.
    for name, entry in sorted(records.items()):
        record = entry["measure"]
        if record["kind"] in ("emulation.first_at", "emulation.count"):
            matches = [record["match"]]
        elif record["kind"] == "emulation.latency":
            matches = [record["from"], record["to"]]
        else:
            matches = []
        for match in matches:
            if match["kind"] in ("i2c.read", "i2c.write") and resolved(match["surface"])["component"] in absent:
                raise _refuse(
                    f"{name} matches {match['kind']} on {match['surface']}, which the question's "
                    "fault makes absent: an absent device has no probe, so the measure would "
                    "read the same whatever the firmware did",
                    "measure",
                )
    for stimulus in scenario.get("stimuli", ()):
        if resolved(stimulus["surface"])["component"] in absent:
            raise _refuse(
                f"the stimulus on {stimulus['surface']}.{stimulus['input']} has nothing to set: "
                f"the question's fault makes {stimulus['surface']} absent",
                "stimulus",
            )

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
                if selector is not None and _selector_number(selector) is None:
                    # The pin configuration would skip the comparison it
                    # cannot make, and count a wrong mux as right.
                    raise _refuse(
                        f"the selector {selector!r} on {pins[pin].vendor_name} is not one the "
                        "platform model reads: it reads an alternate function, AF0 to AF15",
                        "pin",
                    )
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
            model = model_of(component)
            device_descriptors[component] = model
            address = resolve_address(snapshot, other)
            if address is None or not address.known or address.quantity is None:
                reason = getattr(address, "rationale", None) or "it declares no address"
                raise _refuse(f"the address of {_path(entities, component)} is not known: {reason}", "address")
            low, high = address.quantity.interval()
            if low != high:
                raise _refuse(f"the address of {_path(entities, component)} is a range", "address")
            if Decimal(low) < 0:
                raise _refuse(
                    f"the address of {_path(entities, component)} is "
                    f"{format(Decimal(low).normalize(), 'f')}; a bus address is not negative",
                    "address",
                )
            if Decimal(low) != Decimal(low).to_integral_value():
                # Made whole, the emulator would put the device at an
                # address the graph does not hold.
                raise _refuse(
                    f"the address of {_path(entities, component)} is "
                    f"{format(Decimal(low).normalize(), 'f')}, not a whole number; a device "
                    "answers on an integer address, and no other is given to the emulator "
                    "in its place",
                    "address",
                )
            plan_devices.append(
                PlanDevice(component, _probe_name(_path(entities, component)),
                           model.id, model.document["renode_type"], int(low), component in absent)
            )
            models.append(_model_record(component, model))
        buses.append(PlanBus(port.id, port.peripheral, emulator,
                             tuple(plan_pins[p] for p in sorted(plan_pins, key=lambda p: pins[p].vendor_name)),
                             tuple(plan_devices)))

    # A pin configuration is counted over a bus's pins, so a port that is no
    # bus the plan reaches, or a bus that reaches no pin of the target, would
    # measure 0 having checked nothing.
    for surface, port_id in sorted(pin_config_surfaces.items()):
        bus = next((b for b in buses if b.port == port_id), None)
        if bus is None:
            raise _refuse(
                f"PinConfig({surface!r}) names {_path(entities, port_id)}, which is no I2C "
                f"bus of {_path(entities, target)} with a device on it; a pin "
                "configuration is measured over a bus's pins",
                "bus",
            )
        if not bus.pins:
            raise _refuse(
                f"PinConfig({surface!r}) names {_path(entities, port_id)}, whose lowered "
                f"connections reach no pin of {_path(entities, target)}",
                "bus",
            )

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
    unaccounted = sorted(
        _path(entities, c) for c in in_scope if c not in modelled and c not in abstracted
    )
    if unaccounted:
        raise _refuse(
            f"{', '.join(unaccounted)}: each shares a net with a pin the question "
            "touches, carries no emulation model, and is not listed as abstracted",
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

    if "run_until" not in scenario:
        raise _refuse("the question names no run duration, and none is assumed", "duration")
    run_until = _quantity_from(scenario["run_until"])
    run_until_ns = _nanoseconds(run_until)
    if run_until_ns <= 0:
        raise _refuse(
            f"the run lasts {run_until}; a run lasts a positive time, and one of no time "
            "observes nothing",
            "duration",
        )

    stimuli = []
    assumptions = _clock_assumptions(clock) if clock is not None else [
        f"the core runs at {core_clock_hz} Hz, as the platform model assumes"
    ]
    for stimulus in scenario.get("stimuli", ()):
        component = resolved(stimulus["surface"])["component"]
        model = device_descriptors.get(component)
        name = stimulus["input"]
        if model is None or name not in model.inputs:
            raise _refuse(f"the model of {_path(entities, component)} accepts no input {name!r}", "stimulus")
        quantity = _quantity_from(stimulus["quantity"])
        if quantity.kind != "scalar":
            raise _refuse(
                f"{stimulus['surface']}.{name} is set to {quantity}, a {quantity.kind}: a "
                "stimulus sets the model's input to one value",
                "stimulus",
            )
        try:
            converted, _ = quantity.converted_to(model.inputs[name]["unit"])
        except Exception as exc:
            raise _refuse(
                f"{stimulus['surface']}.{name} takes {model.inputs[name]['unit']}, not {quantity}", "stimulus"
            ) from exc
        device = next(d for b in buses for d in b.devices if d.component == component)
        at = _nanoseconds(_quantity_from(stimulus["at"]))
        if not 0 <= at <= run_until_ns:
            raise _refuse(
                f"the stimulus on {stimulus['surface']}.{name} at {_quantity_from(stimulus['at'])} "
                f"falls outside the run, from 0 to {run_until}, so it would never be applied",
                "stimulus",
            )
        stimuli.append(PlanStimulus(at, component, device.probe, name, model.inputs[name]["property"],
                                    format(converted.value.normalize(), "f"), model.inputs[name]["unit"]))
        assumptions.append(f"{stimulus['surface']}.{name} is {quantity} from {_quantity_from(stimulus['at'])}")

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
                start, end = (int(bound) for bound in record["within_ns"])
                if not start < end:
                    raise _refuse(
                        f"{name} counts over [{start} ns, {end} ns), an empty window: "
                        "it would count 0 whatever the firmware did",
                        "measure",
                    )
                out["within_ns"] = [start, end]
        elif kind == "latency":
            out = {"kind": kind, "matches": [match_record(record["from"]), match_record(record["to"])]}
        elif kind == "uart_value":
            out = {"kind": kind, "entity": resolved(record["surface"])["port"],
                   "prefix": record["prefix"], "unit": record["unit"]}
        elif kind == "duty":
            window = record.get("within_ns") or ()
            start, end = (int(bound) for bound in window) if len(window) == 2 else (0, 0)
            if not start < end:
                raise _refuse(
                    f"{name} is a fraction of [{start} ns, {end} ns), an empty window: "
                    "it would read the same whatever the firmware did",
                    "measure",
                )
            level = record.get("level")
            if isinstance(level, bool) or level not in (0, 1):
                raise _refuse(f"{name} names the level {level!r}; a pin's level is 0 or 1", "measure")
            out = {"kind": kind, "entity": resolved(record["surface"])["port"], "level": level,
                   "within_ns": [start, end]}
        else:
            out = {"kind": kind, "entity": resolved(record["surface"])["port"]}
        measures[name] = out

    # Each expected warning names the descriptor that expects it, so a run
    # matches a warning only against its own model's patterns.
    gaps = set(platform.not_modelled)
    expected = [{"model": platform.id, **w} for w in platform.expected_warnings]
    for model in sorted({m.id: m for m in device_descriptors.values()}.values(), key=lambda m: m.id):
        gaps.update(model.not_modelled)
        expected.extend({"model": model.id, **w} for w in model.expected_warnings)
    for component, name in abstracted.items():
        gaps.add(f"{name} is abstracted, not modelled")

    return EmulationPlan(
        question=question.id,
        requirement=question.verifies,
        snapshot=snapshot.hash,
        machine="board",
        platform=platform.id,
        # A platform whose emulator records everything itself, from a program
        # built against its library, has neither a platform file nor a port
        # to hang a recorder on.
        platform_file=platform.document.get("platform_file", ""),
        recorder_port=platform.document.get("recorder_port", ""),
        target=target,
        firmware_path=firmware_path,
        firmware_target=firmware_target,
        core_clock_hz=core_clock_hz,
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
        clock=clock,
        schema=CLOCKED_PLAN_SCHEMA if clock is not None else PLAN_SCHEMA,
    )


#: Where a plan's fuses came from, as its assumptions say it.
_FUSE_SOURCES = {
    "factory": "the factory fuses, the values the part ships with",
    "binding": "the fuses the firmware binding states",
    "question": "the fuses the question states",
}


def _resolve_clock(platform: Descriptor, asked, bound, part: str) -> dict:
    """The clock a part whose fuses set it starts at, from the fuses the
    question states, else the binding's; refused, naming the fuse and the
    bits, where none are stated or the platform model does not cover them.

    A byte left out of a stated mapping is the value the part ships with. A
    bit the model does not model must be the part's shipped value, so nothing
    the fuses do is silently left out of the run. AVR fuses read 0 when
    programmed.
    """
    spec = platform.document["clock"]
    factory = {name: int(value, 16) for name, value in spec["fuses"].items()}
    stated, source = (asked, "question") if asked is not None else (bound, "binding")
    if stated is None:
        raise _refuse(
            f"the clock of {part} is set by its fuses, and neither its firmware binding nor "
            f"the question states them; state them, or {FACTORY!r} for the values the part "
            "ships with, rather than have the plan assume them",
            "clock",
        )
    fuses = dict(factory)
    if stated == FACTORY:
        source = "factory"
    else:
        for name, value in stated.items():
            if name not in factory:
                raise _refuse(
                    f"{part} has no {name} fuse; its model, {platform.id}, has "
                    f"{', '.join(sorted(factory))}",
                    "clock",
                )
            fuses[name] = int(value, 16)
    for name, value in sorted(fuses.items()):
        unmodelled = (value ^ factory[name]) & ~int(spec["modelled"][name], 16) & 0xFF
        if unmodelled:
            raise _refuse(
                f"the {name} fuse of {part} is 0x{value:02X}: bits 0x{unmodelled:02X} differ "
                f"from the 0x{factory[name]:02X} the part ships with, and {platform.id} does not "
                "model them, so the run would leave out what they do",
                "clock",
            )
    select = spec["clock_select"]
    byte = fuses[select["fuse"]]
    cksel = byte & int(select["mask"], 16)
    oscillator = select["oscillators"].get(f"0x{cksel:X}")
    if oscillator is None:
        modelled = ", ".join(sorted(select["oscillators"]))
        raise _refuse(
            f"the {select['fuse']} fuse of {part} is 0x{byte:02X}, whose clock-select bits "
            f"(CKSEL) are 0x{cksel:X}: a clock source {platform.id} does not model; it models "
            f"CKSEL {modelled}",
            "clock",
        )
    divide = spec["divide_by_8"]
    prescaler = 1 if fuses[divide["fuse"]] >> divide["bit"] & 1 else 8
    start = spec["start_up"]
    mask = int(start["mask"], 16)
    sut = (fuses[start["fuse"]] & mask) >> ((mask & -mask).bit_length() - 1)
    delay = start["delays"].get(f"0x{sut:X}")
    if delay is None:
        raise _refuse(
            f"the {start['fuse']} fuse of {part} is 0x{fuses[start['fuse']]:02X}, whose "
            f"start-up bits (SUT) are 0x{sut:X}, which the part reserves",
            "clock",
        )
    return {
        "oscillator_hz": int(oscillator),
        "prescaler": prescaler,
        "fuses": {name: f"0x{fuses[name]:02X}" for name in FUSE_BYTES if name in fuses},
        "source": source,
        "start_up": delay,
        "prescaler_register": spec["prescaler_register"],
    }


def _clock_assumptions(clock: Mapping[str, Any]) -> list[str]:
    fuses = ", ".join(f"{name} {value}" for name, value in clock["fuses"].items())
    hz = clock["oscillator_hz"] // clock["prescaler"]
    return [
        f"the core starts at {hz} Hz: the {clock['oscillator_hz']} Hz oscillator divided "
        f"by {clock['prescaler']}, from {_FUSE_SOURCES[clock['source']]} ({fuses})",
        "the oscillator runs at its nominal frequency; its calibration and tolerance are "
        "not modelled",
        f"time zero is the first instruction; the part starts {clock['start_up']} after "
        "reset, which the run does not model",
    ]


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


# --------------------------------------------------------------------------
# Declaring an emulation question
# --------------------------------------------------------------------------

from .diagnostics import (  # noqa: E402 - the question layer sits on the plan above
    SIM_EMULATION_BUS,
    SIM_EMULATION_CLOCK,
    SIM_EMULATION_DURATION,
    SIM_EMULATION_FAULT,
    SIM_EMULATION_FIRMWARE,
    SIM_EMULATION_MODEL,
    SIM_EMULATION_PIN,
    SIM_EMULATION_SCOPE,
    SIM_EMULATION_STIMULUS,
    SIM_UNRESOLVED_SURFACE,
    UNIT_DIMENSION_MISMATCH,
    error,
)
from .lang import _caller_location  # noqa: E402
from .runtime import Status  # noqa: E402
from .simulation import Level  # noqa: E402
from .units import Unit  # noqa: E402
from .verification import (  # noqa: E402
    _NO_RESULT,
    MODEL_CONFIDENCE,
    Job,
    Measure,
    Measurement,
    NotRunnable,
    Question,
    QuestionDeclaration,
    RawRun,
    ToolUnavailable,
    _walk,
    register_method,
    register_tool,
)

_TIME = Unit.parse("s").dimension
_DIMENSIONLESS = Unit.parse("1").dimension

#: The plan's refusal reasons, as the diagnostic code each is reported under.
_CODES = {
    "clock": SIM_EMULATION_CLOCK,
    "model": SIM_EMULATION_MODEL,
    "scope": SIM_EMULATION_SCOPE,
    "fault": SIM_EMULATION_FAULT,
    "stimulus": SIM_EMULATION_STIMULUS,
    "pin": SIM_EMULATION_PIN,
    "duration": SIM_EMULATION_DURATION,
    "firmware": SIM_EMULATION_FIRMWARE,
    "target": SIM_EMULATION_FIRMWARE,
    "bus": SIM_EMULATION_BUS,
    "address": SIM_EMULATION_BUS,
    "surface": SIM_UNRESOLVED_SURFACE,
    "measure": SIM_UNRESOLVED_SURFACE,
    "quantity": UNIT_DIMENSION_MISMATCH,
}


def _match_from(payload: Mapping[str, Any]) -> Match:
    return Match(payload["kind"], payload["surface"], dict(payload.get("detail", {})))


@dataclass(frozen=True)
class FirstAtMeasure(Measure):
    """The virtual time of the first matching event."""

    kind = "emulation.first_at"
    match: Match | None = None

    def surfaces(self) -> tuple[str, ...]:
        return (self.match.surface,)

    def produces(self, analysis: str | None):
        return _TIME

    def fields(self) -> dict:
        return {"match": self.match.as_dict()}

    @classmethod
    def read(cls, payload: Mapping) -> "Measure":
        return cls(payload["surface"], _match_from(payload["match"]))


@dataclass(frozen=True)
class CountMeasure(Measure):
    """Matching events in a window of virtual time, or over the whole run."""

    kind = "emulation.count"
    match: Match | None = None
    within_ns: tuple[int, int] | None = None

    def surfaces(self) -> tuple[str, ...]:
        return (self.match.surface,)

    def produces(self, analysis: str | None):
        return _DIMENSIONLESS

    def fields(self) -> dict:
        out = {"match": self.match.as_dict()}
        if self.within_ns is not None:
            out["within_ns"] = list(self.within_ns)
        return out

    @classmethod
    def read(cls, payload: Mapping) -> "Measure":
        within = payload.get("within_ns")
        return cls(payload["surface"], _match_from(payload["match"]), tuple(within) if within else None)


@dataclass(frozen=True)
class DutyMeasure(Measure):
    """The fraction of a window of virtual time a pin spent at a level,
    decided only over the part of the window the run observed."""

    kind = "emulation.duty"
    level: int = 0
    within_ns: tuple[int, int] | None = None

    def produces(self, analysis: str | None):
        return _DIMENSIONLESS

    def fields(self) -> dict:
        return {"level": self.level, "within_ns": list(self.within_ns)}

    @classmethod
    def read(cls, payload: Mapping) -> "Measure":
        return cls(payload["surface"], int(payload["level"]), tuple(payload["within_ns"]))


@dataclass(frozen=True)
class LatencyMeasure(Measure):
    """The time from the first `from_` event to the first `to` event after it."""

    kind = "emulation.latency"
    from_: Match | None = None
    to: Match | None = None

    def surfaces(self) -> tuple[str, ...]:
        return (self.from_.surface, self.to.surface)

    def produces(self, analysis: str | None):
        return _TIME

    def fields(self) -> dict:
        return {"from": self.from_.as_dict(), "to": self.to.as_dict()}

    @classmethod
    def read(cls, payload: Mapping) -> "Measure":
        return cls(payload["surface"], _match_from(payload["from"]), _match_from(payload["to"]))


@dataclass(frozen=True)
class UartValueMeasure(Measure):
    """The number after `prefix` on the first line a UART carried: the
    firmware's report of a value, recorded as such."""

    kind = "emulation.uart_value"
    prefix: str = ""
    unit: str = "1"

    def produces(self, analysis: str | None):
        return Unit.parse(self.unit).dimension

    def logarithmic(self) -> bool:
        return Unit.parse(self.unit).logarithmic

    def fields(self) -> dict:
        return {"prefix": self.prefix, "unit": self.unit}

    @classmethod
    def read(cls, payload: Mapping) -> "Measure":
        return cls(payload["surface"], payload["prefix"], payload["unit"])


@dataclass(frozen=True)
class PinConfigMeasure(Measure):
    """How many of a bus's pins the firmware configured otherwise than the
    board requires."""

    kind = "emulation.pin_config"

    def produces(self, analysis: str | None):
        return _DIMENSIONLESS

    @classmethod
    def read(cls, payload: Mapping) -> "Measure":
        return cls(payload["surface"])


def FirstAt(match: Match) -> FirstAtMeasure:
    return FirstAtMeasure(match.surface, match)


def _window_ns(
    within: Sequence[Quantity] | None, location=None, *, what: str = "Count", empty: str = "count 0"
) -> tuple[int, int] | None:
    """A window as integer nanoseconds: two single times, the start before
    the end. Anything else is refused where it is declared, because an empty
    window reads the same whatever the firmware does, and a window in volts
    would be read as seconds. `what` names the measure and `empty` what an
    empty window would give it."""
    if within is None:
        return None
    bounds = tuple(within)
    if len(bounds) != 2:
        raise error(
            SIM_UNRESOLVED_SURFACE,
            f"a {what} window is a start and an end, not {len(bounds)} values",
            location=location,
        )
    for bound in bounds:
        if not isinstance(bound, Quantity) or bound.dimension != _TIME:
            raise error(
                UNIT_DIMENSION_MISMATCH,
                f"a {what} window is bounded by times, and {bound} is not one",
                location=location,
            )
        low, high = bound.interval()
        if low != high:
            raise error(
                SIM_UNRESOLVED_SURFACE, f"a {what} window's bound is one time, not {bound}", location=location
            )
    start, end = (int((Decimal(b.interval()[0]) * _NS).to_integral_value()) for b in bounds)
    if not start < end:
        raise error(
            SIM_UNRESOLVED_SURFACE,
            f"the {what} window ({bounds[0]}, {bounds[1]}) is empty: its start is not "
            f"before its end, so it would {empty} whatever the firmware did",
            location=location,
        )
    return (start, end)


def Count(match: Match, *, within: Sequence[Quantity] | None = None) -> CountMeasure:
    return CountMeasure(match.surface, match, _window_ns(within, _caller_location(2)))


def Latency(from_: Match, to: Match) -> LatencyMeasure:
    return LatencyMeasure(from_.surface, from_, to)


def UartValue(uart: str, *, prefix: str, unit: Any) -> UartValueMeasure:
    """`unit` is a unit literal, `degC`, or its symbol."""
    symbol = unit.unit.symbol if hasattr(unit, "unit") else getattr(unit, "symbol", unit)
    return UartValueMeasure(uart, prefix, str(symbol))


def PinConfig(port: str) -> PinConfigMeasure:
    return PinConfigMeasure(port)


def Duty(surface: str, *, level: int, within: Sequence[Quantity]) -> DutyMeasure:
    """The fraction of `within` the pin at `surface` spent at `level`, 0 or 1."""
    location = _caller_location(2)
    if isinstance(level, bool) or level not in (0, 1):
        raise error(
            SIM_UNRESOLVED_SURFACE, f"a pin's level is 0 or 1, not {level!r}", location=location
        )
    if within is None:
        raise error(
            SIM_UNRESOLVED_SURFACE, "a Duty is taken over a window, within=(start, end)", location=location
        )
    return DutyMeasure(surface, level, _window_ns(within, location, what="Duty", empty="read the same"))


@dataclass(frozen=True)
class At:
    """A stimulus: one of a model's inputs set at a virtual time."""

    time: Quantity
    target: str                       # "<device surface>.<input>"
    value: Quantity

    @property
    def surface(self) -> str:
        return self.target.rsplit(".", 1)[0]

    @property
    def input(self) -> str:
        return self.target.rsplit(".", 1)[1]


@dataclass(frozen=True)
class Fault:
    """A fault, named by its mechanism. A plan accepts one only where the
    device's model declares it, and never lets one mechanism stand in for
    another: a device that stops answering is not a stuck line."""

    surface: str
    kind: str


def Absent(surface: str) -> Fault:
    """The device is not on its bus, so its address goes unanswered."""
    return Fault(surface, "absent")


class Emulates(QuestionDeclaration):
    """A question answered by running the board's firmware in an emulator.

    Declared beside the requirement it serves, like `Simulates`: the run's
    virtual duration, its stimuli, its faults by mechanism, the parts it
    abstracts, and its measures over what the emulator's probes observe, each
    named by part surface; and, for a part whose fuses set its clock, the
    fuses it is programmed with, where they differ from its binding's. It
    elaborates to a verification with method `emulation`, records the
    emulator its target's platform model names, is routed at the behavioural
    level to that emulator, and cannot state its result.
    """

    fixed_method = "emulation"

    def __init__(
        self,
        verifies: str,
        *,
        measures: Mapping[str, Measure],
        run_until: Quantity | None = None,
        stimuli: Sequence[At] = (),
        faults: Sequence[Fault] = (),
        firmware: str | None = None,
        fuses: Any = None,
        seed: int = 0,
        abstracted: Sequence[str] = (),
        tool: str | None = None,
        result: object = _NO_RESULT,
    ) -> None:
        super().__init__(verifies, measures=measures, abstracted=abstracted, tool=tool, result=result)
        # Validated here, where they are written; whether the part's model
        # covers them is the plan's question.
        fuses = declared_fuses(fuses, location=self._source)
        if run_until is not None and run_until.dimension != _TIME:
            raise error(
                UNIT_DIMENSION_MISMATCH,
                f"run_until is {run_until}; a run lasts a time",
                location=self._source,
            )
        # A run of no time, or of less, would be lowered with nothing to run
        # and still end "completed", so it is refused where it is written, as
        # the plan refuses it when it compiles.
        if run_until is not None and not Decimal(run_until.interval()[0]) > 0:
            raise error(
                SIM_EMULATION_DURATION,
                f"run_until is {run_until}; a run lasts a positive time, and one of "
                "no time observes nothing",
                location=self._source,
            )
        for stimulus in stimuli:
            if stimulus.time.dimension != _TIME:
                raise error(
                    UNIT_DIMENSION_MISMATCH,
                    f"the stimulus on {stimulus.target} is at {stimulus.time}; it happens at a time",
                    location=self._source,
                )
        self.run_until = run_until
        self.stimuli = tuple(stimuli)
        self.faults = tuple(faults)
        self.firmware = firmware
        self.fuses = fuses
        self.seed = int(seed)

    def named_surfaces(self) -> tuple[str, ...]:
        return (
            super().named_surfaces()
            + tuple(s.surface for s in self.stimuli)
            + tuple(f.surface for f in self.faults)
        )

    def resolve_surface(self, module, name: str) -> dict:
        """A part names a device; a part's surface names a port or a signal.

        Both are recorded as the entities they are. Which pins they land on is
        read from the graph when the plan is compiled, so nothing about a pin
        is decided here.
        """
        owner, consumed, rest = _walk(module, name)
        if not rest:
            if not consumed or owner.entity_kind != "component":
                raise error(
                    SIM_UNRESOLVED_SURFACE,
                    f"{name!r} names no part of {type(module).__name__}",
                    location=self._source,
                )
            return {"kind": "part", "component": owner._entity_id}
        surface = owner.surfaces().get(rest[0]) if len(rest) == 1 else None
        if surface is None:
            raise error(
                SIM_UNRESOLVED_SURFACE,
                f"{name!r} names no surface of {type(owner).__name__}",
                location=self._source,
            )
        return {"kind": "surface", "component": owner._entity_id, "port": surface._entity_id}

    def measured_dimension(self, measure: Measure):
        return measure.produces(None)

    def question_fields(self, module) -> dict:
        scenario: dict = {
            "seed": self.seed,
            "stimuli": [
                {
                    "at": s.time.as_dict(),
                    "surface": s.surface,
                    "input": s.input,
                    "quantity": s.value.as_dict(),
                }
                for s in self.stimuli
            ],
            "faults": [{"kind": f.kind, "surface": f.surface} for f in self.faults],
        }
        if self.run_until is not None:
            scenario["run_until"] = self.run_until.as_dict()
        if self.firmware is not None:
            scenario["firmware"] = self.firmware
        if self.fuses is not None:
            scenario["fuses"] = self.fuses
        fields: dict = {"scenario": scenario}
        engine = _platform_engine(module)
        if engine is not None:
            fields["engine"] = engine
        return fields


def _platform_engine(module) -> str | None:
    """The emulator a module's firmware target runs on, recorded on its
    questions so that routing, which sees only the question, sends each to
    that emulator. The target is found as the plan finds it: the part whose
    platform model has a firmware binding beside it, else the one part with a
    platform model. None where no shipped platform model is found, or two name
    different emulators; the plan then refuses the question, naming why."""
    platforms: list[tuple[Any, Descriptor]] = []
    bound: set[int] = set()

    def visit(node) -> None:
        for child in node.children().values():
            for trait in child.traits:
                if isinstance(trait, EmulationModel):
                    model = descriptors().get(trait.source)
                    if model is not None and model.is_platform:
                        platforms.append((child, model))
                elif isinstance(trait, Firmware):
                    bound.add(id(child))
            visit(child)

    visit(module)
    candidates = [model for part, model in platforms if id(part) in bound] or [m for _, m in platforms]
    engines = {model.engine for model in candidates}
    return engines.pop() if len(engines) == 1 else None


# --------------------------------------------------------------------------
# The emulation tools
# --------------------------------------------------------------------------

#: A model's qualification, as the confidence a run resting on it can claim:
#: a model only tested in emulation is an inference, never an assertion.
QUALIFICATION_CONFIDENCE: Mapping[str, Decimal] = {
    "experimental": MODEL_CONFIDENCE[next(c for c in MODEL_CONFIDENCE if c.value == "unverified")],
    "tested in emulation": MODEL_CONFIDENCE[next(c for c in MODEL_CONFIDENCE if c.value == "inferred")],
    "hardware-correlated": MODEL_CONFIDENCE[next(c for c in MODEL_CONFIDENCE if c.value == "asserted")],
}


def plan_from_dict(payload: Mapping[str, Any]) -> EmulationPlan:
    """A plan read back from its canonical form, as a bundle carries it.

    v2 is v1 without the snapshot, which stopped being part of the plan so an
    unrelated design change would leave the job current; a v1 plan still reads.
    v3 is v2 with a clock, and only a plan with a clock is v3. A plan of any
    other schema is refused by its label, not misread.
    """
    schema = payload.get("schema")
    if schema not in READABLE_PLAN_SCHEMAS:
        raise ValueError(
            f"a plan of schema {schema!r} is not one fang reads "
            f"({', '.join(sorted(READABLE_PLAN_SCHEMAS))})"
        )
    clock = payload.get("clock")
    if (clock is not None) != (schema == CLOCKED_PLAN_SCHEMA):
        raise ValueError(
            f"a plan of schema {schema} {'carries' if clock is not None else 'lacks'} a clock; "
            f"only a {CLOCKED_PLAN_SCHEMA} plan carries one, and it always does"
        )

    def pin(p):
        return PlanPin(p["pin"], p["vendor"], p["signal"], p.get("selector"), p["open_drain"],
                       p["emulator"]["port"], int(p["emulator"]["index"]))

    def device(d):
        return PlanDevice(d["component"], d["probe"], d["model"], d["renode_type"], int(d["address"]), d["absent"])

    return EmulationPlan(
        schema=schema,
        question=payload["question"],
        requirement=payload["requirement"],
        # A bundle's plan names no snapshot; one written before it stopped
        # carrying it still reads.
        snapshot=payload.get("snapshot", ""),
        machine=payload["machine"],
        platform=payload["platform"]["model"],
        platform_file=payload["platform"]["file"],
        recorder_port=payload["platform"]["recorder_port"],
        target=payload["target"]["component"],
        firmware_path=payload["target"]["firmware"]["path"],
        firmware_target=payload["target"]["firmware"]["target"],
        core_clock_hz=int(payload["platform"]["core_clock_hz"]),
        seed=int(payload["seed"]),
        run_until_ns=int(payload["run_until_ns"]),
        buses=tuple(
            PlanBus(b["port"], b["instance"], b["emulator"], tuple(pin(p) for p in b["pins"]),
                    tuple(device(d) for d in b["devices"]))
            for b in payload["buses"]
        ),
        observations=tuple(
            PlanObservation(o["probe"], o["kind"], o["entity"], o["surface"], o["emulator"], o.get("index"))
            for o in payload["observations"]
        ),
        watched=tuple(PlanWatch(w["probe"], w["emulator"], w["entity"]) for w in payload["watched"]),
        registers=tuple(
            PlanRegister(r["source"], r["peripheral"], r["register"], int(r["address"], 16),
                         int(r["reset"], 16), r["stored"])
            for r in payload["registers"]
        ),
        stimuli=tuple(
            PlanStimulus(int(s["at_ns"]), s["component"], s["probe"], s["input"], s["property"], s["value"], s["unit"])
            for s in payload["stimuli"]
        ),
        faults=tuple(dict(f) for f in payload["faults"]),
        measures={name: dict(m) for name, m in payload["measures"].items()},
        models=tuple(dict(m) for m in payload["models"]),
        abstracted=tuple(payload["abstracted"]),
        assumptions=tuple(payload["assumptions"]),
        coverage_gaps=tuple(payload["coverage_gaps"]),
        expected_warnings=tuple(dict(w) for w in payload["expected_warnings"]),
        clock=dict(clock) if clock is not None else None,
    )


def _firmware_location(snapshot, question, path: str, target: str | None):
    """Where the firmware is on this machine: relative to the program that
    names it, which is the question's if the question names its own build,
    and otherwise the program that declares the part it runs on, as a SPICE
    model's path is. A run and the staleness check both read it here, so the
    two cannot disagree about which file the evidence's digest is of."""
    from pathlib import Path

    written = Path(path)
    if written.is_absolute():
        return written
    if question.data.get("scenario", {}).get("firmware"):
        origin = question.source_location
    else:
        part = snapshot.entities.get(target) if target else None
        origin = part.source_location if part is not None else None
    if origin is None:
        return Path.cwd() / written
    return Path(origin.file).parent / written


@dataclass
class EmulationTool:
    """An emulator answering emulation questions, at the behavioural level.

    What every emulator shares. A question is covered only by the emulator it
    recorded at elaboration, so one never stands in for another. Preparing
    compiles the plan and lowers it into the engine's own bundle; running
    crosses the engine's process boundary and keeps the bundle and what the
    run left in the workspace; reading measures the event record, whose schema
    every engine writes alike. An engine supplies its package -- a lowering
    with `bundle` and `LoweringError`, the names of the files a run leaves,
    and a `Backend` that raises `Unavailable` -- and nothing else.
    """

    name: str = ""
    level: Level = Level.BEHAVIOURAL
    backend: Any = None
    timeout: float = 300

    #: The package holding the engine's lowering and backend.
    package: ClassVar[str] = ""

    def __post_init__(self) -> None:
        if self.backend is None:
            self.backend = self._engine().Backend()

    def _engine(self):
        import importlib

        return importlib.import_module(self.package)

    def covers(self, question) -> bool:
        # A question recorded before emulators were is Renode's: every one was.
        return question.method == "emulation" and question.data.get("engine", "renode") == self.name

    def available(self) -> bool:
        """Whether the emulator is installed. A version the lowering was not
        checked against is installed, and `version` refuses it naming the
        version, so a question is reported unsupported for the reason it is."""
        return self.backend.available()

    def version(self) -> str:
        try:
            version, build = self.backend.check()
        except self._engine().Unavailable as exc:
            raise ToolUnavailable(str(exc)) from None
        return f"{version} (build {build})" if build else version

    def prepare(self, snapshot, question, *, traits=None) -> Job:
        import hashlib

        from .traits import TraitRegistry

        engine = self._engine()
        try:
            plan = compile_plan(snapshot, question, traits=traits or TraitRegistry())
        except EmulationError as exc:
            raise NotRunnable(f"{question.label}: {exc}", code=_CODES.get(exc.code or "")) from None
        location = _firmware_location(snapshot, question, plan.firmware_path, plan.target)
        if not location.is_file():
            raise NotRunnable(
                f"{question.label}: the firmware {plan.firmware_path} is not a file at {location}",
                code=SIM_EMULATION_FIRMWARE,
            )
        firmware = location.read_bytes()
        digest = "sha256:" + hashlib.sha256(firmware).hexdigest()
        try:
            files = engine.bundle(plan, firmware)
        except engine.LoweringError as exc:
            raise NotRunnable(f"{question.label}: {exc}", code=SIM_UNRESOLVED_SURFACE) from None
        reports = sorted(name for name, m in plan.measures.items() if m["kind"] == "uart_value")
        extra = {
            "plan": plan.hash,
            "seed": str(plan.seed),
            "firmware": f"{plan.firmware_path} {digest}",
            "platform": plan.platform,
            "ran": "local",
            # The part the firmware runs on: a bound firmware's path is read
            # relative to the program that declares it, here and when the
            # evidence is checked for staleness.
            "target": plan.target,
        }
        if reports:
            extra["firmware_reports"] = ", ".join(reports)
        # Every file the run is given, by its digest, as the manifest lists them.
        extra["bundle"] = ", ".join(
            f"{name} sha256:{hashlib.sha256(content).hexdigest()}" for name, content in sorted(files.items())
        )
        confidence = min(
            (QUALIFICATION_CONFIDENCE.get(m["qualification"], Decimal("0.5")) for m in plan.models),
            default=Decimal(1),
        )
        return Job(
            self.name,
            question,
            snapshot.hash,
            files,
            assumptions=plan.assumptions,
            coverage_gaps=plan.coverage_gaps,
            inputs={plan.firmware_path: digest},
            extra=extra,
            confidence=confidence,
        )

    def run(self, job: Job, *, workspace) -> RawRun:
        """Run the bundle, and keep it and what the run left in `workspace`.

        The emulator runs from the temporary copy its backend makes, so a run
        reaches nothing but its own copy. The bundle, the event record, the
        emulator's log and the outcome are then written into `workspace`:
        under `fang verify --commit` that is beside the run's evidence, and
        otherwise a scratch directory. A run that could not be made writes
        nothing.
        """
        from pathlib import Path

        from .serialization import canonical_bytes

        engine = self._engine()
        files = {name: (c.encode("utf-8") if isinstance(c, str) else c) for name, c in job.files.items()}
        try:
            run = self.backend.run(files, timeout=self.timeout)
        except engine.Unavailable as exc:
            raise ToolUnavailable(str(exc)) from None
        kept = Path(workspace)
        kept.mkdir(parents=True, exist_ok=True)
        for name, content in sorted(files.items()):
            target = kept / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        (kept / engine.lowering.EVENTS).write_bytes(run.events)
        (kept / engine.lowering.LOG).write_text(run.log, encoding="utf-8")
        ended = {
            "outcome": run.outcome,
            self.name: {"version": run.version, "build": run.build},
            "arguments": list(run.arguments),
        }
        if run.exit_status is not None:
            ended["exit_status"] = run.exit_status
        # An engine whose native input is built on the host says what built it.
        compiler = getattr(run, "compiler", None)
        if compiler:
            ended["compiler"] = compiler
        (kept / engine.lowering.OUTCOME).write_bytes(canonical_bytes(ended))
        version = f"{run.version} (build {run.build})" if run.build else run.version
        succeeded = run.outcome == "completed"
        return RawRun(
            self.name,
            version,
            run.exit_status if run.exit_status is not None else -1,
            stdout=run.log,
            outputs={"events.jsonl": run.events, "outcome": run.outcome},
            status=Status.SUCCEEDED if succeeded else Status.FAILED,
            message="" if succeeded else f"the run ended: {run.outcome}",
        )

    def read(self, job: Job, raw: RawRun) -> tuple[Measurement, ...]:
        plan = plan_from_dict(json.loads(job.files["plan.json"]))
        outcome = raw.outputs.get("outcome", "completed" if raw.status is Status.SUCCEEDED else "crashed")
        if isinstance(outcome, bytes):
            outcome = outcome.decode()
        events = raw.outputs.get("events.jsonl", b"")
        if isinstance(events, str):
            events = events.encode("utf-8")
        found = {m.name: m for m in measure(plan, run_record(events, outcome))}
        out = []
        for entry in job.question.measures:
            value = found.get(entry.name)
            quantity, reason = None, None
            if value is None:
                reason = "the plan carries no such measure"
            elif value.quantity is None:
                reason = value.reason
            elif value.quantity.unit.symbol in ("1", "") and entry.unit in ("1", ""):
                quantity = value.quantity
            else:
                quantity, _ = value.quantity.converted_to(entry.unit)
            out.append(
                Measurement(entry.name, entry.parameter, quantity, self.name, raw.version,
                            job.hash, job.confidence, reason)
            )
        return tuple(out)


@dataclass
class RenodeTool(EmulationTool):
    """Renode answering emulation questions on the platforms it models."""

    name: str = "renode"
    package: ClassVar[str] = "fang.renode"


@dataclass
class SimavrTool(EmulationTool):
    """simavr answering emulation questions on the AVR cores it models."""

    name: str = "simavr"
    package: ClassVar[str] = "fang.simavr"


def tool_for(question, tools=None):
    """The registered emulation tool that covers a question: the emulator its
    target's platform model names, installed or not. None where none does."""
    from .verification import TOOLS

    for tool in TOOLS if tools is None else tools:
        if isinstance(tool, EmulationTool) and tool.covers(question):
            return tool
    return None


#: Renode, registered after the tools already there, at the behavioural level,
#: and simavr after it. Each covers only the questions whose target's platform
#: model names it, so their order decides nothing between them.
RENODE = RenodeTool()
SIMAVR = SimavrTool()
register_method("emulation", Level.BEHAVIOURAL)
register_tool(RENODE)
register_tool(SIMAVR)


def stale(snapshot) -> tuple[tuple[str, str, str, str], ...]:
    """Emulation verifications whose evidence names a firmware the bound file
    no longer is: (verification, path, recorded digest, current digest).

    Rebuilding firmware is not a design change, so the snapshot does not move
    when the file does; the evidence's digest is how the change is seen.
    """
    import hashlib

    from .entities import Evidence, Verification

    found = []
    for verification in sorted(
        (e for e in snapshot.entities.values() if isinstance(e, Verification)), key=lambda v: v.id
    ):
        if verification.method != "emulation":
            continue
        question = Question.of(verification)
        if question is None:
            continue
        for evidence_id in verification.evidence:
            evidence = snapshot.entities.get(evidence_id)
            if not isinstance(evidence, Evidence):
                continue
            record = evidence.extensions.get("measurement", {})
            for entry in record.get("inputs", ()):
                # Resolved exactly as the run resolved it.
                location = _firmware_location(snapshot, question, entry["path"], record.get("target"))
                current = (
                    "sha256:" + hashlib.sha256(location.read_bytes()).hexdigest()
                    if location.is_file()
                    else "missing"
                )
                if current != entry["hash"]:
                    label = str(verification.identity.path or verification.id)
                    found.append((label, entry["path"], entry["hash"], current))
    return tuple(found)
