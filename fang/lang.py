"""The Fang language: the declarative surface an engineer or an agent writes.

Spec: "Fang Is Ordinary Python", "Declarative Module Composition", "Parameter
Declaration And Reference", "Declared Constraints Are Not Evaluated Eagerly",
and "The Connect Operator".

A Fang program is an ordinary Python module. Nothing here mutates geometry,
calls a tool, or evaluates a constraint; declarations are recorded and the
kernel decides.
"""

from __future__ import annotations

import inspect
import itertools
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

from .constraints import (
    Arithmetic,
    Comparison,
    Literal,
    Node,
    Ref,
)
from .diagnostics import (
    ELAB_UNTYPED_CONNECTION,
    UNIT_DIMENSION_MISMATCH,
    SourceLocation,
    error,
)
from .entities import ConnectionKind
from .toolplan import Handle, PlanRecorder
from .traits import DatasheetEvidence, Footprint, Sourcing, Trait
from .units import DIMENSIONLESS, Dimension, Quantity, Unit
from .values import Value

_ORDER = itertools.count()


def _caller_location(depth: int = 2) -> SourceLocation | None:
    """The file and line of the declaration being made.

    Captured at declaration time, because a source location recovered later is a
    guess and every entity must carry the real one.
    """
    frame = inspect.currentframe()
    for _ in range(depth):
        if frame is None:
            return None
        frame = frame.f_back
    if frame is None:
        return None
    return SourceLocation(frame.f_code.co_filename, frame.f_lineno)


# --------------------------------------------------------------------------
# Unit literals
# --------------------------------------------------------------------------


class UnitLiteral:
    """A unit usable as a literal, so ``3.3 * V`` is a quantity.

    The magnitude becomes a decimal on the way in; a binary float never reaches
    a quantity record.
    """

    __slots__ = ("unit",)

    def __init__(self, symbol: str) -> None:
        self.unit = Unit.parse(symbol)

    def __rmul__(self, magnitude) -> Quantity:
        return Quantity.scalar(_decimal(magnitude), self.unit)

    __mul__ = __rmul__

    def __call__(self, magnitude) -> Quantity:
        return Quantity.scalar(_decimal(magnitude), self.unit)

    def __repr__(self) -> str:
        return f"<unit {self.unit.symbol}>"


def class_location(cls: type) -> SourceLocation | None:
    """The file and line where a module class is defined.

    Used for a root system the elaborator instantiates itself: it has no
    declaring line in a parent's class body, and the caller's line would vary
    between builds.
    """
    try:
        file = inspect.getsourcefile(cls)
        _, line = inspect.getsourcelines(cls)
    except (OSError, TypeError):
        return None
    return SourceLocation(file, line) if file else None


def _decimal(magnitude) -> Decimal:
    if isinstance(magnitude, Decimal):
        return magnitude
    return Decimal(str(magnitude))


# The units a board design actually reaches for. A project adds its own with
# UnitLiteral("...") rather than editing this list.
V = UnitLiteral("V")
mV = UnitLiteral("mV")
uV = UnitLiteral("uV")
kV = UnitLiteral("kV")
A = UnitLiteral("A")
mA = UnitLiteral("mA")
uA = UnitLiteral("uA")
nA = UnitLiteral("nA")
W = UnitLiteral("W")
mW = UnitLiteral("mW")
Ohm = UnitLiteral("Ohm")
mOhm = UnitLiteral("mOhm")
kOhm = UnitLiteral("kOhm")
MOhm = UnitLiteral("MOhm")
F = UnitLiteral("F")
uF = UnitLiteral("uF")
nF = UnitLiteral("nF")
pF = UnitLiteral("pF")
H = UnitLiteral("H")
mH = UnitLiteral("mH")
uH = UnitLiteral("uH")
Hz = UnitLiteral("Hz")
kHz = UnitLiteral("kHz")
MHz = UnitLiteral("MHz")
s = UnitLiteral("s")
ms = UnitLiteral("ms")
us = UnitLiteral("us")
ns = UnitLiteral("ns")
m = UnitLiteral("m")
mm = UnitLiteral("mm")
degC = UnitLiteral("degC")
percent = UnitLiteral("percent")


def between(minimum: Quantity, maximum: Quantity, typical: Quantity | None = None) -> Quantity:
    """A range quantity. Both bounds must share a dimension."""
    if minimum.dimension != maximum.dimension:
        raise error(
            UNIT_DIMENSION_MISMATCH,
            f"a range needs bounds of equal dimension: {minimum.unit} and {maximum.unit}",
        )
    converted, _ = maximum.converted_to(minimum.unit)
    typical_value = None
    if typical is not None:
        typical_converted, _ = typical.converted_to(minimum.unit)
        typical_value = typical_converted.value
    return Quantity.range(minimum.value, converted.value, minimum.unit, typical_value)


def tolerance(nominal: Quantity, amount: str | Decimal | Quantity) -> Quantity:
    """A tolerance quantity. A string ending in ``%`` is a relative tolerance."""
    if isinstance(amount, Quantity):
        converted, _ = amount.converted_to(nominal.unit)
        return Quantity.with_tolerance(
            nominal.value, converted.value, nominal.unit, kind="absolute"
        )
    text = str(amount).strip()
    if text.endswith("%"):
        relative = Decimal(text[:-1]) / Decimal(100)
        return Quantity.with_tolerance(nominal.value, relative, nominal.unit)
    return Quantity.with_tolerance(nominal.value, Decimal(text), nominal.unit)


# --------------------------------------------------------------------------
# Declarations
# --------------------------------------------------------------------------


class Declared:
    """Anything written in a module's class body.

    Each subclass names its `_declaration_kind` so the metaclass can sort a
    class body without importing the modules that define the kinds.

    Each declaration records its order and its source location at construction,
    so elaboration never depends on dictionary iteration and every entity can
    name the line that produced it.
    """

    _declaration_kind = "child"

    def __new__(cls, *args, **kwargs):
        instance = object.__new__(cls)
        instance._ctor = (args, kwargs)
        instance._order = next(_ORDER)
        instance._source = _caller_location(2)
        return instance

    def _clone(self) -> "Declared":
        """A fresh copy, so two instances never share a declaration."""
        args, kwargs = self._ctor
        copy = type(self)(*args, **kwargs)
        copy._source = self._source
        copy._order = self._order
        return copy


class ParameterRef:
    """A reference to a parameter, usable in a constraint expression.

    Comparing it builds an expression node rather than returning a Python
    boolean, which is what lets `require()` record a constraint instead of
    evaluating one.
    """

    __slots__ = ("owner", "name", "dimension")

    def __init__(self, owner: "Module", name: str, dimension: Dimension) -> None:
        self.owner = owner
        self.name = name
        self.dimension = dimension

    def _node(self) -> Ref:
        return Ref(self.owner._entity_id, self.name, self.dimension)

    def _other(self, other) -> Node:
        if isinstance(other, ParameterRef):
            return other._node()
        if isinstance(other, Node):
            return other
        if isinstance(other, Quantity):
            return Literal.of(other)
        return Literal.of(other)

    # Comparisons build nodes. Nothing is decided here.
    def __le__(self, other) -> Comparison:
        return Comparison("le", (self._node(), self._other(other)))

    def __lt__(self, other) -> Comparison:
        return Comparison("lt", (self._node(), self._other(other)))

    def __ge__(self, other) -> Comparison:
        return Comparison("ge", (self._node(), self._other(other)))

    def __gt__(self, other) -> Comparison:
        return Comparison("gt", (self._node(), self._other(other)))

    def __eq__(self, other) -> Comparison:  # type: ignore[override]
        return Comparison("eq", (self._node(), self._other(other)))

    def __ne__(self, other) -> Comparison:  # type: ignore[override]
        return Comparison("ne", (self._node(), self._other(other)))

    def __hash__(self) -> int:
        return hash((id(self.owner), self.name))

    # Arithmetic builds nodes too, so a constraint can relate two parameters.
    def __add__(self, other) -> Arithmetic:
        return Arithmetic("add", (self._node(), self._other(other)))

    def __sub__(self, other) -> Arithmetic:
        return Arithmetic("sub", (self._node(), self._other(other)))

    def __mul__(self, other) -> Arithmetic:
        return Arithmetic("mul", (self._node(), self._other(other)))

    def __truediv__(self, other) -> Arithmetic:
        return Arithmetic("div", (self._node(), self._other(other)))

    def __repr__(self) -> str:
        return f"<{self.owner._path or type(self.owner).__name__}.{self.name}>"


class Parameter(Declared):
    """A declared parameter. A bare number is not a parameter.

    Unassigned, its value is unknown rather than defaulted, as the spec requires.
    """

    _declaration_kind = "parameter"

    def __init__(self, unit: str, *, default: Quantity | None = None, description: str = "") -> None:
        self.unit = Unit.parse(unit)
        self.default = default
        self.description = description
        self.name = ""
        if default is not None and default.dimension != self.unit.dimension:
            raise error(
                UNIT_DIMENSION_MISMATCH,
                f"default {default} does not match the declared unit {self.unit}",
            )

    def __set_name__(self, owner, name: str) -> None:
        self.name = name

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        return ParameterRef(instance, self.name, self.unit.dimension)

    def __set__(self, instance, value) -> None:
        instance._set_parameter(self.name, self, value)


class Surface(Declared):
    """A connection surface on a module.

    Stage 3 replaces these with the full typed interface catalogue; the
    connection they record is already typed.
    """

    _declaration_kind = "surface"
    connection_kind: ConnectionKind = ConnectionKind.ELECTRICAL
    surface_type: str = "electrical"
    signals: tuple[str, ...] = ("line",)

    def __init__(self, *, name: str = "", direction: str | None = None) -> None:
        self.name = name
        self.direction = direction
        self.owner: "Module | None" = None
        self.attribute: str = ""

    @property
    def _entity_id(self) -> str:
        return self.owner._port_ids[self.attribute]

    def pin_lookup(self, signal: str) -> tuple[str, str]:
        """Where the pin map is asked for this signal's candidates.

        A single-wire surface answers for its own wire whatever the other side
        calls it: one wire to one wire is unambiguous.
        """
        own = self.signals
        return (self.attribute, signal if signal in own else own[0])

    def connect(
        self, other: "Surface", *, location: SourceLocation | None = None
    ) -> None:
        """Record a typed connection. Neither surface is mutated."""
        _context().connect(self, other, location or _caller_location(2))

    def __rshift__(self, other: "Surface") -> "Surface":
        # The useful location is the line that wrote ">>", not this method.
        self.connect(other, location=_caller_location(2))
        return other

    def __repr__(self) -> str:
        owner = self.owner._path if self.owner and self.owner._path else "?"
        return f"<{type(self).__name__} {owner}.{self.attribute}>"


class Electrical(Surface):
    connection_kind = ConnectionKind.ELECTRICAL
    surface_type = "electrical"


class Power(Surface):
    connection_kind = ConnectionKind.POWER
    surface_type = "power"
    signals = ("vcc",)


class Ground(Surface):
    connection_kind = ConnectionKind.GROUND
    surface_type = "ground"
    signals = ("gnd",)


class Signal(Surface):
    connection_kind = ConnectionKind.SIGNAL
    surface_type = "signal"


class Mechanical(Surface):
    connection_kind = ConnectionKind.MECHANICAL
    surface_type = "mechanical"


#: Which surface kinds may connect across types. Two surfaces of the same type
#: always connect; this table names the cross-type pairs that also make sense. A
#: power output into a mechanical mount is not a connection anyone meant to make,
#: so it is refused rather than recorded.
COMPATIBLE_SURFACES: Mapping[str, frozenset[str]] = {
    "electrical": frozenset({"power", "ground", "signal"}),
    "power": frozenset({"electrical", "power_input", "power_output"}),
    "ground": frozenset({"electrical"}),
    "signal": frozenset({"electrical"}),
    "power_output": frozenset({"power_input", "power"}),
    "power_input": frozenset({"power_output", "power"}),
    "analog_output": frozenset({"analog_input"}),
    "analog_input": frozenset({"analog_output"}),
}


# --------------------------------------------------------------------------
# Modules
# --------------------------------------------------------------------------


#: Where the metaclass files each declaration kind.
_DECLARATION_ATTRIBUTES = {
    "parameter": "_parameters",
    "surface": "_surfaces",
    "child": "_children",
    "pin": "_pins",
    "pin_map": "_pin_maps",
    "rationale": "_rationale",
}


class ModuleMeta(type):
    """Collects declarations in class-body order.

    Python preserves class-body insertion order, so declaration order is the
    order written rather than an artefact of hashing.
    """

    def __new__(mcls, name, bases, namespace, **kwargs):
        cls = super().__new__(mcls, name, bases, namespace, **kwargs)

        collected: dict[str, dict[str, Any]] = {
            kind: {} for kind in _DECLARATION_ATTRIBUTES
        }
        for base in reversed(bases):
            for kind, attribute in _DECLARATION_ATTRIBUTES.items():
                collected[kind].update(getattr(base, attribute, {}))

        for attribute, value in namespace.items():
            if isinstance(value, Declared):
                collected[value._declaration_kind][attribute] = value

        for kind, attribute in _DECLARATION_ATTRIBUTES.items():
            setattr(cls, attribute, collected[kind])
        return cls


class Module(Declared, metaclass=ModuleMeta):
    """A reusable unit owning parameters, surfaces, constraints, and children.

    Composition is connection between declared surfaces, not between pins.
    """

    #: What kind of entity this module becomes. `Part` overrides it.
    entity_kind = "block"

    _parameters: Mapping[str, Parameter] = {}
    _surfaces: Mapping[str, Surface] = {}
    _children: Mapping[str, "Module"] = {}
    _pins: Mapping[str, Declared] = {}
    _pin_maps: Mapping[str, Declared] = {}
    _rationale: Mapping[str, Declared] = {}

    def __init__(self, **overrides) -> None:
        self._path: str = ""
        self._entity_id: str = ""
        self._values: dict[str, Value] = {}
        self._declared_constraints: list[tuple[Node, SourceLocation | None]] = []
        self._traits: list[Trait] = []
        self._port_ids: dict[str, str] = {}
        self._instance_children: dict[str, Module] = {}
        self._instance_surfaces: dict[str, Surface] = {}

        # Each instance gets its own children and surfaces; the class body holds
        # templates, never shared state.
        for attribute, template in sorted(
            type(self)._surfaces.items(), key=lambda kv: kv[1]._order
        ):
            surface = template._clone()
            surface.owner = self
            surface.attribute = attribute
            self._instance_surfaces[attribute] = surface
            object.__setattr__(self, attribute, surface)

        for attribute, template in sorted(
            type(self)._children.items(), key=lambda kv: kv[1]._order
        ):
            child = template._clone()
            self._instance_children[attribute] = child
            object.__setattr__(self, attribute, child)

        self._instance_pins: dict[str, Declared] = {}
        for attribute, template in sorted(
            type(self)._pins.items(), key=lambda kv: kv[1]._order
        ):
            pin = template._clone()
            pin.owner = self
            pin.attribute = attribute
            self._instance_pins[attribute] = pin
            object.__setattr__(self, attribute, pin)

        self._pin_map = _merge_pin_maps(type(self)._pin_maps.values())

        self._instance_rationale: dict[str, Declared] = {}
        for attribute, template in sorted(
            type(self)._rationale.items(), key=lambda kv: kv[1]._order
        ):
            declaration = template._clone()
            declaration.owner = self
            declaration.attribute = attribute
            self._instance_rationale[attribute] = declaration
            object.__setattr__(self, attribute, declaration)

        for name, parameter in type(self)._parameters.items():
            if parameter.default is not None:
                self._set_parameter(name, parameter, parameter.default)

        for name, value in overrides.items():
            parameter = type(self)._parameters.get(name)
            if parameter is None:
                raise error(
                    ELAB_UNTYPED_CONNECTION,
                    f"{type(self).__name__} has no declared parameter {name!r}",
                )
            self._set_parameter(name, parameter, value)

    # -- parameters --------------------------------------------------------

    def _set_parameter(self, name: str, parameter: Parameter, value) -> None:
        if isinstance(value, Value):
            self._values[name] = value
            return
        if not isinstance(value, Quantity):
            raise error(
                UNIT_DIMENSION_MISMATCH,
                f"{type(self).__name__}.{name} takes a quantity with an explicit "
                f"unit, not {value!r}; a bare number is not a parameter",
            )
        if value.dimension != parameter.unit.dimension:
            raise error(
                UNIT_DIMENSION_MISMATCH,
                f"{type(self).__name__}.{name} is declared in {parameter.unit} but "
                f"was assigned {value.unit}",
            )
        self._values[name] = Value.explicit(value)

    def value_of(self, name: str) -> Value:
        """The recorded value, or unknown. Never a default standing in for one."""
        return self._values.get(name, Value.unknown())

    # -- traits ------------------------------------------------------------

    def add_trait(self, trait: Trait) -> Trait:
        self._traits.append(trait)
        return trait

    @property
    def traits(self) -> tuple[Trait, ...]:
        return tuple(self._traits)

    # -- hooks the author overrides ---------------------------------------

    def architecture(self) -> None:
        """Connect children. Called once during elaboration."""

    def constraints(self) -> None:
        """Declare constraints. Called once during elaboration."""

    # -- introspection -----------------------------------------------------

    @property
    def path(self) -> str:
        return self._path

    def children(self) -> Mapping[str, "Module"]:
        return dict(self._instance_children)

    def surfaces(self) -> Mapping[str, Surface]:
        return dict(self._instance_surfaces)

    def pins(self) -> Mapping[str, Declared]:
        return dict(self._instance_pins)

    def rationale(self) -> Mapping[str, Declared]:
        """What this module records about its own reasoning."""
        return dict(self._instance_rationale)

    @property
    def pin_map(self):
        """The merged pin map: which pins can carry which interface signal."""
        return self._pin_map

    def __repr__(self) -> str:
        return f"<{type(self).__name__} {self._path or 'unelaborated'}>"


def _merge_pin_maps(maps):
    """One module may declare several pin maps; the merge is their union."""
    merged: dict[str, tuple[str, ...]] = {}
    for pin_map in sorted(maps, key=lambda m: m._order):
        merged.update(pin_map.mapping)
    return _MergedPinMap(merged)


class _MergedPinMap:
    """The lookup the lowering uses. Empty when a module declares no pins."""

    __slots__ = ("mapping",)

    def __init__(self, mapping: Mapping[str, tuple[str, ...]]) -> None:
        self.mapping = dict(mapping)

    def candidates(self, port_attribute: str, signal: str) -> tuple[str, ...]:
        return self.mapping.get(f"{port_attribute}.{signal}", ())

    def as_dict(self) -> dict:
        return {key: list(value) for key, value in sorted(self.mapping.items())}

    def __bool__(self) -> bool:
        return bool(self.mapping)


class System(Module):
    """The root module of a design."""

    entity_kind = "block"


class Part(Module):
    """A leaf module that becomes a component rather than a block.

    A part separates its logical identity from the vendor part that realizes it:
    it carries no manufacturer and no part number until one is selected, because
    inventing a vendor for a part nobody has chosen is exactly the unearned
    certainty the standard exists to prevent.
    """

    entity_kind = "component"
    designator_prefix = "U"
    package: str | None = None

    #: Which of its own surfaces this part conducts between, as pairs of surface
    #: names. A resistor bridges its two terminals; a connector bridges nothing.
    #: Declared, because nothing else in the graph says that what enters one
    #: terminal leaves at the other, and an interface that continues through a
    #: series part is otherwise indistinguishable from one that stops there.
    bridges: tuple[tuple[str, str], ...] = ()

    def __init__(self, *, package: str | None = None, **parameters) -> None:
        super().__init__(**parameters)
        if package is not None:
            self.package = package
        self.manufacturer: str | None = None
        self.mpn: str | None = None
        if self.package:
            self.add_trait(Footprint(library="Package", name=self.package))

    def select(
        self,
        manufacturer: str,
        mpn: str,
        *,
        distributor_ids: Mapping[str, str] | None = None,
        datasheet: str | None = None,
        evidence: tuple[str, ...] = (),
    ) -> "Part":
        """Select a vendor part.

        The selection attaches as sourcing; it does not replace the part's
        logical identity, so the design still says "a 3.3 V regulator" and
        separately says which one was bought.
        """
        self.manufacturer = manufacturer
        self.mpn = mpn
        self.add_trait(
            Sourcing(
                manufacturer=manufacturer,
                mpn=mpn,
                distributor_ids=dict(distributor_ids or {}),
            )
        )
        if datasheet is not None:
            self.add_trait(
                DatasheetEvidence(document=datasheet, evidence_ids=tuple(evidence))
            )
        return self

    @property
    def selected(self) -> bool:
        return self.mpn is not None


# --------------------------------------------------------------------------
# The elaboration context
# --------------------------------------------------------------------------

_CONTEXT_STACK: list["ElaborationContext"] = []


class ElaborationContext:
    """What `require()` and the connect operator talk to.

    It exists only while a program is being elaborated; outside one, declaring a
    constraint or a connection is an error rather than a silent no-op.
    """

    def __init__(self) -> None:
        self.connections: list[tuple[Surface, Surface, SourceLocation | None]] = []
        self.constraints: list[tuple[Module, Node, SourceLocation | None]] = []
        self.current: Module | None = None
        self.plan = PlanRecorder()

    def __enter__(self) -> "ElaborationContext":
        _CONTEXT_STACK.append(self)
        return self

    def __exit__(self, *exc_info) -> None:
        _CONTEXT_STACK.pop()

    def connect(self, left: Surface, right: Surface, location: SourceLocation | None) -> None:
        same_type = left.surface_type == right.surface_type
        permitted = COMPATIBLE_SURFACES.get(left.surface_type, frozenset())
        if not same_type and right.surface_type not in permitted:
            raise error(
                ELAB_UNTYPED_CONNECTION,
                f"a {left.surface_type} surface does not connect to a "
                f"{right.surface_type} surface ({left!r} to {right!r})",
                location=location,
            )
        self.connections.append((left, right, location))

    def require(self, expression: Node, location: SourceLocation | None) -> None:
        if self.current is None:
            raise error(
                ELAB_UNTYPED_CONNECTION,
                "require() is called from a module's constraints() during "
                "elaboration",
                location=location,
            )
        self.constraints.append((self.current, expression, location))


def _context() -> ElaborationContext:
    if not _CONTEXT_STACK:
        raise error(
            ELAB_UNTYPED_CONNECTION,
            "connections and constraints are declared during elaboration; "
            "a Fang program is elaborated, not executed for effect",
        )
    return _CONTEXT_STACK[-1]


def require(expression: Node) -> None:
    """Record a constraint. It is not evaluated here."""
    if not isinstance(expression, Node):
        raise error(
            UNIT_DIMENSION_MISMATCH,
            f"require() takes a constraint expression, not {expression!r}; "
            "comparing two quantities directly decides the question too early",
        )
    _context().require(expression, _caller_location(2))


def connect(left: Surface, right: Surface) -> None:
    """Record a typed connection between two surfaces."""
    _context().connect(left, right, _caller_location(2))


class _Tools:
    """The tool surface a program calls.

    Every call is recorded in the plan and returns a handle. Nothing runs here;
    a program never reaches an engine implementation directly.
    """

    def __getattr__(self, tool: str):
        if tool.startswith("_"):
            raise AttributeError(tool)

        def record(*args, **arguments) -> Handle:
            if args:
                # Positional arguments would make a plan's meaning depend on
                # order rather than on names, which a stored, replayed plan
                # cannot rely on.
                raise error(
                    ELAB_UNTYPED_CONNECTION,
                    f"tools.{tool}() takes named arguments, so the recorded plan "
                    "names what it was given",
                )
            return _context().plan.record(
                tool, arguments, source_location=_caller_location(2)
            )

        return record


#: The tool surface. ``tools.layout(...)`` records a call and returns a handle.
tools = _Tools()
