"""Simulation as a compiler target.

Spec: "Simulation Is A Compiler Target", "Simulation Plan Validation", "SPICE
Lowering", "Backends Are Reached Across A Process Boundary", "Normalized
Simulation Results", "Verification Level Selection", and, for a question's
deck, "Verification Tools Sit Behind One Protocol".

Components expose models; the kernel compiles a scope into a simulator's native
input and normalizes what comes back. A pass is a finding with the confidence its
model provenance supports, never proof of physical correctness.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .diagnostics import Diagnostic, Severity, error
from .entities import Component, Entity, Pin
from .netlist import compile_netlist
from .traits import Simulatable, TraitRegistry
from .units import Quantity
from .values import Value


class SimulationError(Exception):
    """A plan that cannot be satisfied. Never run with a substitute.

    Where the refusal is one the diagnostic registry names, it carries that
    code, so a caller can report it as the diagnostic it is.
    """

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class Level(Enum):
    """Verification levels, cheapest first."""

    EQUATION = 1
    SYMBOLIC = 2
    BEHAVIOURAL = 3
    CIRCUIT = 4
    EXTERNAL = 5

    @property
    def label(self) -> str:
        return self.name.lower()


# --------------------------------------------------------------------------
# Analyses
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Analysis:
    """The base of an analysis request."""

    probes: tuple[str, ...] = ()

    @property
    def kind(self) -> str:
        raise NotImplementedError

    def directive(self) -> str:
        """The simulator's analysis line."""
        raise NotImplementedError

    def as_dict(self) -> dict:
        return {"kind": self.kind, "probes": list(self.probes)}


@dataclass(frozen=True)
class OperatingPoint(Analysis):
    @property
    def kind(self) -> str:
        return "operating_point"

    def directive(self) -> str:
        return ".op"


@dataclass(frozen=True)
class Transient(Analysis):
    stop: str = "1ms"
    step: str = "1us"
    initial_conditions: Mapping[str, str] = field(default_factory=dict)

    @property
    def kind(self) -> str:
        return "transient"

    def directive(self) -> str:
        return f".tran {self.step} {self.stop}"

    def as_dict(self) -> dict:
        out = super().as_dict()
        out.update({"stop": self.stop, "step": self.step})
        if self.initial_conditions:
            out["initial_conditions"] = dict(self.initial_conditions)
        return out


@dataclass(frozen=True)
class DCSweep(Analysis):
    source: str = "V1"
    start: str = "0"
    stop: str = "5"
    step: str = "0.1"

    @property
    def kind(self) -> str:
        return "dc"

    def directive(self) -> str:
        return f".dc {self.source} {self.start} {self.stop} {self.step}"

    def as_dict(self) -> dict:
        out = super().as_dict()
        out.update({"source": self.source, "start": self.start, "stop": self.stop, "step": self.step})
        return out


@dataclass(frozen=True)
class ACSweep(Analysis):
    variation: str = "dec"
    points: int = 10
    start: str = "1"
    stop: str = "1meg"

    @property
    def kind(self) -> str:
        return "ac"

    def directive(self) -> str:
        return f".ac {self.variation} {self.points} {self.start} {self.stop}"

    def as_dict(self) -> dict:
        out = super().as_dict()
        out.update({"variation": self.variation, "points": self.points, "start": self.start, "stop": self.stop})
        return out


def analysis_from_dict(payload: Mapping) -> Analysis:
    """Read an analysis back from its record. The inverse of `as_dict`.

    A question stores its analysis in the graph, and the runner rebuilds it
    from there with nothing but the snapshot in hand.
    """
    kind = payload.get("kind")
    probes = tuple(payload.get("probes", ()))
    if kind == "operating_point":
        return OperatingPoint(probes=probes)
    if kind == "transient":
        return Transient(
            probes=probes,
            stop=payload["stop"],
            step=payload["step"],
            initial_conditions=dict(payload.get("initial_conditions", {})),
        )
    if kind == "dc":
        return DCSweep(
            probes=probes,
            source=payload["source"],
            start=payload["start"],
            stop=payload["stop"],
            step=payload["step"],
        )
    if kind == "ac":
        return ACSweep(
            probes=probes,
            variation=payload["variation"],
            points=int(payload["points"]),
            start=payload["start"],
            stop=payload["stop"],
        )
    raise ValueError(f"no analysis is defined for kind {kind!r}")


# --------------------------------------------------------------------------
# Plans
# --------------------------------------------------------------------------

#: Options every run pins, so a rerun is a rerun and not a new experiment.
DETERMINISTIC_OPTIONS: Mapping[str, str] = {
    "reltol": "1e-3",
    "abstol": "1e-12",
    "vntol": "1e-6",
    "method": "gear",
}


@dataclass(frozen=True)
class ModelUse:
    """One model the plan will use, with the provenance that justifies it."""

    component: str
    model_kind: str
    source: str | None
    backends: tuple[str, ...]
    distribution_restricted: bool
    provenance: tuple[dict, ...] = ()

    def as_dict(self) -> dict:
        out = {
            "component": self.component,
            "model_kind": self.model_kind,
            "backends": sorted(self.backends),
            "distribution_restricted": self.distribution_restricted,
        }
        if self.source is not None:
            out["source"] = self.source
        if self.provenance:
            out["provenance"] = list(self.provenance)
        return out


@dataclass(frozen=True)
class SimulationPlan:
    """An explicit plan. Nothing runs until one exists."""

    snapshot: str
    backend: str
    analysis: Analysis
    scope: tuple[str, ...]
    models: tuple[ModelUse, ...]
    abstracted: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    options: Mapping[str, str] = field(default_factory=lambda: dict(DETERMINISTIC_OPTIONS))
    seed: int | None = None

    @property
    def coverage_gaps(self) -> tuple[str, ...]:
        """What this run does not cover. Stated, never left implicit."""
        gaps = [f"{component} is abstracted, not modelled" for component in self.abstracted]
        if self.analysis.kind == "operating_point":
            gaps.append("an operating point says nothing about dynamic behaviour")
        if not self.analysis.probes:
            gaps.append("no probes were requested, so nothing is asserted about signals")
        return tuple(sorted(gaps))

    def as_dict(self) -> dict:
        return {
            "snapshot": self.snapshot,
            "backend": self.backend,
            "analysis": self.analysis.as_dict(),
            "scope": sorted(self.scope),
            "models": [model.as_dict() for model in self.models],
            "abstracted": sorted(self.abstracted),
            "assumptions": list(self.assumptions),
            "options": dict(sorted(self.options.items())),
            "seed": self.seed,
            "coverage_gaps": list(self.coverage_gaps),
        }


def compile_plan(
    snapshot,
    *,
    backend: str = "ngspice",
    analysis: Analysis | None = None,
    scope: Sequence[str] | None = None,
    traits: TraitRegistry | None = None,
    abstracted: Sequence[str] = (),
    seed: int | None = None,
) -> SimulationPlan:
    """Compile a simulation request into an explicit plan.

    Raises rather than substituting: a plan that cannot satisfy its own
    conditions is rejected with the reason, and never run with a stand-in.
    """
    analysis = analysis or OperatingPoint()
    entities = snapshot.entities
    traits = traits or TraitRegistry()

    components = [
        entity
        for entity in sorted(entities.values(), key=lambda e: e.id)
        if isinstance(entity, Component)
        and (scope is None or entity.id in set(scope))
    ]
    abstracted_set = set(abstracted)

    models: list[ModelUse] = []
    assumptions: list[str] = []

    for component in components:
        if component.id in abstracted_set:
            assumptions.append(
                f"{component.id} is abstracted: it contributes no device to the netlist"
            )
            continue

        trait = traits.get(component.id, "simulatable")
        if trait is None:
            if _is_primitive(component):
                # A resistor is a device the simulator already knows; it needs no
                # vendor model, and saying so is not the same as inventing one.
                continue
            raise SimulationError(
                f"{component.id} has no simulation model and is not abstracted; "
                "the plan is rejected rather than run with a substitute"
            )

        if backend not in trait.backends:
            raise SimulationError(
                f"{component.id} carries a model for {', '.join(sorted(trait.backends)) or 'no backend'}, "
                f"not for {backend}"
            )

        missing = _missing_pins(component, entities, trait)
        if missing:
            raise SimulationError(
                f"{component.id}'s pin map does not cover {', '.join(missing)}"
            )

        models.append(
            ModelUse(
                component.id,
                trait.model_kind,
                trait.source,
                tuple(trait.backends),
                trait.distribution_restricted,
                tuple(trait.provenance.as_list()),
            )
        )
        if trait.distribution_restricted:
            assumptions.append(
                f"{component.id}'s model forbids redistribution and is referenced, "
                "not inlined"
            )

    return SimulationPlan(
        snapshot.hash,
        backend,
        analysis,
        tuple(component.id for component in components),
        tuple(models),
        tuple(sorted(abstracted_set)),
        tuple(assumptions),
        dict(DETERMINISTIC_OPTIONS),
        seed,
    )


#: Designator prefixes SPICE models natively; these need no vendor model.
_PRIMITIVE_PREFIXES = frozenset({"R", "C", "L", "V", "I"})


def _is_primitive(component: Component) -> bool:
    return component.extensions.get("designator_prefix") in _PRIMITIVE_PREFIXES


def _missing_pins(component: Component, entities, trait: Simulatable) -> list[str]:
    pins = [
        entity.vendor_name
        for entity in entities.values()
        if isinstance(entity, Pin) and entity.owner == component.id
    ]
    if not trait.pin_map:
        return sorted(pins)
    return sorted(pin for pin in pins if pin not in trait.pin_map)


# --------------------------------------------------------------------------
# Lowering
# --------------------------------------------------------------------------


def lower_to_spice(snapshot, plan: SimulationPlan, *, traits=None, title: str = "fang") -> str:
    """Emit the simulator's native netlist.

    The kernel writes SPICE itself rather than binding to a wrapper, so the
    backend stays replaceable and its assumptions stay out of the model.
    """
    netlist = compile_netlist(snapshot, traits=traits)
    scope = set(plan.scope)

    net_of = spice_nodes(snapshot, netlist)
    designator_of = {c.entity_id: c.designator for c in netlist.components}
    pins_of: dict[str, list[str]] = {}
    for entity in sorted(snapshot.entities.values(), key=lambda e: e.id):
        if isinstance(entity, Pin) and entity.owner in designator_of:
            pins_of.setdefault(designator_of[entity.owner], []).append(entity.vendor_name)

    lines = [f"* {title}", f"* plan for {plan.backend} over {plan.snapshot}"]

    abstracted_designators = {
        designator_of[entity_id]
        for entity_id in plan.abstracted
        if entity_id in designator_of
    }

    for component in netlist.components:
        if component.entity_id not in scope:
            continue
        if component.designator in abstracted_designators:
            lines.append(f"* {component.designator} abstracted; no device emitted")
            continue
        terminals = sorted(pins_of.get(component.designator, ()))
        if len(terminals) < 2:
            lines.append(
                f"* {component.designator} has fewer than two terminals and emits no device"
            )
            continue
        nodes = [net_of[(component.designator, pin)] for pin in terminals[:2]]
        lines.append(
            f"{component.designator} {nodes[0]} {nodes[1]} {_spice_value(component.value)}"
        )

    for model in plan.models:
        if model.source:
            # A restricted model is referenced by path, never inlined.
            lines.append(f".include {model.source}")

    for name, value in sorted(plan.options.items()):
        lines.append(f".options {name}={value}")
    lines.append(plan.analysis.directive())
    if plan.analysis.probes:
        lines.append(".print " + plan.analysis.kind + " " + " ".join(plan.analysis.probes))
    lines.append(".end")
    return "\n".join(lines) + "\n"


def _is_ground(name: str) -> bool:
    lowered = name.lower()
    return "gnd" in lowered or lowered.endswith("-0")


def spice_nodes(snapshot, netlist: Netlist) -> dict[tuple[str, str], str]:
    """Which SPICE node every terminal sits on, keyed by designator and pin.

    Every terminal needs a node. A pin on a net takes that net's number; a pin
    on no net takes a node of its own, because SPICE has no notion of a terminal
    that is simply absent.

    Node 0 is the simulator's ground, and which net that is comes from the
    graph: a net holding a pin whose canonical role is ground is the return.
    The net's *name* is only a fallback, because an elaborated net is named
    after the first pad on it and a program cannot say otherwise -- so a board
    whose ground happens to start at a capacitor would otherwise lower to a deck
    with no ground node at all.

    A script that reads a run's output needs the same numbering the deck was
    written with, so it asks for it here rather than deriving its own.
    """
    ground_pins = {
        entity.id
        for entity in snapshot.entities.values()
        if isinstance(entity, Pin) and entity.role == "ground"
    }

    nodes: dict[tuple[str, str], str] = {}
    for index, net in enumerate(netlist.nets, start=1):
        grounded = _is_ground(net.name) or any(
            node.pin_id in ground_pins for node in net.nodes
        )
        name = "0" if grounded else str(index)
        for node in net.nodes:
            nodes[(node.designator, node.pin)] = name

    designator_of = {c.entity_id: c.designator for c in netlist.components}
    pins_of: dict[str, list[str]] = {}
    for entity in sorted(snapshot.entities.values(), key=lambda e: e.id):
        if isinstance(entity, Pin) and entity.owner in designator_of:
            pins_of.setdefault(designator_of[entity.owner], []).append(entity.vendor_name)

    dangling = len(netlist.nets)
    for designator in sorted(pins_of):
        for pin in sorted(pins_of[designator]):
            if (designator, pin) not in nodes:
                dangling += 1
                nodes[(designator, pin)] = str(dangling)
    return nodes


def _spice_value(value: str) -> str:
    """Render a quantity the way SPICE expects, without changing its magnitude."""
    text = value.replace(" ", "")
    for unit in ("Ohm", "F", "H", "V", "A", "W", "Hz"):
        if text.endswith(unit):
            text = text[: -len(unit)]
            break
    return text or "1"


# --------------------------------------------------------------------------
# Lowering for a question: what a real run needs
# --------------------------------------------------------------------------
#
# A question's deck is written from the snapshot, the traits and the question
# alone. Every magnitude is written as a plain decimal in SI base units, so no
# SPICE suffix -- where "M" is milli and "MEG" is mega -- can change what a
# number means, and every line is a function of its inputs, so two
# preparations of one question are byte-identical.


def spice_number(magnitude: Decimal) -> str:
    """A decimal magnitude as SPICE reads it, without a suffix."""
    from .units import _decimal_str

    return _decimal_str(magnitude)


def si_magnitude(quantity: Quantity) -> Decimal:
    """The one magnitude a device is written with, in SI base units.

    A scalar is its value and a tolerance its nominal; a range is its typical
    value when it has one. A range with no typical value has no one magnitude,
    and choosing its midpoint would be inventing one, so it is refused.
    """
    if quantity.kind == "scalar":
        magnitude = quantity.value
    elif quantity.kind == "tolerance":
        magnitude = quantity.nominal
    elif quantity.typical is not None:
        magnitude = quantity.typical
    else:
        raise SimulationError(
            f"{quantity} is a range with no typical value; a device is written "
            "with one magnitude and none is chosen for it"
        )
    return quantity._to_base(magnitude)


@dataclass(frozen=True)
class Subcircuit:
    """A model's `.subckt` line: its name and its ports in declared order."""

    name: str
    ports: tuple[str, ...]


def read_subcircuit(text: str, *, source: str = "the model") -> Subcircuit:
    """Read the first `.subckt` line of a model file.

    The ports are the model's own order, which is the order an instance must
    list its nodes in; the part's pin map says which pin lands on which port.
    Continuation lines are joined and parameters after the ports are ignored.
    """
    logical: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("*"):
            continue
        for marker in (";", "$ "):
            if marker in line:
                line = line.split(marker, 1)[0].rstrip()
        if line.startswith("+") and logical:
            logical[-1] += " " + line[1:].strip()
        else:
            logical.append(line)
    for line in logical:
        tokens = line.split()
        if tokens and tokens[0].lower() == ".subckt":
            if len(tokens) < 2:
                break
            ports = []
            for token in tokens[2:]:
                if "=" in token or token.lower() in ("params:", "param:"):
                    break
                ports.append(token)
            return Subcircuit(tokens[1], tuple(ports))
    raise SimulationError(f"{source} declares no .subckt line")


@dataclass(frozen=True)
class ModelFile:
    """A model a question's deck includes, and the facts the evidence keeps.

    `path` is how the deck names the file, relative to the run's workspace;
    `location` is where it is read from on this machine, which is not part of
    any record; `digest` is what the evidence records, because the snapshot
    does not hold the file.
    """

    component: str
    path: str
    location: str
    digest: str
    subcircuit: Subcircuit


def model_path(component: Component, source: str) -> tuple[str, Path]:
    """Where a part's model file is, and how a run's workspace names it.

    A relative source is resolved against the folder of the program that
    declared the part, which its source location gives, and is named in the
    workspace by that same relative path, so nothing machine-specific reaches
    a job, its hash or the evidence. An absolute or escaping path is named
    `models/<file>`.
    """
    from pathlib import PurePosixPath

    if not source:
        raise SimulationError(f"{component.id}'s model names no file")
    written = Path(source)
    if written.is_absolute():
        location = written
    elif component.source_location is not None:
        location = Path(component.source_location.file).parent / written
    else:
        location = Path.cwd() / written

    relative = PurePosixPath(source)
    if relative.is_absolute() or ".." in relative.parts:
        relative = PurePosixPath("models") / relative.name
    if not location.is_file():
        raise SimulationError(f"{component.id}'s model {source} is not a file at {location}")
    return relative.as_posix(), location


def load_model(component: Component, trait: Simulatable) -> ModelFile:
    """Find, digest and read the subcircuit model a part's trait names."""
    import hashlib

    relative, location = model_path(component, trait.source)
    data = location.read_bytes()
    subcircuit = read_subcircuit(data.decode("utf-8", errors="replace"), source=trait.source)
    return ModelFile(
        component.id,
        relative,
        str(location),
        "sha256:" + hashlib.sha256(data).hexdigest(),
        subcircuit,
    )


def subcircuit_instance(
    designator: str,
    model: ModelFile,
    pin_map: Mapping[str, str],
    node_of_pin: Mapping[str, str],
) -> str:
    """An `X` device instantiating a part's model.

    The nodes are listed in the model's port order, each the node of the pin
    the part's pin map lands on that port. A port no pin reaches is refused by
    name, as is a pin mapped onto a port the model does not declare: either
    would be a deck whose wiring nobody chose.
    """
    from .diagnostics import SIM_MODEL_PORT_UNREACHED

    pins_of: dict[str, list[str]] = {}
    for pin, port in sorted(pin_map.items()):
        pins_of.setdefault(port, []).append(pin)
    unreached = [port for port in model.subcircuit.ports if port not in pins_of]
    if unreached:
        raise SimulationError(
            f"{designator}'s model {model.subcircuit.name} has port"
            f"{'s' if len(unreached) > 1 else ''} {', '.join(unreached)} that no pin "
            "of the part's pin map reaches",
            code=SIM_MODEL_PORT_UNREACHED,
        )
    undeclared = sorted(set(pins_of) - set(model.subcircuit.ports))
    if undeclared:
        raise SimulationError(
            f"{designator}'s pin map lands on {', '.join(undeclared)}, which "
            f"{model.subcircuit.name} does not declare",
            code=SIM_MODEL_PORT_UNREACHED,
        )
    nodes = [node_of_pin[pins_of[port][0]] for port in model.subcircuit.ports]
    return f"X{designator} {' '.join(nodes)} {model.subcircuit.name}"


def primitive_device(component: Component, designator: str, nodes: Sequence[str]) -> str:
    """A device SPICE knows natively, written from the value the graph holds.

    A primitive with no known value is refused: a resistor of unknown
    resistance is not a one-ohm resistor.
    """
    from .netlist import VALUE_PARAMETERS

    prefix = component.extensions.get("designator_prefix")
    parameter = VALUE_PARAMETERS.get(prefix)
    value = component.parameters.get(parameter) if parameter else None
    if not isinstance(value, Value) or not value.known or value.quantity is None:
        raise SimulationError(
            f"{designator}'s {parameter or 'value'} is unknown; a device is not "
            "written with a value nobody gave it"
        )
    magnitude = spice_number(si_magnitude(value.quantity))
    if prefix == "V":
        return f"{designator} {nodes[0]} {nodes[1]} DC {magnitude}"
    return f"{designator} {nodes[0]} {nodes[1]} {magnitude}"


@dataclass(frozen=True)
class BenchItem:
    """One supply or load, at the nodes its surface resolved to."""

    role: str               # "supply" or "load"
    surface: str
    quantity: Quantity
    positive: str
    negative: str


def bench_device(item: BenchItem, index: int, *, ac: bool = False) -> str:
    """A bench item as a device: a supply is a `V`, a load an `I` or an `R`.

    Which, for a load, is decided by its dimension, and a load of any other
    dimension is refused. Under an AC analysis a supply is also the
    stimulus, at its own magnitude, and the question's assumptions say so.
    """
    from .diagnostics import SIM_LOAD_DIMENSION
    from .units import Unit

    magnitude = spice_number(si_magnitude(item.quantity))
    nodes = f"{item.positive} {item.negative}"
    if item.role == "supply":
        if item.quantity.dimension != Unit.parse("V").dimension:
            raise SimulationError(f"the supply at {item.surface} is not a voltage")
        stimulus = f" AC {magnitude}" if ac else ""
        return f"Vfang_supply{index} {nodes} DC {magnitude}{stimulus}"
    if item.quantity.dimension == Unit.parse("A").dimension:
        # Current flows from the first node through the source to the second:
        # out of the surface's signal, into its return.
        return f"Ifang_load{index} {nodes} DC {magnitude}"
    if item.quantity.dimension == Unit.parse("Ohm").dimension:
        return f"Rfang_load{index} {nodes} {magnitude}"
    raise SimulationError(
        f"the load at {item.surface} is {item.quantity}; a load is a current "
        "drawn or a resistance, nothing else",
        code=SIM_LOAD_DIMENSION,
    )


@dataclass(frozen=True)
class DeckMeasure:
    """One measure as a deck sees it: a slot, two nodes, and what to take.

    Magnitudes are decimals in SI base units: a window in seconds or hertz,
    a level in volts.
    """

    slot: str
    kind: str
    positive: str
    negative: str = "0"
    after: Decimal | None = None
    until: Decimal | None = None
    at: Decimal | None = None
    level: Decimal | None = None
    edge: str = "either"
    occurrence: int = 1


class SpiceDialect:
    """What differs between SPICE simulators: analysis, measurement, output.

    Everything else in a question's deck -- the devices, the subcircuit
    instances, the bench -- is shared, which is what lets a second simulator
    answer the same question with the same circuit.
    """

    name: str = ""
    #: The analysis kinds the dialect can lower a measure over.
    analyses: frozenset[str] = frozenset()

    def options(self, options: Mapping[str, str]) -> list[str]:
        """The solver options, in the simulator's own form."""
        return [f".options {name}={value}" for name, value in sorted(options.items())]

    def analysis_lines(self, analysis: Analysis, measures: Sequence[DeckMeasure]) -> list[str]:
        """The analysis and a measurement line for each measure."""
        raise NotImplementedError

    def parse(
        self,
        output: str,
        measures: Sequence[DeckMeasure],
        *,
        outputs: Mapping[str, str] | None = None,
    ) -> dict[str, Decimal | str]:
        """Each slot's number, or the reason the output gives none.

        `output` is what the simulator printed and `outputs` the files it
        wrote; a dialect reads whichever its simulator reports measures in.
        """
        raise NotImplementedError


#: ngspice's name for each measure's statistic.
_NGSPICE_STATISTIC = {
    "peak_to_peak": "PP",
    "average": "AVG",
    "maximum": "MAX",
    "minimum": "MIN",
}

_NGSPICE_EDGE = {"rising": "RISE", "falling": "FALL", "either": "CROSS"}


class NgspiceDialect(SpiceDialect):
    """ngspice in batch mode, measuring through a `.control` block.

    Both choices are forced by the installed ngspice (45.2): batch mode
    ignores `.print op`, so an operating-point value is printed from the
    control block; and a deck-level `.meas ac` reports the real part of a node
    voltage where the same line in a control block reports its magnitude --
    an RC corner came back as 1024 Hz against the correct 1592 Hz.
    """

    name = "ngspice"
    analyses = frozenset({"operating_point", "transient", "ac"})

    _MEASURED = re.compile(r"^\s*(fang_m\d+)\s*=\s*([-+0-9.eE]+)", re.MULTILINE)
    _FAILED = re.compile(r"^\s*meas\s+\w+\s+(fang_m\d+)\b.*failed!", re.MULTILINE | re.IGNORECASE)

    @staticmethod
    def _signal(measure: DeckMeasure, analysis: str) -> str:
        def voltage(node: str) -> str:
            return "0" if node == "0" else f"v({node})"

        if measure.positive == "0" and measure.negative == "0":
            raise SimulationError(
                f"{measure.slot} would measure ground against ground"
            )
        if measure.negative == "0":
            expression = voltage(measure.positive)
        else:
            expression = f"{voltage(measure.positive)}-{voltage(measure.negative)}"
        return f"mag({expression})" if analysis == "ac" else expression

    def analysis_lines(self, analysis: Analysis, measures: Sequence[DeckMeasure]) -> list[str]:
        if analysis.kind not in self.analyses:
            raise SimulationError(f"ngspice does not measure over a {analysis.kind} analysis here")
        if getattr(analysis, "initial_conditions", None):
            raise SimulationError("initial conditions are not lowered for a question")
        lines = [".control", analysis.directive().lstrip(".")]
        sweep = {"transient": "tran", "ac": "ac"}.get(analysis.kind)
        for index, measure in enumerate(measures):
            signal = self._signal(measure, analysis.kind)
            if analysis.kind == "operating_point":
                if measure.kind != "value_at" or measure.at is not None:
                    raise SimulationError(
                        f"an operating point has one value per node; {measure.kind} "
                        "needs a sweep"
                    )
                lines.append(f"let {measure.slot} = {signal}")
                lines.append(f"print {measure.slot}")
                continue
            vector = f"fang_s{index}"
            lines.append(f"let {vector} = {signal}")
            if measure.kind in _NGSPICE_STATISTIC:
                window = "".join(
                    f" {name}={spice_number(value)}"
                    for name, value in (("from", measure.after), ("to", measure.until))
                    if value is not None
                )
                lines.append(
                    f"meas {sweep} {measure.slot} {_NGSPICE_STATISTIC[measure.kind]} "
                    f"{vector}{window}"
                )
            elif measure.kind == "value_at":
                if measure.at is None:
                    raise SimulationError(f"{measure.slot} names no point to take the value at")
                lines.append(
                    f"meas {sweep} {measure.slot} FIND {vector} AT={spice_number(measure.at)}"
                )
            elif measure.kind == "crossing":
                after = f" FROM={spice_number(measure.after)}" if measure.after is not None else ""
                lines.append(
                    f"meas {sweep} {measure.slot} WHEN {vector}={spice_number(measure.level)} "
                    f"{_NGSPICE_EDGE[measure.edge]}={measure.occurrence}{after}"
                )
            else:
                raise SimulationError(f"ngspice has no lowering for a {measure.kind} measure")
        lines.append(".endc")
        return lines

    def parse(
        self,
        output: str,
        measures: Sequence[DeckMeasure],
        *,
        outputs: Mapping[str, str] | None = None,
    ) -> dict[str, Decimal | str]:
        """Read `name = value` lines into decimals, and nothing else.

        A measure ngspice reports as failed, or does not report at all, gets a
        reason and no number: the parser contains nothing the output did not.
        """
        found: dict[str, Decimal | str] = {}
        for slot in self._FAILED.findall(output):
            found[slot.lower()] = "ngspice reported the measure as failed"
        for slot, text in self._MEASURED.findall(output):
            slot = slot.lower()
            if slot in found:
                continue
            try:
                found[slot] = Decimal(text)
            except Exception:
                found[slot] = f"ngspice printed {text!r}, which is not a number"
        return {
            measure.slot: found.get(measure.slot, "ngspice's output does not report it")
            for measure in measures
        }


#: Xyce's name for each measure's statistic, which is SPICE's.
_XYCE_STATISTIC = dict(_NGSPICE_STATISTIC)

_XYCE_EDGE = dict(_NGSPICE_EDGE)

#: Which of the solver options Xyce takes, and in which of its packages.
_XYCE_TIMEINT = ("abstol", "method", "reltol")


class XyceDialect(SpiceDialect):
    """Xyce: deck-level `.MEASURE` lines, read back from its measure file.

    Written from the Xyce Reference Guide, not against a binary, because Xyce
    is not installed where this was built: Xyce takes `.MEASURE` at the deck
    level and writes each result to a measure file beside the netlist --
    `<netlist>.mt0` for a transient, `<netlist>.ma0` for an AC sweep -- one
    `NAME = value` line per measure, with `FAILED` in place of a value for a
    measure that could not be taken. An AC measure reads the magnitude, `VM`.
    Solver options belong to packages; the tolerances and the integration
    method are `TIMEINT` options, and an option with no Xyce counterpart is
    named in a comment rather than written as something it is not.
    """

    name = "xyce"
    analyses = frozenset({"transient", "ac"})

    _MEASURED = re.compile(r"^\s*(fang_m\d+)\s*=\s*(\S+)", re.MULTILINE | re.IGNORECASE)
    _MEASURE_FILE = re.compile(r"\.m[a-z]\d+$")

    def options(self, options: Mapping[str, str]) -> list[str]:
        timeint = [
            f"{name.upper()}={value}"
            for name, value in sorted(options.items())
            if name in _XYCE_TIMEINT
        ]
        lines = [".OPTIONS TIMEINT " + " ".join(timeint)] if timeint else []
        lines += [
            f"* {name}={value} has no Xyce option and is not written"
            for name, value in sorted(options.items())
            if name not in _XYCE_TIMEINT
        ]
        return lines

    @staticmethod
    def _signal(measure: DeckMeasure, analysis: str) -> str:
        if measure.positive == "0" and measure.negative == "0":
            raise SimulationError(f"{measure.slot} would measure ground against ground")
        nodes = measure.positive if measure.negative == "0" else f"{measure.positive},{measure.negative}"
        return f"VM({nodes})" if analysis == "ac" else f"V({nodes})"

    def analysis_lines(self, analysis: Analysis, measures: Sequence[DeckMeasure]) -> list[str]:
        if analysis.kind not in self.analyses:
            raise SimulationError(f"Xyce does not measure over a {analysis.kind} analysis here")
        if getattr(analysis, "initial_conditions", None):
            raise SimulationError("initial conditions are not lowered for a question")
        sweep = {"transient": "TRAN", "ac": "AC"}[analysis.kind]
        lines = [analysis.directive()]
        for measure in measures:
            signal = self._signal(measure, analysis.kind)
            head = f".MEASURE {sweep} {measure.slot}"
            if measure.kind in _XYCE_STATISTIC:
                window = "".join(
                    f" {name}={spice_number(value)}"
                    for name, value in (("FROM", measure.after), ("TO", measure.until))
                    if value is not None
                )
                lines.append(f"{head} {_XYCE_STATISTIC[measure.kind]} {signal}{window}")
            elif measure.kind == "value_at":
                if measure.at is None:
                    raise SimulationError(f"{measure.slot} names no point to take the value at")
                lines.append(f"{head} FIND {signal} AT={spice_number(measure.at)}")
            elif measure.kind == "crossing":
                after = f" FROM={spice_number(measure.after)}" if measure.after is not None else ""
                lines.append(
                    f"{head} WHEN {signal}={spice_number(measure.level)} "
                    f"{_XYCE_EDGE[measure.edge]}={measure.occurrence}{after}"
                )
            else:
                raise SimulationError(f"Xyce has no lowering for a {measure.kind} measure")
        return lines

    def parse(
        self,
        output: str,
        measures: Sequence[DeckMeasure],
        *,
        outputs: Mapping[str, str] | None = None,
    ) -> dict[str, Decimal | str]:
        """Read the measure file's `NAME = value` lines into decimals.

        `FAILED` is a measure Xyce could not take; a measure the file does not
        name is not reported. Either gets a reason and no number.
        """
        found: dict[str, Decimal | str] = {}
        for path, text in sorted((outputs or {}).items()):
            if not self._MEASURE_FILE.search(path):
                continue
            for slot, value in self._MEASURED.findall(text):
                slot = slot.lower()
                if value.upper() == "FAILED":
                    found[slot] = "Xyce reported the measure as failed"
                    continue
                try:
                    found[slot] = Decimal(value)
                except Exception:
                    found[slot] = f"Xyce wrote {value!r}, which is not a number"
        return {
            measure.slot: found.get(measure.slot, "Xyce's measure file does not report it")
            for measure in measures
        }


def lower_question(
    *,
    title: Sequence[str],
    devices: Sequence[str],
    bench: Sequence[BenchItem],
    models: Sequence[ModelFile],
    analysis: Analysis,
    measures: Sequence[DeckMeasure],
    dialect: SpiceDialect,
    options: Mapping[str, str] = DETERMINISTIC_OPTIONS,
) -> str:
    """Write a question's deck: shared circuit, then the dialect's lines.

    The circuit -- devices, subcircuit instances and bench -- is the same for
    every SPICE dialect; only the options, the analysis and the measurement
    lines are the dialect's. Each model is included by path, never inlined.
    """
    ac = analysis.kind == "ac"
    lines = [f"* {line}" for line in title]
    lines.extend(devices)
    for role in ("supply", "load"):
        items = [item for item in bench if item.role == role]
        lines.extend(bench_device(item, index, ac=ac) for index, item in enumerate(items))
    for path in sorted({model.path for model in models}):
        lines.append(f".include {path}")
    lines.extend(dialect.options(options))
    lines.extend(dialect.analysis_lines(analysis, measures))
    lines.append(".end")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Backends
# --------------------------------------------------------------------------


class BackendUnavailable(Exception):
    """The simulator is not installed. Reported, never worked around."""


@dataclass(frozen=True)
class RawResult:
    backend: str
    version: str
    stdout: str
    exit_status: int
    netlist: str
    #: Files the run wrote beside its input, by name: Xyce's measure files.
    outputs: Mapping[str, str] = field(default_factory=dict)


@dataclass
class NgspiceBackend:
    """ngspice, reached across a process boundary.

    The executable runs against a temporary copy of its input with the source
    project unreachable to it, and every invocation is recorded.
    """

    name: str = "ngspice"
    executable: str = "ngspice"

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def version(self) -> str:
        if not self.available():
            raise BackendUnavailable(f"{self.executable} is not installed")
        completed = subprocess.run(
            [self.executable, "--version"], capture_output=True, text=True, timeout=30
        )
        printed = [
            line.strip() for line in (completed.stdout or completed.stderr).splitlines()
        ]
        # ngspice opens its banner with a rule of asterisks, so the first line
        # is not the version. The line that names the program is, and recording
        # the rule instead would record nothing.
        for line in printed:
            if self.name in line.lower():
                return line.strip("* ").split(" : ")[0].strip()
        return next((line for line in printed if line), "unknown")

    def run(self, netlist: str, *, workspace: Path, timeout: int = 60) -> RawResult:
        if not self.available():
            raise BackendUnavailable(
                f"{self.executable} is not installed; the run reports unsupported "
                "rather than producing a substitute result"
            )
        workspace.mkdir(parents=True, exist_ok=True)
        deck = workspace / "deck.cir"
        deck.write_text(netlist)
        completed = subprocess.run(
            [self.executable, "-b", str(deck)],
            capture_output=True,
            text=True,
            cwd=workspace,
            timeout=timeout,
        )
        return RawResult(
            self.name, self.version(), completed.stdout, completed.returncode, netlist
        )


@dataclass
class XyceBackend:
    """Xyce, reached across a process boundary as ngspice is.

    Xyce writes its measures to files beside the netlist rather than to its
    output, so a run returns those files with what it printed. Where Xyce is
    not installed it says so, by name, and nothing runs in its place.
    """

    name: str = "xyce"
    executable: str = "Xyce"

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def version(self) -> str:
        if not self.available():
            raise BackendUnavailable(f"{self.executable} is not installed")
        completed = subprocess.run(
            [self.executable, "-v"], capture_output=True, text=True, timeout=30
        )
        printed = [line.strip() for line in (completed.stdout or completed.stderr).splitlines()]
        for line in printed:
            if self.name in line.lower():
                return line
        return next((line for line in printed if line), "unknown")

    def run(self, netlist: str, *, workspace: Path, timeout: int = 60) -> RawResult:
        if not self.available():
            raise BackendUnavailable(
                f"{self.executable} is not installed; the run reports unsupported "
                "rather than producing a substitute result"
            )
        workspace.mkdir(parents=True, exist_ok=True)
        deck = workspace / "deck.cir"
        deck.write_text(netlist)
        completed = subprocess.run(
            [self.executable, str(deck)],
            capture_output=True,
            text=True,
            cwd=workspace,
            timeout=timeout,
        )
        outputs = {
            path.name: path.read_text(errors="replace")
            for path in sorted(workspace.glob(f"{deck.name}.m*"))
            if path.is_file()
        }
        return RawResult(
            self.name, self.version(), completed.stdout, completed.returncode, netlist,
            outputs=outputs,
        )


# --------------------------------------------------------------------------
# Normalized results
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Assertion:
    expression: str
    result: str          # pass, fail, undecided

    def as_dict(self) -> dict:
        return {"expression": self.expression, "result": self.result}


@dataclass(frozen=True)
class NormalizedResult:
    """What a run produced, with everything needed to judge it.

    A pass here is a finding with a confidence, not proof of physical
    correctness; first-spin results remain the physical evidence.
    """

    plan: SimulationPlan
    backend: str
    backend_version: str
    signals: Mapping[str, str]        # probe name to artifact reference
    assertions: tuple[Assertion, ...] = ()
    exit_status: int = 0
    confidence: str = "inferred"

    @property
    def passed(self) -> bool:
        return self.exit_status == 0 and all(a.result == "pass" for a in self.assertions)

    def as_finding(self) -> dict:
        """A simulation pass is a finding, never a proof."""
        return {
            "kind": "simulation",
            "result": "PASS" if self.passed else "FAIL",
            "confidence": self.confidence,
            "coverage_gaps": list(self.plan.coverage_gaps),
            "caveat": (
                "a simulation pass is not proof of physical correctness; "
                "first-spin measurement remains the physical evidence"
            ),
        }

    def as_dict(self) -> dict:
        return {
            "analysis": self.plan.analysis.kind,
            "backend": self.backend,
            "backend_version": self.backend_version,
            "plan": self.plan.as_dict(),
            "models": [model.as_dict() for model in self.plan.models],
            "assumptions": list(self.plan.assumptions),
            "coverage_gaps": list(self.plan.coverage_gaps),
            # Samples are referenced as artifacts, never inlined.
            "signals": dict(sorted(self.signals.items())),
            "assertions": [a.as_dict() for a in self.assertions],
            "exit_status": self.exit_status,
            "finding": self.as_finding(),
        }


def normalize(
    plan: SimulationPlan,
    raw: RawResult,
    *,
    artifacts: Mapping[str, str] | None = None,
    assertions: Sequence[Assertion] = (),
) -> NormalizedResult:
    """Bring a backend's output back into one shape everything else reads."""
    signals = dict(artifacts or {})
    for probe in plan.analysis.probes:
        signals.setdefault(probe, f"artifact://{plan.snapshot}/{plan.backend}/{probe}")
    return NormalizedResult(
        plan, raw.backend, raw.version, signals, tuple(assertions), raw.exit_status
    )


# --------------------------------------------------------------------------
# Verification levels
# --------------------------------------------------------------------------


def select_level(
    *,
    decidable_by_equation: bool = False,
    linear: bool = False,
    system_level: bool = False,
    needs_analog_detail: bool = False,
    needs_field_solver: bool = False,
) -> Level:
    """Pick the cheapest level that can decide the question.

    Cheapest first, because running a circuit simulation to answer a question an
    equation settles costs time and buys no more confidence.
    """
    if needs_field_solver:
        return Level.EXTERNAL
    if decidable_by_equation:
        return Level.EQUATION
    if linear:
        return Level.SYMBOLIC
    if system_level and not needs_analog_detail:
        return Level.BEHAVIOURAL
    return Level.CIRCUIT
