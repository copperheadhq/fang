"""Verification questions, the tools that answer them, and the way back in.

Spec: "Verification Questions Are Declared", "The Bench Is Explicit", "The
Cheapest Verification Level Is Chosen And Recorded", "Verification Tools Sit
Behind One Protocol", "Measurements Re-enter Through The Commit Gate", "A
Failing Measurement Is Recorded And Not Applied", and "The Verify Command".

A question is a verification entity whose result is not known yet. A program
declares it beside the requirement it serves -- the parameters it measures
into, the measures that produce them, and for a circuit question the bench --
and cannot declare its answer. The runner routes it to the cheapest level that
can decide it, prepares the chosen tool's native input from the snapshot alone,
runs the tool across a process boundary, reads decimal measurements back, and
returns them through the commit gate as an ordinary transaction. The constraint
over a measured parameter is decided by the gate's constraint check and by
nothing else here.

The extension points a second kind of question plugs into without editing this
module are `QuestionDeclaration` (its hooks are `named_surfaces`,
`resolve_surface`, `measured_dimension` and `question_fields`), `Tool`,
`register_tool`, and `METHOD_LEVELS` with `register_method`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping, Sequence

from .diagnostics import (
    SIM_LOAD_DIMENSION,
    SIM_QUESTION_RESULT,
    SIM_UNDECLARED_PARAMETER,
    SIM_UNRESOLVED_SURFACE,
    UNIT_DIMENSION_MISMATCH,
    SourceLocation,
    error,
)
from .rationale import Verifies
from .serialization import canonical_dumps
from .simulation import Analysis
from .units import Dimension, Quantity, Unit

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
    """A statistic of the surface's voltage over a window of the analysis."""

    after: Quantity | None = field(default=None, kw_only=True)
    until: Quantity | None = field(default=None, kw_only=True)

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
    result, checks that every measure writes a parameter its module declares,
    resolves every surface while the module tree is still in hand, and builds
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
            produced = self.measured_dimension(measure)
            if produced is not None and produced != parameter.unit.dimension:
                raise error(
                    UNIT_DIMENSION_MISMATCH,
                    f"{self.attribute} measures {name} with "
                    f"{type(measure).__name__}, which does not produce "
                    f"{parameter.unit}",
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
