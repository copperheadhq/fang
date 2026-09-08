"""Simulation as a compiler target.

Spec: "Simulation Is A Compiler Target", "Simulation Plan Validation", "SPICE
Lowering", "Backends Are Reached Across A Process Boundary", "Normalized
Simulation Results", and "Verification Level Selection".

Components expose models; the kernel compiles a scope into a simulator's native
input and normalizes what comes back. A pass is a finding with the confidence its
model provenance supports, never proof of physical correctness.
"""

from __future__ import annotations

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
    """A plan that cannot be satisfied. Never run with a substitute."""


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

    # Every terminal needs a node. A pin on a net takes that net's number; a pin
    # on no net takes a node of its own, because SPICE has no notion of a
    # terminal that is simply absent.
    net_of: dict[tuple[str, str], str] = {}
    for index, net in enumerate(netlist.nets, start=1):
        name = "0" if _is_ground(net.name) else str(index)
        for node in net.nodes:
            net_of[(node.designator, node.pin)] = name

    designator_of = {c.entity_id: c.designator for c in netlist.components}
    pins_of: dict[str, list[str]] = {}
    for entity in sorted(snapshot.entities.values(), key=lambda e: e.id):
        if isinstance(entity, Pin) and entity.owner in designator_of:
            pins_of.setdefault(designator_of[entity.owner], []).append(entity.vendor_name)

    dangling = len(netlist.nets)
    for designator in sorted(pins_of):
        for pin in sorted(pins_of[designator]):
            if (designator, pin) not in net_of:
                dangling += 1
                net_of[(designator, pin)] = str(dangling)

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


def _spice_value(value: str) -> str:
    """Render a quantity the way SPICE expects, without changing its magnitude."""
    text = value.replace(" ", "")
    for unit in ("Ohm", "F", "H", "V", "A", "W", "Hz"):
        if text.endswith(unit):
            text = text[: -len(unit)]
            break
    return text or "1"


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
        first = (completed.stdout or completed.stderr).splitlines()
        return first[0].strip() if first else "unknown"

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
