"""Verification questions, the tools that answer them, and the way back in.

Spec: "Verification Questions Are Declared", "The Bench Is Explicit", "The
Cheapest Verification Level Is Chosen And Recorded", "Verification Tools Sit
Behind One Protocol", "Measurements Re-enter Through The Commit Gate", "A
Failing Measurement Is Recorded And Not Applied", "The Verify Command", and,
for the declarations `fang.rulecheck` and `fang.rf` answer, "Rule Checks Are
Evidence" and "A Touchstone Model Is Data".

A question is a verification entity whose result is not known yet. A program
declares it beside the requirement it serves -- the parameters it measures
into, the measures that produce them, and for a circuit question the bench --
and cannot declare its answer. The runner routes it to the cheapest level that
can decide it, prepares the chosen tool's native input from the snapshot alone,
runs the tool across a process boundary, reads decimal measurements back, and
returns them through the commit gate as an ordinary transaction. The constraint
over a measured parameter is decided by the gate's constraint check and by
nothing else here.

A second kind of question plugs in without editing this module, through:

- `QuestionDeclaration`, whose hooks are `named_surfaces`, `resolve_surface`,
  `measured_dimension` and `question_fields`, and `Measure`, whose subclasses
  register by their `kind`;
- `METHOD_LEVELS` and `register_method`, which say what level a method routes
  to;
- the `Tool` protocol and `register_tool`, with `Job` (a bundle of files and
  what it rests on), `RawRun` and `Measurement` as what it trades in, and an
  optional `verdict(job, raw) -> Verdict` for a tool that judges rather than
  measures.

The built-in tools, in routing order, are ngspice and xyce (`SpiceTool`, here),
kicad-erc (`fang.rulecheck`) and touchstone (`fang.rf`). `route`, `answer` and
`verify` are the runner; `reenter` is the way back in for a run made
elsewhere, against the same head.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, ClassVar, Iterator, Mapping, Protocol, Sequence, runtime_checkable

from .constraints import CheckStatus, Constraint, Node, Ref
from .diagnostics import (
    SIM_EXCLUSION_WITHOUT_REASON,
    SIM_LOAD_DIMENSION,
    SIM_MISSING_BENCH,
    SIM_QUESTION_RESULT,
    SIM_UNDECLARED_PARAMETER,
    SIM_UNRESOLVED_SURFACE,
    UNIT_DIMENSION_MISMATCH,
    SourceLocation,
    error,
)
from .entities import Component, Verification
from .lang import _caller_location
from .provenance import Confidence, Provenance
from .rationale import Verifies
from .runtime import Status
from .serialization import canonical_bytes, canonical_dumps
from .simulation import (
    Analysis,
    BackendUnavailable,
    BenchItem,
    DeckMeasure,
    Level,
    ModelFile,
    NgspiceBackend,
    NgspiceDialect,
    SimulationError,
    SpiceDialect,
    XyceBackend,
    XyceDialect,
    analysis_from_dict,
    bundle_models,
    compile_plan,
    load_model,
    lower_question,
    primitive_device,
    si_magnitude,
    spice_nodes,
    subcircuit_instance,
)
from .units import SCALE_MISMATCH, Dimension, Quantity, Unit

#: The dimensions a circuit question reasons in.
VOLTAGE = Unit.parse("V").dimension
CURRENT = Unit.parse("A").dimension
RESISTANCE = Unit.parse("Ohm").dimension
TIME = Unit.parse("s").dimension
FREQUENCY = Unit.parse("Hz").dimension


def canonical(value: Any) -> Any:
    """A plain copy in the order the record stream will read it back in.

    A question and a measurement record live in an entity's extensions, and
    the canonical serializer sorts every collection it does not know to be
    ordered. Building them through it means the dictionary in memory is the
    dictionary a reloaded workspace holds, so the two compare equal.
    """
    return json.loads(canonical_dumps(value))


def _quantity(payload: Mapping | None) -> Quantity | None:
    return None if payload is None else Quantity.from_dict(payload)


# --------------------------------------------------------------------------
# Measures
# --------------------------------------------------------------------------

#: Every measure kind, by the name its record carries, so a question read back
#: from a snapshot rebuilds the measure it was declared with.
MEASURES: dict[str, type["Measure"]] = {}


@dataclass(frozen=True)
class Measure:
    """A quantity taken at a part surface and written into one parameter.

    A surface is named the way the program names it, `"rail_out.dc"`, and the
    elaboration resolves it to pins; a measure never names a simulator node.
    """

    surface: str

    #: The name the measure's record carries. Each concrete measure sets it.
    kind: ClassVar[str] = ""

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if cls.__dict__.get("kind"):
            MEASURES[cls.kind] = cls

    def surfaces(self) -> tuple[str, ...]:
        """Every surface this measure reads."""
        return (self.surface,)

    def produces(self, analysis: str | None) -> Dimension | None:
        """The dimension of what this measure produces under an analysis kind,
        or None where that depends on an analysis not yet named."""
        return VOLTAGE

    def logarithmic(self) -> bool:
        """Whether what it produces is a decibel, which no dimension says: a
        decibel goes only into a parameter declared in decibels."""
        return False

    def check(self, analysis: str | None) -> None:
        """Refuse a field whose dimension the analysis cannot give a meaning."""

    def fields(self) -> dict:
        """The measure's own fields, as plain data."""
        return {}

    def as_dict(self) -> dict:
        out = {"kind": self.kind, "surface": self.surface}
        out.update(self.fields())
        return out

    @staticmethod
    def from_dict(payload: Mapping) -> "Measure":
        kind = payload.get("kind")
        if kind not in MEASURES:
            raise ValueError(f"no measure is defined for kind {kind!r}")
        return MEASURES[kind].read(payload)

    @classmethod
    def read(cls, payload: Mapping) -> "Measure":
        return cls(payload["surface"])


def _axis(analysis: str | None) -> Dimension | None:
    """What a window is measured along: time in a transient, frequency in AC."""
    if analysis == "transient":
        return TIME
    if analysis == "ac":
        return FREQUENCY
    return None


def _check_axis(measure: Measure, name: str, quantity: Quantity | None, analysis: str | None) -> None:
    axis = _axis(analysis)
    if quantity is None or axis is None:
        return
    if quantity.dimension != axis:
        raise error(
            UNIT_DIMENSION_MISMATCH,
            f"{type(measure).__name__} at {measure.surface} gives {name} in "
            f"{quantity.unit}, but a {analysis} analysis runs along "
            f"{'time' if axis == TIME else 'frequency'}",
        )


@dataclass(frozen=True)
class _Windowed(Measure):
    """A statistic of the surface's voltage over a window of the analysis.

    A window whose start is not before its end is refused where it is
    written, as an emulation count's is: lowered, it would be a measure the
    simulator takes over nothing, and the declaration's fault would read as
    the run's. Bounds in two dimensions are left to `check`, which names the
    axis each should be along.
    """

    after: Quantity | None = field(default=None, kw_only=True)
    until: Quantity | None = field(default=None, kw_only=True)

    def __post_init__(self) -> None:
        if self.after is None or self.until is None or self.after.dimension != self.until.dimension:
            return
        try:
            start, end = si_magnitude(self.after), si_magnitude(self.until)
        except SimulationError:
            return          # a bound with no one magnitude is refused where it is lowered
        if not start < end:
            raise error(
                SIM_UNRESOLVED_SURFACE,
                f"the {type(self).__name__} window ({self.after}, {self.until}) at "
                f"{self.surface} is empty: its start is not before its end, so it "
                "would measure nothing whatever the circuit did",
                location=_caller_location(3),
            )

    def check(self, analysis: str | None) -> None:
        _check_axis(self, "after", self.after, analysis)
        _check_axis(self, "until", self.until, analysis)

    def fields(self) -> dict:
        out = {}
        if self.after is not None:
            out["after"] = self.after.as_dict()
        if self.until is not None:
            out["until"] = self.until.as_dict()
        return out

    @classmethod
    def read(cls, payload: Mapping) -> "Measure":
        return cls(
            payload["surface"],
            after=_quantity(payload.get("after")),
            until=_quantity(payload.get("until")),
        )


class PeakToPeak(_Windowed):
    """The difference between the highest and the lowest voltage in a window."""

    kind = "peak_to_peak"


class Average(_Windowed):
    """The mean voltage over a window."""

    kind = "average"


class Maximum(_Windowed):
    """The highest voltage in a window."""

    kind = "maximum"


class Minimum(_Windowed):
    """The lowest voltage in a window."""

    kind = "minimum"


@dataclass(frozen=True)
class ValueAt(Measure):
    """The voltage at one point: a time, a frequency, or the operating point."""

    at: Quantity | None = field(default=None, kw_only=True)

    kind = "value_at"

    def check(self, analysis: str | None) -> None:
        _check_axis(self, "at", self.at, analysis)

    def fields(self) -> dict:
        return {"at": self.at.as_dict()} if self.at is not None else {}

    @classmethod
    def read(cls, payload: Mapping) -> "Measure":
        return cls(payload["surface"], at=_quantity(payload.get("at")))


#: How a crossing is counted.
EDGES = ("rising", "falling", "either")


@dataclass(frozen=True)
class Crossing(Measure):
    """Where the surface's voltage crosses a level: a time in a transient, a
    frequency in an AC sweep -- a filter's corner is a crossing of the level
    a decibel table puts it at."""

    level: Quantity = field(kw_only=True)
    edge: str = field(default="either", kw_only=True)
    occurrence: int = field(default=1, kw_only=True)
    after: Quantity | None = field(default=None, kw_only=True)

    kind = "crossing"

    def __post_init__(self) -> None:
        if self.edge not in EDGES:
            raise ValueError(f"a crossing's edge is one of {', '.join(EDGES)}")
        if self.occurrence < 1:
            raise ValueError("a crossing counts occurrences from 1")
        if self.level.dimension != VOLTAGE:
            raise error(
                UNIT_DIMENSION_MISMATCH,
                f"a crossing at {self.surface} is of a voltage level, not "
                f"{self.level.unit}",
            )

    def produces(self, analysis: str | None) -> Dimension | None:
        return _axis(analysis)

    def check(self, analysis: str | None) -> None:
        _check_axis(self, "after", self.after, analysis)

    def fields(self) -> dict:
        out = {
            "level": self.level.as_dict(),
            "edge": self.edge,
            "occurrence": self.occurrence,
        }
        if self.after is not None:
            out["after"] = self.after.as_dict()
        return out

    @classmethod
    def read(cls, payload: Mapping) -> "Measure":
        return cls(
            payload["surface"],
            level=Quantity.from_dict(payload["level"]),
            edge=payload.get("edge", "either"),
            occurrence=int(payload.get("occurrence", 1)),
            after=_quantity(payload.get("after")),
        )


# --------------------------------------------------------------------------
# Resolving the names a question uses
# --------------------------------------------------------------------------


def _walk(module, name: str):
    """Descend a dotted name through child modules as far as it goes.

    Returns the module reached, the segments consumed, and what is left over.
    """
    segments = name.split(".") if name else []
    current = module
    consumed: list[str] = []
    while segments and segments[0] in current.children():
        consumed.append(segments[0])
        current = current.children()[segments.pop(0)]
    return current, consumed, segments


def _signal_role(surface, signal: str) -> str:
    interface = getattr(surface, "interface", None)
    if interface is not None:
        return interface.signal(signal).role
    return "ground" if surface.surface_type == "ground" else "unknown"


def resolve_surface(module, name: str, *, location: SourceLocation | None = None) -> dict:
    """Resolve a part surface, `"rail_out.dc"`, to the pins it lands on.

    The answer names a signal pin and, where the surface has a ground wire, a
    return pin, each as its component's identifier and the pin's vendor name.
    A single-wire surface resolves to its one pin, measured against the
    simulator's ground. A system's own surface has no pins, and is refused by
    name rather than probed somewhere nearby.
    """

    def refuse(reason: str):
        return error(
            SIM_UNRESOLVED_SURFACE,
            f"{name!r} resolves to no pins: {reason}",
            location=location,
        )

    owner, consumed, rest = _walk(module, name)
    if not rest:
        raise refuse("it names a module, not one of its surfaces")
    surface = owner.surfaces().get(rest[0])
    if surface is None:
        raise refuse(f"{type(owner).__name__} has no surface {rest[0]!r}")
    if len(rest) > 2:
        raise refuse("a surface name has at most one signal after it")
    if not owner.pin_map:
        raise refuse(
            f"{rest[0]} is a surface of {type(owner).__name__}, which has no pins; "
            "a system's own surface is not a probe"
        )

    signals = tuple(surface.signals)
    if len(rest) == 2:
        if rest[1] not in signals:
            raise refuse(f"{rest[0]} has no signal {rest[1]!r}")
        positive, returning = rest[1], None
    else:
        live = [s for s in signals if _signal_role(surface, s) != "ground"]
        grounds = [s for s in signals if _signal_role(surface, s) == "ground"]
        # A surface with several live signals names no one net: probing the
        # first declared would measure a net the author may not have meant.
        if len(live) > 1:
            raise refuse(
                f"{rest[0]} carries several signals ({', '.join(live)}); name the one "
                f"measured, as {rest[0]}.<signal>"
            )
        positive = live[0] if live else signals[0]
        returning = grounds[0] if live and grounds else None

    def pin(signal: str) -> dict:
        candidates = owner.pin_map.candidates(rest[0], signal)
        if not candidates:
            raise refuse(f"the pin map of {type(owner).__name__} gives {rest[0]}.{signal} no pin")
        if len(candidates) > 1:
            raise refuse(
                f"the pin map of {type(owner).__name__} gives {rest[0]}.{signal} "
                f"several candidate pins ({', '.join(candidates)}); a probe lands on one"
            )
        return {"component": owner._entity_id, "pin": candidates[0]}

    resolved = {"signal": pin(positive)}
    if returning is not None:
        resolved["return"] = pin(returning)
    return resolved


def resolve_parts(module, name: str, *, location: SourceLocation | None = None) -> list[dict]:
    """Every part a name covers: the part itself, or each part inside a block."""
    owner, consumed, rest = _walk(module, name)
    if rest or not consumed:
        raise error(
            SIM_UNRESOLVED_SURFACE,
            f"{name!r} names no part of {type(module).__name__} to abstract",
            location=location,
        )

    found: list[dict] = []

    def collect(current, path: str) -> None:
        if current.entity_kind == "component":
            found.append({"name": path, "component": current._entity_id})
        for child_name, child in current.children().items():
            collect(child, f"{path}.{child_name}")

    collect(owner, ".".join(consumed))
    if not found:
        raise error(
            SIM_UNRESOLVED_SURFACE,
            f"{name!r} holds no part to abstract",
            location=location,
        )
    return found


# --------------------------------------------------------------------------
# Declaring a question
# --------------------------------------------------------------------------

#: Stands for "no result was given", so that even `result=None` is refused.
_NO_RESULT = object()


class QuestionDeclaration(Verifies):
    """A verification whose result a run produces, never the program.

    The common base of every declared question. It fixes the method, refuses a
    result, checks that every measure writes a parameter its module declares
    and gives no value, resolves every surface while the module tree is still
    in hand, and builds
    the canonical question dictionary that `elaborate` stores in the
    verification's `extensions["question"]`.

    A kind of question extends it through four hooks and nothing else:
    `named_surfaces` lists the surfaces it reads, `resolve_surface` turns one
    into pins, `measured_dimension` says what a measure produces, and
    `question_fields` adds the kind's own fields -- a bench, a scenario.
    """

    #: The verification method this kind of question fixes.
    fixed_method: ClassVar[str] = ""

    def __init__(
        self,
        verifies: str,
        *,
        measures: Mapping[str, Measure],
        abstracted: Sequence[str] = (),
        tool: str | None = None,
        result: object = _NO_RESULT,
    ) -> None:
        if result is not _NO_RESULT:
            raise error(
                SIM_QUESTION_RESULT,
                f"{type(self).__name__} cannot state its own result ({result!r}); "
                "a question's result is produced by a run, and a verification by "
                "inspection or test is declared with Verifies",
                location=self._source,
            )
        super().__init__(verifies, method=self.fixed_method, evidence=(), result="UNKNOWN")
        self.measures = dict(measures)
        self.abstracted = tuple(abstracted)
        self.tool = tool

    # -- the hooks a kind of question extends -------------------------------

    def named_surfaces(self) -> tuple[str, ...]:
        """Every part surface the question reads or drives."""
        return tuple(s for measure in self.measures.values() for s in measure.surfaces())

    def resolve_surface(self, module, name: str) -> dict:
        """One surface as the pins it lands on, recorded at elaboration."""
        return resolve_surface(module, name, location=self._source)

    def measured_dimension(self, measure: Measure) -> Dimension | None:
        """What a measure produces, or None where it is not yet knowable."""
        return measure.produces(None)

    def question_fields(self, module) -> dict:
        """The kind's own fields: a bench, a scenario."""
        return {}

    # -- elaboration --------------------------------------------------------

    def elaborate_question(self, module, *, project_id: str) -> dict:
        """The canonical question dictionary, built where the module tree is.

        Pin maps live on part classes, which the snapshot does not keep; every
        surface is therefore resolved here, so the runner needs the snapshot
        and nothing else.
        """
        declared = type(module)._parameters
        measures = []
        for name, measure in sorted(self.measures.items()):
            parameter = declared.get(name)
            if parameter is None:
                raise error(
                    SIM_UNDECLARED_PARAMETER,
                    f"{self.attribute} measures into {name!r}, which "
                    f"{type(module).__name__} does not declare as a parameter",
                    entities=(module._entity_id,),
                    location=self._source,
                )
            stated = module.value_of(name)
            if stated.known:
                # A value the program gives would be the question's answer,
                # stated rather than produced, and would let the evaluator
                # answer the question with nothing run.
                raise error(
                    SIM_QUESTION_RESULT,
                    f"{self.attribute} measures into {name}, which "
                    f"{type(module).__name__} gives the value {stated.quantity}; a "
                    "measured parameter is declared without a value, and only a "
                    "run gives it one",
                    entities=(module._entity_id,),
                    location=self._source,
                )
            produced = self.measured_dimension(measure)
            if produced is not None and produced != parameter.unit.dimension:
                raise error(
                    UNIT_DIMENSION_MISMATCH,
                    f"{self.attribute} measures {name} with "
                    f"{type(measure).__name__}, which does not produce "
                    f"{parameter.unit}",
                    location=self._source,
                )
            if (
                produced is not None
                and produced.dimensionless
                and measure.logarithmic() != parameter.unit.logarithmic
            ):
                gives = "decibels" if measure.logarithmic() else "a linear ratio"
                raise error(
                    UNIT_DIMENSION_MISMATCH,
                    f"{self.attribute} measures {name} with "
                    f"{type(measure).__name__}, which gives {gives}, but {name} is "
                    f"declared in {parameter.unit}: {SCALE_MISMATCH}",
                    location=self._source,
                )
            measures.append(
                {
                    "name": name,
                    "parameter": f"{module._entity_id}.{name}",
                    "unit": parameter.unit.symbol,
                    "measure": measure.as_dict(),
                }
            )

        abstracted = [
            part
            for name in self.abstracted
            for part in resolve_parts(module, name, location=self._source)
        ]
        question: dict = {
            "method": self.method,
            "measures": measures,
            "surfaces": {
                name: self.resolve_surface(module, name)
                for name in sorted(set(self.named_surfaces()))
            },
            "abstracted": abstracted,
        }
        if self.tool is not None:
            question["tool"] = self.tool
        question.update(self.question_fields(module))
        return canonical(question)


class Simulates(QuestionDeclaration):
    """A circuit question: measured on a bench by a circuit simulator.

    The bench is explicit and nothing about it is defaulted: every supply and
    load at a part surface, the analysis and its window, and the parts it
    deliberately leaves out. A question with no supply still elaborates, and
    is reported as not runnable rather than run against a source nobody chose.
    """

    fixed_method = "simulation"

    def __init__(
        self,
        verifies: str,
        *,
        measures: Mapping[str, Measure],
        supplies: Mapping[str, Quantity] | None = None,
        loads: Mapping[str, Quantity] | None = None,
        analysis: Analysis | None = None,
        abstracted: Sequence[str] = (),
        tool: str | None = None,
        result: object = _NO_RESULT,
    ) -> None:
        super().__init__(
            verifies, measures=measures, abstracted=abstracted, tool=tool, result=result
        )
        self.supplies = dict(supplies or {})
        self.loads = dict(loads or {})
        self.analysis = analysis

        for surface, quantity in sorted(self.supplies.items()):
            if quantity.dimension != VOLTAGE:
                raise error(
                    UNIT_DIMENSION_MISMATCH,
                    f"the supply at {surface} is {quantity}; a supply is a voltage",
                    location=self._source,
                )
        for surface, quantity in sorted(self.loads.items()):
            if quantity.dimension not in (CURRENT, RESISTANCE):
                raise error(
                    SIM_LOAD_DIMENSION,
                    f"the load at {surface} is {quantity}; a load is a current "
                    "drawn or a resistance, nothing else",
                    location=self._source,
                )
        kind = analysis.kind if analysis is not None else None
        for measure in self.measures.values():
            try:
                measure.check(kind)
            except Exception as exc:
                diagnostic = getattr(exc, "diagnostic", None)
                if diagnostic is None:
                    raise
                raise error(diagnostic.code, diagnostic.message, location=self._source) from None

    def named_surfaces(self) -> tuple[str, ...]:
        return super().named_surfaces() + tuple(self.supplies) + tuple(self.loads)

    def measured_dimension(self, measure: Measure) -> Dimension | None:
        return measure.produces(self.analysis.kind if self.analysis is not None else None)

    def question_fields(self, module) -> dict:
        bench: dict = {
            "supplies": [
                {"surface": surface, "quantity": quantity.as_dict()}
                for surface, quantity in sorted(self.supplies.items())
            ],
            "loads": [
                {"surface": surface, "quantity": quantity.as_dict()}
                for surface, quantity in sorted(self.loads.items())
            ],
        }
        if self.analysis is not None:
            bench["analysis"] = self.analysis.as_dict()
        return {"bench": bench}


class Checks(QuestionDeclaration):
    """A rule-check question: an external checker over an artifact the kernel
    lowers -- the schematic it draws.

    Nothing is measured into a parameter; the checker's report is the answer.
    A violation of error severity fails the verification and a warning does
    not. A rule may be excluded, and only with a reason: the evidence records
    the rule, the reason and how many violations it excluded, so an exclusion
    is a stated decision rather than a hidden one.
    """

    fixed_method = "rule check"

    def __init__(
        self,
        verifies: str,
        *,
        tool: str | None = None,
        artifact: str = "schematic",
        excluded: Mapping[str, str] | None = None,
        result: object = _NO_RESULT,
    ) -> None:
        super().__init__(verifies, measures={}, tool=tool, result=result)
        if excluded is not None and not isinstance(excluded, Mapping):
            rules = ", ".join(sorted(str(rule) for rule in excluded))
            raise error(
                SIM_EXCLUSION_WITHOUT_REASON,
                f"{type(self).__name__} excludes {rules} without reasons; an "
                "exclusion maps each rule to why it does not apply",
                location=self._source,
            )
        self.excluded = dict(excluded or {})
        for rule, reason in sorted(self.excluded.items()):
            if not isinstance(reason, str) or not reason.strip():
                raise error(
                    SIM_EXCLUSION_WITHOUT_REASON,
                    f"{type(self).__name__} excludes {rule!r} without a reason; "
                    "a rule is set aside only with the reason it does not apply",
                    location=self._source,
                )
        self.artifact = artifact

    def question_fields(self, module) -> dict:
        return {
            "check": {
                "artifact": self.artifact,
                "excluded": [
                    {"rule": rule, "reason": reason.strip()}
                    for rule, reason in sorted(self.excluded.items())
                ],
            }
        }


@dataclass(frozen=True)
class ReturnLoss(Measure):
    """How much of what is sent into a port comes back: -20 log10 |Gamma|, in dB.

    Taken at a part carrying a Touchstone model, at one frequency, through the
    matching parts named in order from the port toward the model, and against
    a reference impedance, 50 Ohm unless the question says otherwise. Each
    matching part is a series or a shunt element by how the graph connects it,
    and its value is the one the graph holds; parts that do not form that
    ladder, in the order named, are refused when the question is prepared.
    """

    at: Quantity = field(kw_only=True)
    through: tuple[str, ...] = field(default=(), kw_only=True)
    reference: Quantity = field(
        default_factory=lambda: Quantity.scalar("50", "Ohm"), kw_only=True
    )

    kind = "return_loss"

    def __post_init__(self) -> None:
        object.__setattr__(self, "through", tuple(self.through))
        if self.at.dimension != FREQUENCY:
            raise error(
                UNIT_DIMENSION_MISMATCH,
                f"a return loss at {self.surface} is taken at a frequency, not {self.at.unit}",
            )
        if self.reference.dimension != RESISTANCE:
            raise error(
                UNIT_DIMENSION_MISMATCH,
                f"a return loss at {self.surface} is against a resistance, not "
                f"{self.reference.unit}",
            )

    def produces(self, analysis: str | None) -> Dimension | None:
        return Unit.parse("dB").dimension

    def logarithmic(self) -> bool:
        return True

    def fields(self) -> dict:
        # The matching parts are a chain, so each carries its position: the
        # record stream sorts a list it does not know to be ordered.
        return {
            "at": self.at.as_dict(),
            "reference": self.reference.as_dict(),
            "through": [
                {"position": position, "part": part}
                for position, part in enumerate(self.through)
            ],
        }

    @classmethod
    def read(cls, payload: Mapping) -> "Measure":
        chain = sorted(payload.get("through", ()), key=lambda link: link["position"])
        return cls(
            payload["surface"],
            at=Quantity.from_dict(payload["at"]),
            through=tuple(link["part"] for link in chain),
            reference=Quantity.from_dict(payload["reference"]),
        )


class Evaluates(QuestionDeclaration):
    """A question over a data model a part carries -- a vendor's or an
    instrument's network parameters -- answered by reading the data and
    composing the named parts in closed form, at the equation level.

    Each matching part a measure names is resolved here, while the module tree
    is in hand, to the one component it is.
    """

    fixed_method = "analysis"

    def question_fields(self, module) -> dict:
        parts: dict[str, str] = {}
        for measure in self.measures.values():
            for name in getattr(measure, "through", ()):
                found = resolve_parts(module, name, location=self._source)
                if len(found) != 1:
                    raise error(
                        SIM_UNRESOLVED_SURFACE,
                        f"{name!r} holds {len(found)} parts; a matching element is one part",
                        location=self._source,
                    )
                parts[name] = found[0]["component"]
        return {
            "evaluation": {
                "parts": [
                    {"name": name, "component": component}
                    for name, component in sorted(parts.items())
                ]
            }
        }


# --------------------------------------------------------------------------
# A question, read from the graph
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MeasureEntry:
    """One measure of a question as the graph records it."""

    name: str
    parameter: str          # "<entity id>.<parameter name>"
    unit: str
    record: Mapping[str, Any]

    @property
    def entity(self) -> str:
        return self.parameter.split(".", 1)[0]

    @property
    def attr(self) -> str:
        return self.parameter.split(".", 1)[1]

    @property
    def measure(self) -> Measure:
        """The measure rebuilt from its record, through `Measure.from_dict`."""
        return Measure.from_dict(self.record)


@dataclass(frozen=True)
class Question:
    """A declared question, read from its verification entity.

    Everything a tool needs is here, because the question dictionary was
    built with every surface already resolved: the runner works from the
    snapshot alone.
    """

    id: str
    verifies: str
    method: str
    data: Mapping[str, Any]
    path: str = ""
    source_location: SourceLocation | None = None

    @classmethod
    def of(cls, entity) -> "Question | None":
        """The question a verification declares, or None for one that is not
        a question -- a verification by inspection or test, which is never
        routed."""
        if not isinstance(entity, Verification) or "question" not in entity.extensions:
            return None
        return cls(
            entity.id,
            entity.verifies,
            entity.method,
            entity.extensions["question"],
            str(entity.identity.path or ""),
            entity.source_location,
        )

    @property
    def label(self) -> str:
        return self.path or self.id

    @property
    def tool(self) -> str | None:
        """The tool the question names, if it names one."""
        return self.data.get("tool")

    @property
    def bench(self) -> Mapping[str, Any]:
        return self.data.get("bench", {})

    @property
    def measures(self) -> tuple[MeasureEntry, ...]:
        return tuple(
            MeasureEntry(entry["name"], entry["parameter"], entry["unit"], entry["measure"])
            for entry in sorted(self.data.get("measures", ()), key=lambda e: e["name"])
        )

    @property
    def parameters(self) -> tuple[tuple[str, str], ...]:
        """Every measured parameter, as (entity id, parameter name)."""
        return tuple((entry.entity, entry.attr) for entry in self.measures)

    def surface(self, name: str) -> Mapping[str, Any] | None:
        return self.data.get("surfaces", {}).get(name)


def questions(snapshot) -> tuple[Question, ...]:
    """Every declared question in a snapshot, in identifier order."""
    found = (Question.of(entity) for entity in snapshot.entities.values())
    return tuple(sorted((q for q in found if q is not None), key=lambda q: q.id))


def _references(node: Node | None) -> set[tuple[str, str]]:
    """Every (entity, attribute) an expression reads."""
    if node is None:
        return set()
    if isinstance(node, Ref):
        return {(node.ref, node.attr)}
    found: set[tuple[str, str]] = set()
    for arg in getattr(node, "args", ()):
        found |= _references(arg)
    return found


def constraints_over(snapshot, parameters: Sequence[tuple[str, str]]) -> tuple[Constraint, ...]:
    """The constraints whose expression or applicability reads a parameter."""
    wanted = set(parameters)
    return tuple(
        sorted(
            (
                entity
                for entity in snapshot.entities.values()
                if isinstance(entity, Constraint)
                and (
                    _references(entity.expression) | _references(entity.applicability)
                )
                & wanted
            ),
            key=lambda c: c.id,
        )
    )


# --------------------------------------------------------------------------
# The protocol
# --------------------------------------------------------------------------


class NotRunnable(Exception):
    """A question its tool cannot prepare, refused naming what is missing.

    Nothing is assumed in place of what the question left out.
    """

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.code = code


class ToolUnavailable(Exception):
    """The tool is not installed. Reported as unsupported, never substituted."""


@dataclass(frozen=True)
class Job:
    """A prepared run: the tool's native input, and what it rests on.

    A job is a bundle rather than one text: `files` maps each relative path to
    its content, so a tool whose input is several files -- a platform, a
    script, a firmware image -- is prepared the same way as a SPICE deck,
    which is one file. Beside the files are the assumptions the run makes, the
    coverage gaps it leaves, the digest of every input the snapshot does not
    hold (a model file, a firmware image), and `extra`, the tool's own record
    fields, which the evidence carries as they are.

    The hash covers all of that, and nothing that varies by machine: where an
    input is read from on this machine (`sources`) and which snapshot the job
    was prepared against (`snapshot`, whose hash covers the checkout's path)
    are kept beside it, not in it.
    """

    tool: str
    question: Question
    snapshot: str
    files: Mapping[str, str | bytes]
    assumptions: tuple[str, ...] = ()
    coverage_gaps: tuple[str, ...] = ()
    inputs: Mapping[str, str] = field(default_factory=dict)
    extra: Mapping[str, str] = field(default_factory=dict)
    confidence: Decimal = Decimal(1)
    sources: Mapping[str, str] = field(default_factory=dict, compare=False)

    @classmethod
    def single(
        cls, tool: str, question: Question, snapshot: str, name: str, text: str | bytes, **kwargs
    ) -> "Job":
        """A job whose native input is one file."""
        return cls(tool, question, snapshot, {name: text}, **kwargs)

    @property
    def input(self) -> str | bytes:
        """The native input, where the job is one file."""
        if len(self.files) != 1:
            raise ValueError(
                f"this {self.tool} job is a bundle of {len(self.files)} files; "
                "read them from files"
            )
        return next(iter(self.files.values()))

    def manifest(self) -> dict:
        """What the hash covers, as canonical data."""

        def digest(content: str | bytes) -> str:
            data = content.encode("utf-8") if isinstance(content, str) else content
            return "sha256:" + hashlib.sha256(data).hexdigest()

        return {
            "tool": self.tool,
            "question": self.question.id,
            "asks": dict(self.question.data),
            "files": {path: digest(content) for path, content in sorted(self.files.items())},
            "inputs": dict(sorted(self.inputs.items())),
            "assumptions": list(self.assumptions),
            "coverage_gaps": list(self.coverage_gaps),
            "extra": dict(sorted(self.extra.items())),
            "confidence": self.confidence,
        }

    @property
    def hash(self) -> str:
        return "sha256:" + hashlib.sha256(canonical_bytes(self.manifest())).hexdigest()


@dataclass(frozen=True)
class RawRun:
    """What a run produced, unread: the version, the exit, the output."""

    tool: str
    version: str
    exit_status: int
    stdout: str = ""
    stderr: str = ""
    outputs: Mapping[str, str | bytes] = field(default_factory=dict)
    status: Status = Status.SUCCEEDED
    message: str = ""


@dataclass(frozen=True)
class Measurement:
    """One measure's answer: a quantity, or no value and the reason why.

    A measurement with no value is still a measurement -- the measure was
    asked for and the run could not produce it, or withdrew it -- and its
    reason is recorded on the evidence. Only a measurement with a value ever
    sets a parameter.
    """

    name: str
    parameter: str
    quantity: Quantity | None
    tool: str
    version: str
    job: str
    confidence: Decimal
    reason: str | None = None

    def __post_init__(self) -> None:
        if (self.quantity is None) == (self.reason is None):
            raise ValueError("a measurement carries a quantity or a reason, never both")

    @property
    def measured(self) -> bool:
        return self.quantity is not None

    @property
    def entity(self) -> str:
        return self.parameter.split(".", 1)[0]

    @property
    def attr(self) -> str:
        return self.parameter.split(".", 1)[1]

    def as_record(self) -> dict:
        """The measure's line in the evidence's measurement record."""
        out: dict = {"name": self.name, "parameter": self.parameter}
        if self.quantity is None:
            out["reason"] = self.reason
            return out
        quantity = self.quantity.as_dict()
        out["unit"] = quantity.pop("unit")
        if quantity.get("kind") == "scalar":
            out["value"] = quantity["value"]
        else:
            out.update(quantity)
        return out


@dataclass(frozen=True)
class Verdict:
    """A tool's own judgement of a question that measures nothing.

    A rule checker answers with what it found rather than with a number: its
    result, the fields its evidence carries beside the measurement record's
    own -- the violations, the exclusions and their counts -- and the lines
    a listing shows. A tool offers one by defining `verdict(job, raw)`; for a
    question with measured parameters, the constraints over them still decide,
    and a failing verdict can only make the result worse.
    """

    result: str
    record: Mapping[str, Any] = field(default_factory=dict)
    summary: tuple[str, ...] = ()


@runtime_checkable
class Tool(Protocol):
    """A verification tool, behind the one protocol every tool sits behind.

    `prepare` is a lowering and is deterministic: the same snapshot and
    question give a byte-identical job. `run` is the only method that leaves
    the process. `read` is a parser that produces decimal quantities and
    nothing the raw output did not contain. A tool that is not installed says
    so through `available`, and is reported unsupported by name.
    """

    name: str
    level: Level

    def covers(self, question: Question) -> bool: ...

    def available(self) -> bool: ...

    def version(self) -> str: ...

    def prepare(self, snapshot, question: Question, *, traits=None) -> Job: ...

    def run(self, job: Job, *, workspace: Path) -> RawRun: ...

    def read(self, job: Job, raw: RawRun) -> tuple[Measurement, ...]: ...


# --------------------------------------------------------------------------
# Confidence
# --------------------------------------------------------------------------

#: A model's confidence, by the confidence its most recent provenance record
#: states. A run's confidence is the least of the models it rests on, and a
#: run over primitives rests on none and is 1. The scale is this tool's to
#: state and the evidence records it; nothing here ever raises a confidence.
MODEL_CONFIDENCE: Mapping[Confidence, Decimal] = {
    Confidence.ASSERTED: Decimal("1"),
    Confidence.INFERRED: Decimal("0.8"),
    Confidence.UNVERIFIED: Decimal("0.5"),
}


def assumed_provenance(reason: str) -> Provenance:
    """The provenance of a model nobody has verified: an assumption, stated.

    One record, authored by the program's author, whose confidence is
    unverified. A run resting on such a model reports the confidence
    `MODEL_CONFIDENCE` gives it, and never more.
    """
    from datetime import datetime, timezone

    from .provenance import Actor, ActorKind, ProvenanceOrigin, ProvenanceRecord

    return Provenance().append(
        ProvenanceRecord(
            ProvenanceOrigin.AUTHORED,
            reason,
            Actor(ActorKind.HUMAN, "program author"),
            "REV-000000",
            datetime(1970, 1, 1, tzinfo=timezone.utc),
            confidence=Confidence.UNVERIFIED,
        )
    )


def model_confidence(provenance: Provenance) -> Decimal:
    """How far a run can trust a model, from where the model came from.

    A model with no provenance at all is an assumption, exactly as a claim
    with no citation is, and is treated as one.
    """
    records = provenance.records
    if not records:
        return MODEL_CONFIDENCE[Confidence.UNVERIFIED]
    return MODEL_CONFIDENCE[records[-1].confidence or Confidence.ASSERTED]


# --------------------------------------------------------------------------
# Routing
# --------------------------------------------------------------------------

#: Which level a question's method names. Extended, never edited, by a module
#: that adds a method: `register_method("emulation", Level.BEHAVIOURAL)`.
METHOD_LEVELS: dict[str, Level] = {
    "simulation": Level.CIRCUIT,
    "rule check": Level.EXTERNAL,
    "analysis": Level.EQUATION,
}


def register_method(method: str, level: Level) -> None:
    """Name the level a verification method routes to."""
    existing = METHOD_LEVELS.get(method)
    if existing is not None and existing is not level:
        raise ValueError(
            f"the method {method!r} already routes to the {existing.label} level"
        )
    METHOD_LEVELS[method] = level


class ToolRegistry:
    """The verification tools, in the order routing tries them.

    Distinct from `fang.runtime.ToolRegistry`, which holds the tools a plan
    calls. Order is part of the contract: at a level, the first registered
    tool that covers a question is chosen, whether or not it is installed, so
    the route is the same on every machine and a missing tool is reported
    rather than replaced.
    """

    def __init__(self, tools: Sequence[Tool] = (), *, builtins=None) -> None:
        self._tools: list[Tool] = []
        # The built-in tools live in modules that import this one, so a
        # registry may name them by a function it calls the first time it is
        # used; they always come first, before anything registered later.
        self._builtins = builtins
        for tool in tools:
            self.register(tool)

    def _load(self) -> list[Tool]:
        if self._builtins is not None:
            builtins, self._builtins = self._builtins, None
            for tool in builtins():
                self.register(tool)
        return self._tools

    def register(self, tool: Tool, *, before: str | None = None) -> Tool:
        """Add a tool after those already registered, or before a named one.

        A tool registered again under its name replaces the first in place.
        """
        self._load()
        for index, existing in enumerate(self._tools):
            if existing.name == tool.name:
                self._tools[index] = tool
                return tool
        if before is not None:
            for index, existing in enumerate(self._tools):
                if existing.name == before:
                    self._tools.insert(index, tool)
                    return tool
            raise ValueError(f"no tool named {before!r} is registered to go before")
        self._tools.append(tool)
        return tool

    def get(self, name: str) -> Tool | None:
        return next((tool for tool in self._load() if tool.name == name), None)

    def names(self) -> list[str]:
        """The tools in routing order."""
        return [tool.name for tool in self._load()]

    def __iter__(self) -> Iterator[Tool]:
        return iter(list(self._load()))

    def __contains__(self, name: object) -> bool:
        return any(tool.name == name for tool in self._load())

    def __len__(self) -> int:
        return len(self._load())


#: The tool name recorded for an answer the constraint evaluator gave.
EVALUATOR = "evaluator"


@dataclass(frozen=True)
class Route:
    """Where a question goes: the level and the tool, or why nowhere.

    `decided` is an answer at the equation level by the constraint evaluator,
    for which no tool is prepared or run.
    """

    question: str
    level: Level | None
    tool: str | None
    reason: str
    decided: bool = False

    @property
    def routed(self) -> bool:
        return self.tool is not None

    def as_dict(self) -> dict:
        out: dict = {"question": self.question, "reason": self.reason, "decided": self.decided}
        if self.level is not None:
            out["level"] = self.level.label
        if self.tool is not None:
            out["tool"] = self.tool
        return out


def constraint_statuses(snapshot, question: Question, resolve=None) -> dict[str, CheckStatus]:
    """How each constraint over the question's parameters evaluates now."""
    resolve = resolve or snapshot.resolver()
    return {
        constraint.id: constraint.evaluate(resolve)
        for constraint in constraints_over(snapshot, question.parameters)
    }


def unmeasured(snapshot, question: Question, resolve=None) -> list[str]:
    """The question's measures whose parameter holds no known value."""
    resolve = resolve or snapshot.resolver()
    out = []
    for entry in question.measures:
        value = resolve(entry.entity, entry.attr)
        if value is None or not value.known or value.quantity is None:
            out.append(entry.name)
    return out


def route(snapshot, question: Question, *, tools: ToolRegistry | None = None) -> Route:
    """Route a question to the cheapest level that can decide it.

    If every measured parameter already holds a value and every constraint
    over them already evaluates to a decided result, the evaluator is the
    answer and no tool runs. A parameter with no value and no constraint over
    it is a measure nobody has taken, and the evaluator cannot stand in for
    it. Otherwise the method names the level, and the first registered tool
    at that level that covers the question is chosen -- the one the question
    names, if it names one. A question nothing covers is unroutable; it is
    never answered by a tool at another level, because a cheaper answer is not
    the same answer.
    """
    tools = TOOLS if tools is None else tools
    statuses = constraint_statuses(snapshot, question)
    if (
        statuses
        and not unmeasured(snapshot, question)
        and all(status is not CheckStatus.UNKNOWN for status in statuses.values())
    ):
        return Route(
            question.id,
            Level.EQUATION,
            EVALUATOR,
            "every measured parameter holds a value and every constraint over "
            "them is already decided; nothing runs",
            decided=True,
        )

    level = METHOD_LEVELS.get(question.method)
    if level is None:
        return Route(
            question.id,
            None,
            None,
            f"no verification level is registered for the method {question.method!r}",
        )
    for tool in tools:
        if tool.level is not level:
            continue
        if question.tool is not None and tool.name != question.tool:
            continue
        if tool.covers(question):
            return Route(
                question.id,
                level,
                tool.name,
                f"{question.method} is answered at the {level.label} level, and "
                f"{tool.name} is the first registered tool there that covers it",
            )
    named = f" named {question.tool}" if question.tool is not None else ""
    return Route(
        question.id,
        level,
        None,
        f"no registered tool{named} at the {level.label} level covers it",
    )


# --------------------------------------------------------------------------
# SPICE
# --------------------------------------------------------------------------


def _si(quantity: Quantity | None) -> Decimal | None:
    return None if quantity is None else si_magnitude(quantity)


def _measured_unit(measure: Measure, analysis: str) -> str:
    """The SI unit a SPICE measure reports in."""
    produced = measure.produces(analysis)
    if produced == TIME:
        return "s"
    if produced == FREQUENCY:
        return "Hz"
    return "V"


@dataclass
class SpiceTool:
    """A SPICE simulator answering circuit questions.

    The preparation is shared -- the plan, the devices, each modelled part's
    subcircuit instance, and the bench -- and the dialect writes what differs:
    the options, the analysis, the measurement lines, and how the output is
    read. A second SPICE simulator is a second dialect and backend, and the
    same circuit.
    """

    name: str
    dialect: SpiceDialect
    backend: Any
    level: Level = Level.CIRCUIT

    def covers(self, question: Question) -> bool:
        if question.method != "simulation":
            return False
        analysis = question.bench.get("analysis")
        return analysis is None or analysis.get("kind") in self.dialect.analyses

    def available(self) -> bool:
        return self.backend.available()

    def version(self) -> str:
        try:
            return self.backend.version()
        except BackendUnavailable as exc:
            raise ToolUnavailable(str(exc)) from None

    # -- preparation --------------------------------------------------------

    def prepare(self, snapshot, question: Question, *, traits=None) -> Job:
        from .netlist import compile_netlist
        from .traits import TraitRegistry

        traits = traits or TraitRegistry()
        bench = question.bench
        if not bench.get("supplies"):
            raise NotRunnable(
                f"{question.label} names no supply; a circuit question runs only "
                "against the sources it names, and none is assumed",
                code=SIM_MISSING_BENCH,
            )
        if "analysis" not in bench:
            raise NotRunnable(
                f"{question.label} names no analysis; its window is not defaulted",
                code=SIM_MISSING_BENCH,
            )
        analysis = analysis_from_dict(bench["analysis"])

        named = [entry.measure.surface for entry in question.measures]
        named += [item["surface"] for item in bench.get("supplies", ())]
        named += [item["surface"] for item in bench.get("loads", ())]
        for surface in named:
            resolved = question.surface(surface)
            if not resolved or "signal" not in resolved:
                raise NotRunnable(
                    f"{question.label} names {surface!r}, which resolves to no pins",
                    code=SIM_UNRESOLVED_SURFACE,
                )

        abstracted = sorted({part["component"] for part in question.data.get("abstracted", ())})
        try:
            plan = compile_plan(
                snapshot, backend=self.name, analysis=analysis, traits=traits,
                abstracted=abstracted,
            )
            netlist = compile_netlist(snapshot, traits=traits)
            nodes = spice_nodes(snapshot, netlist)
            designator_of = {c.entity_id: c.designator for c in netlist.components}

            def node(pin: Mapping[str, str]) -> str:
                return nodes[(designator_of[pin["component"]], pin["pin"])]

            def ends(surface: str) -> tuple[str, str]:
                resolved = question.surface(surface)
                back = resolved.get("return")
                return node(resolved["signal"]), node(back) if back else "0"

            models = bundle_models(
                {
                    use.component: load_model(
                        snapshot.entities[use.component], traits.get(use.component, "simulatable")
                    )
                    for use in plan.models
                    if use.source
                },
                designator_of,
            )
            devices = self._devices(snapshot, plan, netlist, nodes, models, traits)

            items = [
                BenchItem(role, item["surface"], Quantity.from_dict(item["quantity"]), *ends(item["surface"]))
                for role, key in (("supply", "supplies"), ("load", "loads"))
                for item in bench.get(key, ())
            ]
            measures = []
            for index, entry in enumerate(question.measures):
                measure = entry.measure
                positive, negative = ends(measure.surface)
                level = getattr(measure, "level", None)
                measures.append(
                    DeckMeasure(
                        f"fang_m{index}",
                        measure.kind,
                        positive,
                        negative,
                        after=_si(getattr(measure, "after", None)),
                        until=_si(getattr(measure, "until", None)),
                        at=_si(getattr(measure, "at", None)),
                        level=_si(level),
                        edge=getattr(measure, "edge", "either"),
                        occurrence=getattr(measure, "occurrence", 1),
                    )
                )

            title = [
                f"fang question {question.label}",
                f"answers {question.id} for {question.verifies} by {question.method}",
            ]
            title += [
                f"{part['name']} ({part['component']}) is abstracted; no device emitted"
                for part in sorted(question.data.get("abstracted", ()), key=lambda p: p["name"])
            ]
            title += [f"{m.slot} measures {entry.name}" for m, entry in zip(measures, question.measures)]
            deck = lower_question(
                title=title,
                devices=devices,
                bench=items,
                models=list(models.values()),
                analysis=analysis,
                measures=measures,
                dialect=self.dialect,
                options=plan.options,
            )
        except SimulationError as exc:
            raise NotRunnable(f"{question.label}: {exc}", code=exc.code) from None

        return Job.single(
            self.name,
            question,
            snapshot.hash,
            "deck.cir",
            deck,
            assumptions=self._assumptions(snapshot, question, analysis, plan, traits),
            coverage_gaps=self._coverage_gaps(snapshot, question, analysis, plan, traits),
            inputs={model.path: model.digest for model in models.values()},
            sources={model.path: model.location for model in models.values()},
            confidence=self._confidence(plan, traits),
        )

    def _devices(self, snapshot, plan, netlist, nodes, models: Mapping[str, ModelFile], traits) -> list[str]:
        """One line per part in scope: an instance, a primitive, or a note."""
        from .simulation import _is_primitive

        scope = set(plan.scope)
        abstracted = set(plan.abstracted)
        pins_of: dict[str, list[str]] = {}
        for entity in snapshot.entities.values():
            if entity.kind == "pin":
                pins_of.setdefault(entity.owner, []).append(entity.vendor_name)
        net_of = {
            (node.designator, node.pin): net.name for net in netlist.nets for node in net.nodes
        }
        lines = []
        for component in netlist.components:
            if component.entity_id not in scope or component.entity_id in abstracted:
                continue
            entity: Component = snapshot.entities[component.entity_id]
            designator = component.designator
            pins = {
                pin: nodes[(designator, pin)] for pin in sorted(pins_of.get(entity.id, ()))
            }
            model = models.get(entity.id)
            if model is not None:
                trait = traits.get(entity.id, "simulatable")
                nets = {
                    pin: net_of[(designator, pin)] for pin in pins if (designator, pin) in net_of
                }
                lines.append(subcircuit_instance(designator, model, trait.pin_map, pins, nets))
                continue
            if not _is_primitive(entity):
                raise SimulationError(
                    f"{designator}'s model names no file to instantiate, and SPICE "
                    "has no device of its own for it"
                )
            terminals = sorted(pins)
            if len(terminals) < 2:
                lines.append(f"* {designator} has fewer than two terminals and emits no device")
                continue
            lines.append(
                primitive_device(entity, designator, [pins[t] for t in terminals[:2]])
            )
        return lines

    def _assumptions(self, snapshot, question, analysis, plan, traits) -> tuple[str, ...]:
        """Every bench item, the analysis, the solver, and each model's conditions."""
        bench = question.bench
        out = []
        for item in bench.get("supplies", ()):
            quantity = Quantity.from_dict(item["quantity"])
            out.append(f"a {quantity} supply at {item['surface']}")
        for item in bench.get("loads", ()):
            quantity = Quantity.from_dict(item["quantity"])
            if quantity.dimension == CURRENT:
                out.append(f"a {quantity} load drawn from {item['surface']}")
            else:
                out.append(f"a {quantity} load across {item['surface']}")
        if analysis.kind == "ac":
            out.append("each supply is also the AC stimulus, at its own magnitude")
        out.append(f"{analysis.kind} analysis: {analysis.directive().lstrip('.')}")
        out.append(
            "solver options "
            + " ".join(f"{name}={value}" for name, value in sorted(plan.options.items()))
        )
        for use in plan.models:
            trait = traits.get(use.component, "simulatable")
            label = _label(snapshot, use.component)
            for name, condition in sorted((trait.conditions or {}).items()):
                out.append(f"{label}'s model holds for {name} {condition}")
            if use.distribution_restricted:
                out.append(f"{label}'s model forbids redistribution and is referenced, not inlined")
        return tuple(out)

    def _coverage_gaps(self, snapshot, question, analysis, plan, traits) -> tuple[str, ...]:
        """Every abstracted part, everything a model leaves out, and the
        limit of the analysis itself."""
        out = [
            f"{_label(snapshot, component)} is abstracted, not modelled"
            for component in plan.abstracted
        ]
        for use in plan.models:
            trait = traits.get(use.component, "simulatable")
            label = _label(snapshot, use.component)
            out.extend(f"{label}'s model: {item}" for item in trait.not_modelled)
        if analysis.kind == "operating_point":
            out.append("an operating point says nothing about dynamic behaviour")
        return tuple(sorted(out))

    def _confidence(self, plan, traits) -> Decimal:
        confidences = [
            model_confidence(traits.get(use.component, "simulatable").provenance)
            for use in plan.models
        ]
        return min(confidences, default=Decimal(1))

    # -- the run ------------------------------------------------------------

    def run(self, job: Job, *, workspace: Path) -> RawRun:
        """Run the deck across a process boundary, on copies of its inputs."""
        if not self.backend.available():
            raise ToolUnavailable(
                f"{self.name} is not installed; the question is unsupported and "
                "nothing else answers it"
            )
        workspace.mkdir(parents=True, exist_ok=True)
        for path, location in sorted(job.sources.items()):
            target = workspace / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(location, target)
        raw = self.backend.run(job.input, workspace=workspace)
        status = Status.SUCCEEDED if raw.exit_status == 0 else Status.FAILED
        return RawRun(
            self.name,
            raw.version,
            raw.exit_status,
            stdout=raw.stdout,
            outputs=dict(getattr(raw, "outputs", {}) or {}),
            status=status,
            message="" if raw.exit_status == 0 else f"{self.name} exited with status {raw.exit_status}",
        )

    def read(self, job: Job, raw: RawRun) -> tuple[Measurement, ...]:
        """Read each measure's number from the output, in its parameter's unit."""
        analysis = analysis_from_dict(job.question.bench["analysis"]).kind
        entries = job.question.measures
        slots = [DeckMeasure(f"fang_m{index}", entry.measure.kind, "") for index, entry in enumerate(entries)]
        found = (
            self.dialect.parse(raw.stdout, slots, outputs=raw.outputs)
            if raw.status is Status.SUCCEEDED
            else {}
        )
        out = []
        for slot, entry in zip(slots, entries):
            value = found.get(slot.slot)
            quantity, reason = None, None
            if raw.status is not Status.SUCCEEDED:
                reason = f"the run did not complete: {raw.message or raw.status.value}"
            elif isinstance(value, Decimal):
                measured = Quantity.scalar(value, _measured_unit(entry.measure, analysis))
                quantity, _ = measured.converted_to(entry.unit)
            else:
                reason = value or f"{self.name}'s output does not report it"
            out.append(
                Measurement(
                    entry.name, entry.parameter, quantity, self.name, raw.version,
                    job.hash, job.confidence, reason,
                )
            )
        return tuple(out)


def _label(snapshot, entity_id: str) -> str:
    """An entity as a person finds it in the program: its semantic path."""
    entity = snapshot.entities.get(entity_id)
    if entity is None:
        return entity_id
    return str(entity.identity.path or entity_id)


#: ngspice, the first tool on the spine.
NGSPICE = SpiceTool("ngspice", NgspiceDialect(), NgspiceBackend())

#: Xyce, the same circuit through a second SPICE dialect. It comes after
#: ngspice, so it answers a question that names it, or one ngspice does not
#: cover; where it is not installed such a question is reported unsupported.
XYCE = SpiceTool("xyce", XyceDialect(), XyceBackend())


def builtin_tools() -> tuple[Tool, ...]:
    """The tools fang ships, in their documented routing order: ngspice and
    xyce at the circuit level, kicad-erc at the external level, and
    touchstone at the equation level."""
    from .rf import TOUCHSTONE
    from .rulecheck import KICAD_ERC

    return (NGSPICE, XYCE, KICAD_ERC, TOUCHSTONE)


def default_tools() -> ToolRegistry:
    """A registry holding the built-in tools and nothing else."""
    return ToolRegistry(builtin_tools())


#: The registry `route` and the runner use unless handed another. A module
#: that brings a tool adds it here with `register_tool` when it is imported.
TOOLS = ToolRegistry(builtins=builtin_tools)


def register_tool(tool: Tool, *, before: str | None = None, registry: ToolRegistry | None = None) -> Tool:
    """Make a tool available to routing, after the tools already registered.

    The documented order is the built-ins first -- ngspice, xyce, kicad-erc,
    touchstone -- and then each tool in the order it registers; `before`
    names a tool to precede instead.
    """
    return (TOOLS if registry is None else registry).register(tool, before=before)


# --------------------------------------------------------------------------
# Re-entry through the gate
# --------------------------------------------------------------------------

#: The fields a measurement record defines. A tool's `extra` fields sit beside
#: them in the record and may not take one of their names, save `ran`, which a
#: tool may state through its job and the record then carries as its own.
RECORD_FIELDS = frozenset(
    {
        "tool", "level", "job", "status", "ran", "exit_status", "confidence",
        "measures", "assumptions", "coverage_gaps", "inputs", "message",
    }
)

#: Where a run happened, as RFC 3's record names it: here, or on a hosted
#: runner whose isolation is stronger. Every record says which.
RAN = ("local", "hosted")


def evidence_identity(snapshot, question: Question, job: Job, version: str, *, attempt: int = 0):
    """The identity of one run's evidence.

    A function of the job and the tool's version, and nothing else, so the
    same run is the same evidence and two versions of a tool are two pieces
    of evidence, not one. A run that did not complete may be tried again; each
    later attempt at the same job is its own evidence, numbered.
    """
    from .identity import derive

    digest = hashlib.sha256(f"{job.hash}\n{job.tool}\n{version}".encode()).hexdigest()[:12]
    base = question.path or f"verification.{question.id.replace('-', '_')}"
    suffix = f"_retry{attempt}" if attempt else ""
    return derive(
        snapshot.project_id,
        "evidence",
        f"{base}.run_{digest}{suffix}",
        display_name=f"{base.rsplit('.', 1)[-1]} run",
    )


def _attempts(snapshot, question: Question, job: Job, version: str) -> list[str]:
    """The evidence already recorded for this job on this version, in order."""
    found = []
    while True:
        identity = evidence_identity(snapshot, question, job, version, attempt=len(found))
        if identity.id not in snapshot.entities:
            return found
        found.append(identity.id)


def measurement_record(
    job: Job, raw: RawRun, measurements: Sequence[Measurement], level: Level,
    *, verdict: Verdict | None = None,
) -> dict:
    """The measurement record a run's evidence carries.

    The tool and its version, the level, the job's hash, the run's terminal
    status, where it ran, its confidence, each measure with its quantity or
    the reason it has none, the assumptions, the coverage gaps, and the
    digest of every input the snapshot does not hold -- with the tool's own
    fields beside them. A run is local unless its tool's job says it was
    hosted; the record carries that once, as its own field.
    """
    extra = dict(job.extra)
    ran = extra.pop("ran", "local")
    if ran not in RAN:
        raise ValueError(f"{job.tool} says it ran {ran!r}; a run is one of {', '.join(RAN)}")
    judged = dict(verdict.record) if verdict is not None else {}
    clashes = sorted((RECORD_FIELDS & (set(extra) | set(judged))) | (set(extra) & set(judged)))
    if clashes:
        raise ValueError(
            f"{job.tool}'s record fields {', '.join(clashes)} would overwrite "
            "fields the measurement record already holds"
        )
    record: dict = {
        "tool": {"name": job.tool, "version": raw.version},
        "level": level.label,
        "job": job.hash,
        "status": raw.status.value,
        "ran": ran,
        "exit_status": raw.exit_status,
        "confidence": job.confidence,
        "measures": [measurement.as_record() for measurement in measurements],
        "assumptions": list(job.assumptions),
        "coverage_gaps": list(job.coverage_gaps),
        "inputs": [{"path": path, "hash": digest} for path, digest in sorted(job.inputs.items())],
    }
    if raw.message:
        record["message"] = raw.message
    record.update(extra)
    record.update(judged)
    return canonical(record)


def _run_record(head, question: Question, job: Job, version: str, record_time):
    from .provenance import Actor, ActorKind, Input, ProvenanceOrigin, ProvenanceRecord

    return ProvenanceRecord(
        ProvenanceOrigin.GENERATED,
        "verification_run",
        Actor(ActorKind.TOOL, job.tool, version),
        head.revision_id,
        record_time,
        derived_from=(question.id,),
        inputs=tuple(Input(path, digest) for path, digest in sorted(job.inputs.items())),
        source_location=question.source_location,
        confidence=Confidence.INFERRED,
    )


def measurement_evidence(
    head, question: Question, job: Job, raw: RawRun, measurements: Sequence[Measurement],
    level: Level, record_time, *, verdict: Verdict | None = None,
):
    """One evidence entity for a run, carrying its measurement record."""
    from .entities import Evidence

    measured = [m for m in measurements if m.measured]
    missing = [m for m in measurements if not m.measured]
    claim = f"{job.tool} ({raw.version})"
    if measured:
        claim += " measured " + ", ".join(f"{m.name} = {m.quantity}" for m in measured)
    if missing:
        claim += ("; " if measured else " ") + "did not measure " + ", ".join(
            f"{m.name} ({m.reason})" for m in missing
        )
    if verdict is not None and verdict.summary:
        claim += ("; " if measurements else " ") + "; ".join(verdict.summary)
    claim += f" for {question.label}, at the {level.label} level"
    attempt = len(_attempts(head, question, job, raw.version))
    return Evidence(
        evidence_identity(head, question, job, raw.version, attempt=attempt),
        claim=claim,
        provenance=Provenance().append(_run_record(head, question, job, raw.version, record_time)),
        source_location=question.source_location,
        extensions={
            "measurement": measurement_record(job, raw, measurements, level, verdict=verdict)
        },
    )


def _replaced(verification: Verification, *, result: str, evidence: tuple[str, ...], level: Level, tool: str, record) -> Verification:
    from dataclasses import replace

    return replace(
        verification,
        result=result,
        evidence=evidence,
        level=level.label,
        tool=tool,
        provenance=verification.provenance.append(record),
    )


def measurement_transaction(
    head, question: Question, evidence, measurements: Sequence[Measurement], *,
    result: str, level: Level, record=None,
):
    """The transaction a run's measurements enter by, and nothing else.

    Three kinds of operation: each measured parameter set to an inferred value
    whose source is the evidence, the evidence added, and the declared
    verification replaced under its own identity with the result, the
    evidence, the level and the tool. Evidence already on the head, that of
    a run already recorded whose measurements re-enter, is cited as it
    stands and not added again, and `record` is the provenance the
    verification gains in place of the run's own.
    """
    from .graph import AddEntity, RemoveEntity, SetParameter, Transaction
    from .values import Value

    verification = head.entities[question.id]
    record = record or evidence.provenance.records[-1]
    operations: list = []
    for measurement in measurements:
        if not measurement.measured:
            continue
        operations.append(
            SetParameter(
                reason=f"measured by {measurement.tool} for {question.label}",
                requirement_refs=(question.verifies,),
                target=measurement.entity,
                name=measurement.attr,
                value=Value.inferred(measurement.quantity, evidence.id, measurement.confidence),
            )
        )
    if evidence.id not in head.entities:
        operations.append(AddEntity(reason=f"the evidence of {question.label}'s run", entity=evidence))
    operations.extend(
        (
            RemoveEntity(reason=f"{question.label} is answered", target=question.id),
            AddEntity(
                reason=f"{question.label} answered by {record.actor.id}",
                requirement_refs=(question.verifies,),
                entity=_replaced(
                    verification, result=result, evidence=(evidence.id,), level=level,
                    tool=record.actor.id, record=record,
                ),
            ),
        )
    )
    return Transaction(head.hash, tuple(operations), origin=record)


def failure_transaction(head, question: Question, evidence, *, level: Level, record=None):
    """The failure, recorded as knowledge: the evidence, and the verification
    with result FAIL. It changes no parameter, so the head never holds the
    value that failed. Evidence already on the head is cited, not added."""
    from .graph import AddEntity, RemoveEntity, Transaction

    verification = head.entities[question.id]
    record = record or evidence.provenance.records[-1]
    added = () if evidence.id in head.entities else (
        AddEntity(reason=f"the evidence of {question.label}'s failed run", entity=evidence),
    )
    return Transaction(
        head.hash,
        added + (
            RemoveEntity(reason=f"{question.label} failed its verification", target=question.id),
            AddEntity(
                reason=f"{question.label} failed by {record.actor.id}",
                requirement_refs=(question.verifies,),
                entity=_replaced(
                    verification, result="FAIL", evidence=(evidence.id,), level=level,
                    tool=record.actor.id, record=record,
                ),
            ),
        ),
        origin=record,
    )


def _result(statuses: Mapping[str, CheckStatus], missing: Sequence[str]) -> str:
    """A verification's result, from the constraints over what it measured."""
    if any(status is CheckStatus.FAIL for status in statuses.values()):
        return "FAIL"
    if missing or not statuses:
        return "UNKNOWN"
    if all(status in (CheckStatus.PASS, CheckStatus.NOT_APPLICABLE) for status in statuses.values()):
        return "PASS"
    return "UNKNOWN"


def _gate_statuses(proposal, question: Question) -> dict[str, CheckStatus]:
    """What the gate's own constraint check said about the question's
    constraints, where it ran."""
    over = {c.id for c in constraints_over(proposal.candidate, question.parameters)}
    return {
        check.subject: check.status
        for check in proposal.checks
        if check.check == "constraint" and check.subject in over
    }


def _failed_on_a_measured_constraint(proposal, question: Question) -> bool:
    """Whether a rejection is a hard constraint over a measured value failing,
    and nothing else. Anything else that rejects is surfaced untouched."""
    from .diagnostics import TXN_GATE_BLOCKED

    if proposal.candidate is None:
        return False
    blocking = [d for d in proposal.diagnostics if d.severity.blocking]
    failed = [check for check in proposal.checks if check.blocking]
    if not blocking or not failed:
        return False
    over = {c.id for c in constraints_over(proposal.candidate, question.parameters)}
    if any(check.check != "constraint" or check.subject not in over for check in failed):
        return False
    return all(d.code == TXN_GATE_BLOCKED for d in blocking)


#: How a question's turn through the runner ended.
ANSWERED = "answered"          # a run's measurements entered through the gate
FAILED = "failed"              # a measured value failed a hard constraint; recorded
DECIDED = "decided"            # answered at the equation level; nothing ran
UP_TO_DATE = "current"         # already answered by exactly this; nothing changed
UNROUTABLE = "unroutable"      # no registered tool covers it
UNSUPPORTED = "unsupported"    # the tool it routes to is not installed
NOT_RUNNABLE = "not runnable"  # the tool refused to prepare it, naming why
REJECTED = "rejected"          # the gate refused for another reason; nothing recorded


@dataclass(frozen=True)
class Outcome:
    """What happened to one question, with everything needed to explain it."""

    question: Question
    route: Route
    status: str
    result: str
    message: str = ""
    job: Job | None = None
    raw: RawRun | None = None
    measurements: tuple[Measurement, ...] = ()
    proposal: Any = None            # the measurement transaction's proposal
    recorded: Any = None            # the failure's proposal, when one was made
    evidence: str | None = None
    verification: Verification | None = None
    verdict: Verdict | None = None

    @property
    def failed(self) -> bool:
        return self.result == "FAIL"


def reenter(
    graph, question: Question, job: Job, raw: RawRun, measurements: Sequence[Measurement], *,
    level: Level, route_: Route | None = None, record_time=None, verdict: Verdict | None = None,
    recorded=None,
) -> Outcome:
    """Return a run's measurements through the commit gate.

    The measurement transaction is proposed against the head. Accepted, it
    commits, and the constraint over each measured parameter has been decided
    by the gate's constraint check. Rejected because a hard constraint over a
    measured value failed, the head does not move; the evidence and the
    verification with result FAIL are recorded by a second transaction that
    sets no parameter. Rejected for any other reason, nothing is recorded.
    Measurements prepared against anything but the head are refused.

    `recorded` is the evidence of a run already on the head, whose
    measurements re-enter rather than a new run's: the evidence is cited as
    it stands, and where the gate decides what the head already says (the
    same result, and the measured parameters as the head holds them),
    nothing is committed and the answer is `current`.
    """
    from datetime import datetime, timezone

    from .diagnostics import TXN_STALE_SNAPSHOT

    head = graph.head
    if job.snapshot != head.hash:
        raise error(
            TXN_STALE_SNAPSHOT,
            f"{question.label}'s run was prepared against {job.snapshot}, but the "
            f"head is {head.hash}; its measurements are refused rather than applied",
            entities=(question.id,),
        )
    route_ = route_ or Route(question.id, level, job.tool, "")
    record_time = record_time or datetime.now(timezone.utc)
    if recorded is None:
        evidence, provenance = measurement_evidence(
            head, question, job, raw, measurements, level, record_time, verdict=verdict
        ), None
    else:
        evidence, provenance = recorded, _reentry_record(head, question, recorded, record_time)

    # The result written on the verification is what the gate's constraint
    # check decides. It is predicted with the same evaluator, and the proposal
    # is rebuilt in the rare case the gate's own results say otherwise.
    measured = {(m.entity, m.attr): m for m in measurements if m.measured}
    base = head.resolver()

    def resolve(entity_id: str, attr: str):
        from .values import Value

        found = measured.get((entity_id, attr))
        if found is not None:
            return Value.inferred(found.quantity, evidence.id, found.confidence)
        return base(entity_id, attr)

    missing = [m.name for m in measurements if not m.measured]

    def judged(statuses) -> str:
        result = _result(statuses, missing)
        if verdict is None:
            return result
        if verdict.result == "FAIL" or result == "FAIL":
            return "FAIL"
        return verdict.result if not question.parameters else result

    def transaction(result: str):
        return measurement_transaction(
            head, question, evidence, measurements, result=result, level=level, record=provenance
        )

    result = judged(constraint_statuses(head, question, resolve))
    proposal = graph.propose(transaction(result))
    if proposal.accepted:
        decided = _gate_statuses(proposal, question)
        if decided and judged(decided) != result:
            result = judged(decided)
            proposal = graph.propose(transaction(result))
    common = dict(
        question=question, route=route_, job=job, raw=raw, measurements=tuple(measurements),
        evidence=evidence.id, verdict=verdict,
    )
    verification = head.entities[question.id]
    again = "" if recorded is None else (
        "the run already recorded for this job, re-entered through the gate"
    )

    def unchanged(candidate) -> bool:
        """Whether the gate decided what the head already says."""
        return recorded is not None and candidate.entities[question.id].result == verification.result and all(
            candidate.entities[entity_id].parameters.get(attr)
            == head.entities[entity_id].parameters.get(attr)
            for entity_id, attr in question.parameters
        )

    def current() -> Outcome:
        return Outcome(
            question, route_, UP_TO_DATE, verification.result,
            message=f"this run is already recorded, on {evidence.id}",
            job=job, evidence=evidence.id, verification=verification,
        )

    if proposal.accepted:
        if unchanged(proposal.candidate):
            return current()
        graph.commit(proposal)
        if missing:
            message = "not measured: " + ", ".join(missing)
        elif result != "UNKNOWN" or verdict is not None:
            message = ""
        else:
            message = "no constraint over its parameters decides it"
        return Outcome(
            status=ANSWERED, result=result,
            message="; ".join(part for part in (again, message) if part),
            proposal=proposal, verification=graph.head.entities[question.id], **common,
        )

    reasons = "; ".join(d.message for d in proposal.diagnostics if d.severity.blocking)
    if _failed_on_a_measured_constraint(proposal, question):
        failure = graph.propose(
            failure_transaction(head, question, evidence, level=level, record=provenance)
        )
        if failure.accepted:
            if unchanged(failure.candidate):
                return current()
            graph.commit(failure)
            refused = "the gate refused the measurement" + (
                "" if recorded is None else ", re-entered from the run already recorded"
            )
            return Outcome(
                status=FAILED, result="FAIL",
                message=f"{refused}: {reasons}",
                proposal=proposal, recorded=failure,
                verification=graph.head.entities[question.id], **common,
            )
        reasons = "; ".join(d.message for d in failure.diagnostics if d.severity.blocking)
        return Outcome(
            status=REJECTED, result=verification.result,
            message=f"the failure could not be recorded: {reasons}",
            proposal=proposal, recorded=failure, verification=verification, **common,
        )
    return Outcome(
        status=REJECTED, result=verification.result,
        message=f"the gate refused the measurement, and nothing is recorded: {reasons}",
        proposal=proposal, verification=verification, **common,
    )


def _reentry_record(head, question: Question, evidence, record_time):
    """The provenance a verification gains when a recorded run's
    measurements re-enter: the tool that measured them, the evidence they
    come from, and no new run."""
    from .provenance import ProvenanceOrigin, ProvenanceRecord

    run = evidence.provenance.records[-1]
    return ProvenanceRecord(
        ProvenanceOrigin.GENERATED,
        "verification_reentry",
        run.actor,
        head.revision_id,
        record_time,
        derived_from=(question.id, evidence.id),
        inputs=run.inputs,
        source_location=question.source_location,
        confidence=Confidence.INFERRED,
    )


def recorded_measurements(record: Mapping) -> tuple[Measurement, ...]:
    """The measurements a run's measurement record holds, read back: a
    quantity in its recorded unit, or no value and the recorded reason."""
    tool = record["tool"]
    confidence = Decimal(str(record["confidence"]))
    out = []
    for entry in record.get("measures", ()):
        quantity, reason = None, entry.get("reason")
        if reason is None:
            payload = {k: v for k, v in entry.items() if k not in ("name", "parameter")}
            payload.setdefault("kind", "scalar")
            quantity = Quantity.from_dict(payload)
        out.append(
            Measurement(
                entry["name"], entry["parameter"], quantity, tool["name"], tool["version"],
                record["job"], confidence, reason,
            )
        )
    return tuple(out)


def _decide(graph, question: Question, route_: Route, record_time) -> Outcome:
    """Answer at the equation level: the evaluator has already decided."""
    from datetime import datetime, timezone

    from . import __version__
    from .graph import AddEntity, RemoveEntity, Transaction
    from .provenance import Actor, ActorKind, ProvenanceOrigin, ProvenanceRecord

    head = graph.head
    verification = head.entities[question.id]
    # `route` decides only where nothing is unmeasured; were anything, the
    # result stays unknown rather than passing on what was never measured.
    result = _result(constraint_statuses(head, question), unmeasured(head, question))
    if verification.result == result:
        return Outcome(
            question, route_, UP_TO_DATE, result,
            message=(
                f"already answered at the {verification.level or 'equation'} level"
                + (f" by {verification.tool}" if verification.tool else "")
            ),
            verification=verification,
            evidence=verification.evidence[0] if verification.evidence else None,
        )

    sources = set()
    resolve = head.resolver()
    for entity_id, attr in question.parameters:
        value = resolve(entity_id, attr)
        if value is not None and value.source in head.entities:
            sources.add(value.source)
    record = ProvenanceRecord(
        ProvenanceOrigin.GENERATED,
        "equation_check",
        Actor(ActorKind.TOOL, "fang", __version__),
        head.revision_id,
        record_time or datetime.now(timezone.utc),
        derived_from=(question.id,),
        source_location=question.source_location,
    )
    replaced = _replaced(
        verification, result=result, evidence=tuple(sorted(sources)) or verification.evidence,
        level=Level.EQUATION, tool=EVALUATOR, record=record,
    )
    proposal = graph.propose(
        Transaction(
            head.hash,
            (
                RemoveEntity(reason=f"{question.label} is decided", target=question.id),
                AddEntity(
                    reason=f"{question.label} decided by the constraint evaluator",
                    requirement_refs=(question.verifies,),
                    entity=replaced,
                ),
            ),
            origin=record,
        )
    )
    if not proposal.accepted:
        reasons = "; ".join(d.message for d in proposal.diagnostics if d.severity.blocking)
        return Outcome(
            question, route_, REJECTED, verification.result,
            message=f"the gate refused the answer: {reasons}", proposal=proposal,
            verification=verification,
        )
    graph.commit(proposal)
    return Outcome(
        question, route_, DECIDED, result, message=route_.reason, proposal=proposal,
        verification=graph.head.entities[question.id],
    )


def answer(
    graph, question: Question, *, traits=None, tools: ToolRegistry | None = None,
    workspace: Path, record_time=None,
) -> Outcome:
    """Route one question, run it if it must run, and return what it found.

    No tool is prepared for a question the evaluator has already decided. A
    question whose tool is not installed is reported unsupported, by name,
    and nothing else answers it.
    """
    tools = TOOLS if tools is None else tools
    head = graph.head
    verification = head.entities[question.id]
    route_ = route(head, question, tools=tools)
    if route_.decided:
        return _decide(graph, question, route_, record_time)
    if not route_.routed:
        return Outcome(
            question, route_, UNROUTABLE, verification.result, message=route_.reason,
            verification=verification,
        )

    tool = tools.get(route_.tool)
    try:
        job = tool.prepare(head, question, traits=traits)
    except NotRunnable as exc:
        return Outcome(
            question, route_, NOT_RUNNABLE, verification.result, message=str(exc),
            verification=verification,
        )

    def unsupported(message: str) -> Outcome:
        return Outcome(
            question, route_, UNSUPPORTED, verification.result, message=message,
            job=job, verification=verification,
        )

    if not tool.available():
        return unsupported(
            f"{tool.name} is not installed; nothing else answers the question "
            "and no result is fabricated"
        )
    try:
        version = tool.version()
    except ToolUnavailable as exc:
        return unsupported(str(exc))

    # The same job on the same version is the same run, and is not run again
    # once it has completed and answered this verification. Its recorded
    # measurements re-enter through the gate instead, which decides on the
    # head as it is now: a constraint relaxed since a FAIL, or one that has
    # become undecided, changes the result, and an unchanged one is current.
    # A verdict is the checker's own over the same job and is not re-judged.
    # A run that did not complete is tried again, as evidence of its own.
    judge = getattr(tool, "verdict", None)
    recorded = _attempts(head, question, job, version)
    if recorded and recorded[-1] in verification.evidence:
        last = head.entities[recorded[-1]]
        record = last.extensions.get("measurement", {})
        if record.get("status") == Status.SUCCEEDED.value:
            if judge is None and question.parameters:
                raw = RawRun(
                    record["tool"]["name"], record["tool"]["version"],
                    int(record.get("exit_status", 0)), message=record.get("message", ""),
                )
                return reenter(
                    graph, question, job, raw, recorded_measurements(record),
                    level=route_.level, route_=route_, record_time=record_time, recorded=last,
                )
            return Outcome(
                question, route_, UP_TO_DATE, verification.result,
                message=f"this run is already recorded, on {last.id}",
                job=job, evidence=last.id, verification=verification,
            )
    try:
        raw = tool.run(job, workspace=Path(workspace) / f"{tool.name}-{job.hash[7:19]}")
    except ToolUnavailable as exc:
        return unsupported(str(exc))
    except Exception as exc:          # a tool's failure is data, not a crash
        raw = RawRun(tool.name, version, -1, status=Status.FAILED, message=str(exc))
    measurements = tool.read(job, raw)
    return reenter(
        graph, question, job, raw, measurements, level=route_.level, route_=route_,
        record_time=record_time, verdict=judge(job, raw) if judge is not None else None,
    )


def verify(
    graph, *, traits=None, tools: ToolRegistry | None = None, workspace: Path,
    record_time=None,
) -> tuple[Outcome, ...]:
    """Answer every declared question on the head, in identifier order.

    Each question is routed and answered against the head as it stands when
    its turn comes, so every measurement is proposed against the committed
    head and nothing is applied to a snapshot that has moved.
    """
    outcomes = []
    for declared in questions(graph.head):
        question = Question.of(graph.head.entities[declared.id])
        outcomes.append(
            answer(
                graph, question, traits=traits, tools=tools, workspace=workspace,
                record_time=record_time,
            )
        )
    return tuple(outcomes)


# --------------------------------------------------------------------------
# Re-elaboration does not withdraw a measured value
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class MeasuredFacts:
    """What a run wrote that a program does not: answered verifications,
    their evidence, and the values whose source that evidence is."""

    verifications: Mapping[str, Verification] = field(default_factory=dict)
    evidence: Mapping[str, Any] = field(default_factory=dict)
    values: Mapping[tuple[str, str], Any] = field(default_factory=dict)

    @staticmethod
    def _answered(verification) -> bool:
        return isinstance(verification, Verification) and "question" in verification.extensions and (
            verification.result != "UNKNOWN" or bool(verification.evidence)
        )

    @classmethod
    def of(cls, snapshot) -> "MeasuredFacts":
        from .entities import Evidence
        from .values import Value

        verifications = {
            e.id: e for e in snapshot.entities.values() if cls._answered(e)
        }
        evidence = {
            ref: snapshot.entities[ref]
            for verification in verifications.values()
            for ref in verification.evidence
            if isinstance(snapshot.entities.get(ref), Evidence)
        }
        values = {}
        resolve = snapshot.resolver()
        for verification in verifications.values():
            for entity_id, attr in Question.of(verification).parameters:
                value = resolve(entity_id, attr)
                if isinstance(value, Value) and value.source in evidence:
                    values[(entity_id, attr)] = value
        return cls(verifications, evidence, values)

    @classmethod
    def from_records(cls, records: Sequence[Mapping]) -> "MeasuredFacts":
        """The same facts, read back from a workspace's record stream.

        Only what a run wrote is rebuilt; everything else a program owns, and
        elaborating the program rebuilds it.
        """
        from .entities import Evidence
        from .identity import Identity
        from .values import Value

        by_id = {record["id"]: record for record in records}

        def common(record) -> dict:
            location = record.get("source_location")
            return dict(
                identity=Identity.from_dict(record["identity"]),
                provenance=Provenance.from_list(record.get("provenance", ())),
                source_location=SourceLocation.from_dict(location) if location else None,
                extensions=dict(record.get("extensions", {})),
            )

        verifications = {}
        for record in records:
            if record.get("kind") != "verification":
                continue
            verification = Verification(
                verifies=record["verifies"],
                method=record["method"],
                evidence=tuple(record.get("evidence", ())),
                result=record["result"],
                level=record.get("level"),
                tool=record.get("tool"),
                **common(record),
            )
            if cls._answered(verification):
                verifications[verification.id] = verification

        evidence = {}
        for verification in verifications.values():
            for ref in verification.evidence:
                record = by_id.get(ref)
                if record is None or record.get("kind") != "evidence":
                    continue
                evidence[ref] = Evidence(
                    claim=record.get("claim", ""),
                    document=record.get("document"),
                    locator=record.get("locator"),
                    **common(record),
                )

        values = {}
        for verification in verifications.values():
            for entity_id, attr in Question.of(verification).parameters:
                payload = by_id.get(entity_id, {}).get("parameters", {}).get(attr)
                if payload is None or "candidates" in payload:
                    continue
                value = Value.from_dict(payload)
                if value.source in evidence:
                    values[(entity_id, attr)] = value
        return cls(verifications, evidence, values)


def _answers(evidence) -> str | None:
    """The question a run's evidence answers, from the record of its run."""
    for record in reversed(evidence.provenance.records):
        if record.activity == "verification_run" and record.derived_from:
            return record.derived_from[0]
    return None


class Currency:
    """Whether what a run measured is still what the design would measure.

    A run is current while preparing the same question afresh, on a fresh
    elaboration, gives the job its measurement record names: the question
    is routed there and prepared by the tool it routes to, and the job's
    hash must be the recorded one. The hash covers the native input the
    snapshot lowers to, the digest of every file the run read that the
    snapshot does not hold (a model, a firmware image) and the question, and
    not the snapshot's own hash, so it moves exactly when what the run rested
    on does. A question that no longer routes to the run's tool, or that the
    tool refuses to prepare, is not current.

    Nothing about the machine enters: whether the tool is installed here, or
    which version is, does not decide what a rebuild keeps, so the same
    program and workspace rebuild to the same snapshot everywhere. A run on
    another version is evidence of its own when the question is next asked
    (`answer`), not a reason to drop this one.
    """

    def __init__(self, snapshot, *, traits=None, tools: ToolRegistry | None = None) -> None:
        self.snapshot = snapshot
        self.traits = traits
        self.tools = TOOLS if tools is None else tools
        self._jobs: dict[str, tuple[str | None, str | None]] = {}

    def job(self, question: Question) -> tuple[str | None, str | None]:
        """The tool the question routes to here, and the hash of its job."""
        if question.id not in self._jobs:
            routed = route(self.snapshot, question, tools=self.tools)
            found: tuple[str | None, str | None] = (None, None)
            if routed.routed and not routed.decided:
                try:
                    prepared = self.tools.get(routed.tool).prepare(
                        self.snapshot, question, traits=self.traits
                    )
                    found = (routed.tool, prepared.hash)
                except NotRunnable:
                    found = (routed.tool, None)
            self._jobs[question.id] = found
        return self._jobs[question.id]

    def __call__(self, evidence) -> bool:
        record = evidence.extensions.get("measurement")
        if record is None:
            return True                       # not a run; nothing to repeat
        declared = self.snapshot.entities.get(_answers(evidence) or "")
        question = Question.of(declared) if declared is not None else None
        if question is None:
            return False
        tool, job = self.job(question)
        return (
            tool is not None
            and job is not None
            and tool == record.get("tool", {}).get("name")
            and job == record.get("job")
        )


def carry_measurements(
    elaborated, facts: MeasuredFacts, *, traits=None, tools: ToolRegistry | None = None,
    current: Callable[[Any], bool] | None = None,
):
    """A fresh elaboration, with what runs measured kept in place while it is
    still current.

    The program declared each measured parameter without a value, so
    elaborating it again says nothing about the value and must not withdraw
    it. An answered verification is kept, with its evidence and the values
    that evidence is the source of, wherever the program still declares the
    same question and every run it rests on is still current (`Currency`):
    the same question prepared afresh gives the same job. A changed circuit,
    model file or firmware changes the job, and the question is answered
    afresh rather than reported current on a measurement of something else;
    so is a question the program has changed. A program cannot give a
    measured parameter a value of its own (elaboration refuses one), so the
    value carried is always the measurement's.

    `current` says whether one run's evidence is still current, and is
    `Currency` over the elaboration unless given. One that keeps every run
    asks only whether the program has changed: carried that way, an
    unchanged program gives back the design its measurements were committed
    to, whatever has happened since to the files it reads.
    """
    entities = dict(elaborated.entities)
    current = current or Currency(elaborated, traits=traits, tools=tools)
    for verification_id, answered in sorted(facts.verifications.items()):
        declared = entities.get(verification_id)
        if not isinstance(declared, Verification):
            continue
        if declared.extensions.get("question") != answered.extensions.get("question"):
            continue
        if any(ref not in facts.evidence and ref not in entities for ref in answered.evidence):
            continue
        if not all(current(facts.evidence[ref]) for ref in answered.evidence if ref in facts.evidence):
            continue
        entities[verification_id] = answered
        for ref in answered.evidence:
            if ref in facts.evidence:
                entities.setdefault(ref, facts.evidence[ref])
        for entity_id, attr in Question.of(answered).parameters:
            value = facts.values.get((entity_id, attr))
            target = entities.get(entity_id)
            if value is None or target is None or value.source not in answered.evidence:
                continue
            entities[entity_id] = target.with_parameter(attr, value)
    return elaborated.with_entities(entities, elaborated.revision_id)


def reelaboration(head, elaborated, *, traits=None, tools: ToolRegistry | None = None):
    """The transaction that moves a head to a fresh elaboration of its program.

    It keeps what runs measured while it is current (`carry_measurements`),
    so an unchanged program elaborated again is an empty transaction: the
    measured value and its evidence stay, and the program is not recorded as
    having changed a parameter it never gave a value.
    """
    from .graph import AddEntity, RemoveEntity, Transaction

    target = carry_measurements(elaborated, MeasuredFacts.of(head), traits=traits, tools=tools)
    operations: list = []
    for entity_id in sorted(set(head.entities) - set(target.entities)):
        operations.append(RemoveEntity(reason="no longer elaborated", target=entity_id))
    for entity_id in sorted(set(target.entities) - set(head.entities)):
        operations.append(AddEntity(reason="elaborated", entity=target.entities[entity_id]))
    for entity_id in sorted(set(target.entities) & set(head.entities)):
        before, after = head.entities[entity_id], target.entities[entity_id]
        if canonical_dumps(before.as_dict()) == canonical_dumps(after.as_dict()):
            continue
        operations.append(RemoveEntity(reason="re-elaborated", target=entity_id))
        operations.append(AddEntity(reason="re-elaborated", entity=after))
    return Transaction(head.hash, tuple(operations))


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def significant(value: Decimal, figures: int = 3) -> str:
    """A magnitude at a number of significant figures, for a person to read.

    The evidence keeps every figure the tool printed; this is only what a
    listing shows, so that a simulator release which moves a number in its
    fourth figure moves nothing a person reads.
    """
    from decimal import ROUND_HALF_EVEN

    if not value.is_finite():
        return "Infinity" if value > 0 else "-Infinity"
    if value == 0:
        return "0"
    quantum = Decimal(1).scaleb(value.adjusted() - figures + 1)
    text = format(value.quantize(quantum, rounding=ROUND_HALF_EVEN), "f")
    return text


def _quantity_text(quantity: Quantity, figures: int) -> str:
    # A dimensionless whole number is a count: exact, and written without the
    # unit "1" that only the record needs.
    unit = "" if str(quantity.unit) in ("1", "") else f" {quantity.unit}"

    def number(value: Decimal) -> str:
        if not unit and value.is_finite() and value == value.to_integral_value():
            return str(int(value))
        return significant(value, figures)

    if quantity.kind == "scalar":
        return f"{number(quantity.value)}{unit}"
    if quantity.kind == "range":
        return f"{number(quantity.minimum)} to {number(quantity.maximum)}{unit}"
    return str(quantity)


def report(outcomes: Sequence[Outcome], *, versions: bool = True, figures: int = 3) -> list[str]:
    """Each question's level, tool, measurements and result, as lines.

    With `versions` false the listing leaves out what follows the machine
    rather than the design -- tool versions and evidence identifiers, which
    derive from them -- and is what an example ships.
    """
    lines: list[str] = []
    for outcome in outcomes:
        question = outcome.question
        lines.append(f"{question.label} ({question.id})")
        route_ = outcome.route
        if route_.decided:
            lines.append("  equation level, by the constraint evaluator; nothing runs")
        elif route_.routed:
            version = ""
            if versions and outcome.raw is not None:
                version = f" ({outcome.raw.version})"
            lines.append(f"  {route_.level.label} level, {route_.tool}{version}")
        for measurement in outcome.measurements:
            if measurement.measured:
                lines.append(
                    f"  {measurement.name} = {_quantity_text(measurement.quantity, figures)}"
                )
            else:
                lines.append(f"  {measurement.name}: not measured ({measurement.reason})")
        if outcome.verdict is not None:
            lines.extend(f"  {line}" for line in outcome.verdict.summary)
        if outcome.job is not None and outcome.status in (ANSWERED, FAILED):
            lines.extend(f"  assumption: {item}" for item in outcome.job.assumptions)
            lines.extend(f"  coverage gap: {item}" for item in outcome.job.coverage_gaps)
            lines.append(f"  confidence {outcome.job.confidence}")
        if outcome.status in (UNROUTABLE, UNSUPPORTED, NOT_RUNNABLE, REJECTED, UP_TO_DATE, FAILED):
            lines.append(f"  {outcome.status}: {outcome.message}")
        elif outcome.message and outcome.status == ANSWERED:
            lines.append(f"  {outcome.message}")
        if versions and outcome.evidence and outcome.status in (ANSWERED, FAILED):
            lines.append(f"  evidence {outcome.evidence}")
        lines.append(f"  {outcome.result}")
    return lines
