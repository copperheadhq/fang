"""The physical layer: the compiled realization of the layers above it.

Spec: "The Physical Entity Model", "The Physical Layer Is Compiled, Never
Authoritative", and "Physical Attributes Resolve Through The Entity They
Realize".

A physical entity names the entity it realizes and never restates it, so the
board is a lowering of the graph rather than a peer source of truth for the same
facts. Identity is derived the same way as everywhere else and never from
geometry, which is what lets a part move without changing a single identifier.

Two kinds of number live here and they are kept apart deliberately. A scalar a
constraint can reason about — a width, a length, a drill — is a `Quantity`, so a
dimensional error is caught when the expression is written. Outline and path
geometry is a sequence of `Point`s in the board's declared unit, because a
polygon is not something a constraint expression compares.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterable, Mapping, Sequence

from .constraints import PHYSICAL_PREFIX
from .diagnostics import UNIT_DIMENSION_MISMATCH, error
from .entities import Entity
from .units import Quantity, _ctx, _decimal, _decimal_str
from .values import Value

# `PHYSICAL_PREFIX` is imported above rather than defined here, and re-exported
# for the layers that read it from this module. It belongs beside the evaluator:
# telling an interval spanned by copper from an interval of uncertainty is a
# decision `Comparison` makes, not one the physical layer makes.

#: The scalar attributes a constraint may reference through that prefix. Every
#: one is a quantity, because a reference evaluates to an interval. An attribute
#: outside this set resolves unknown rather than raising, exactly as a reference
#: to an absent parameter does.
PHYSICAL_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "trace_width",
        "trace_length",
        "clearance",
        "copper_weight",
        "layer_thickness",
        "board_thickness",
        "via_drill",
        "via_diameter",
        "position_x",
        "position_y",
    }
)

#: How confident an aggregate over a realization is. It is measured from
#: geometry the kernel did not compute, so it is inferred rather than explicit,
#: and it is exact for the board it was read from.
_AGGREGATE_CONFIDENCE = Decimal("1")


@dataclass(frozen=True)
class Point:
    """One coordinate pair, in the board's declared unit.

    Magnitudes are decimals, never binary floats, so geometry read twice from
    one board serializes to identical bytes.
    """

    x: Decimal
    y: Decimal

    @classmethod
    def of(cls, x, y) -> "Point":
        return cls(_decimal(x), _decimal(y))

    def as_dict(self) -> dict:
        return {"x": _decimal_str(self.x), "y": _decimal_str(self.y)}


def _points(values: Iterable) -> tuple[Point, ...]:
    return tuple(v if isinstance(v, Point) else Point.of(*v) for v in values)


def _geometry(points: Sequence[Point]) -> list[dict]:
    # A polygon's vertex order is its shape; it is preserved, never sorted.
    return [point.as_dict() for point in points]


@dataclass(frozen=True)
class PhysicalEntity(Entity):
    """The base of the physical layer.

    `realizes()` names the upper-layer entity this one is the copper, the
    placement, or the shape of. It feeds `references()`, so a physical entity
    naming an absent parent is a referential-integrity defect rather than a
    silent orphan.
    """

    def realizes(self) -> tuple[str, ...]:
        return ()

    def physical_attributes(self) -> Mapping[str, Quantity]:
        """The scalar attributes a constraint can reference on what this
        realizes. Absent values are omitted rather than defaulted."""
        return {}

    def references(self) -> tuple[str, ...]:
        return self.realizes()

    def __post_init__(self) -> None:
        _refuse_bare_magnitudes(self)


def _refuse_bare_magnitudes(entity) -> None:
    """Refuse a magnitude that is not a quantity, at construction.

    A bare number carries no unit, so nothing downstream could tell 1 oz of
    copper from 1 metre of it. Catching it here keeps the rule the rest of the
    kernel already holds: a dimensionally meaningless value cannot be stored,
    let alone evaluated.

    Board structure and the copper realizing an entity are separate hierarchies
    and both carry magnitudes, so the rule lives in one function they share
    rather than being written twice.
    """
    for name, value in entity.physical_attributes().items():
        if not isinstance(value, Quantity):
            raise error(
                UNIT_DIMENSION_MISMATCH,
                f"{entity.identity.id}.{name} is {value!r}, which carries no "
                "unit; a physical magnitude is a Quantity",
                entities=[entity.identity.id],
            )


def _attributes(*pairs: tuple[str, Quantity | None]) -> dict[str, Quantity]:
    return {name: value for name, value in pairs if value is not None}


@dataclass(frozen=True)
class Layer(Entity):
    """One layer of a stackup, copper or dielectric."""

    kind: str = "layer"
    layer_name: str = ""
    function: str = "signal"
    copper_weight: Quantity | None = None
    thickness: Quantity | None = None

    def __post_init__(self) -> None:
        _refuse_bare_magnitudes(self)

    def physical_attributes(self) -> Mapping[str, Quantity]:
        return _attributes(
            ("copper_weight", self.copper_weight),
            ("layer_thickness", self.thickness),
        )

    def as_dict(self) -> dict:
        out = self._base_dict()
        out["layer_name"] = self.layer_name
        out["function"] = self.function
        if self.copper_weight is not None:
            out["copper_weight"] = self.copper_weight.as_dict()
        if self.thickness is not None:
            out["thickness"] = self.thickness.as_dict()
        return out


@dataclass(frozen=True)
class Stackup(Entity):
    """The layers of a board, ordered top to bottom.

    The order is the stackup; serialization preserves it rather than sorting it.
    """

    kind: str = "stackup"
    layers: tuple[str, ...] = ()

    def references(self) -> tuple[str, ...]:
        return self.layers

    def as_dict(self) -> dict:
        out = self._base_dict()
        out["layers"] = list(self.layers)
        return out


@dataclass(frozen=True)
class Board(Entity):
    """A board: its outline, its stackup, and the unit its geometry is in."""

    kind: str = "board"
    stackup: str | None = None
    outline: tuple[Point, ...] = ()
    thickness: Quantity | None = None
    unit: str = "mm"

    def __post_init__(self) -> None:
        _refuse_bare_magnitudes(self)

    def physical_attributes(self) -> Mapping[str, Quantity]:
        return _attributes(("board_thickness", self.thickness))

    def references(self) -> tuple[str, ...]:
        return (self.stackup,) if self.stackup else ()

    def as_dict(self) -> dict:
        out = self._base_dict()
        out["unit"] = self.unit
        if self.stackup is not None:
            out["stackup"] = self.stackup
        if self.outline:
            out["outline"] = _geometry(self.outline)
        if self.thickness is not None:
            out["thickness"] = self.thickness.as_dict()
        return out


@dataclass(frozen=True)
class Placement(PhysicalEntity):
    """Where a component sits.

    This is the placed instance. Which library footprint the component uses is
    the `Footprint` trait's business and is not restated here.
    """

    kind: str = "placement"
    component: str = ""
    layer: str | None = None
    x: Quantity | None = None
    y: Quantity | None = None
    rotation: Quantity | None = None

    def realizes(self) -> tuple[str, ...]:
        return (self.component,) if self.component else ()

    def physical_attributes(self) -> Mapping[str, Quantity]:
        return _attributes(("position_x", self.x), ("position_y", self.y))

    def references(self) -> tuple[str, ...]:
        return self.realizes() + ((self.layer,) if self.layer else ())

    def as_dict(self) -> dict:
        out = self._base_dict()
        out["component"] = self.component
        if self.layer is not None:
            out["layer"] = self.layer
        for name, value in (("x", self.x), ("y", self.y), ("rotation", self.rotation)):
            if value is not None:
                out[name] = value.as_dict()
        return out


@dataclass(frozen=True)
class Pad(PhysicalEntity):
    """One pad of a placement, realizing one pin."""

    kind: str = "pad"
    pin: str = ""
    placement: str | None = None
    layer: str | None = None
    pad_number: str = ""
    at: Point | None = None

    def realizes(self) -> tuple[str, ...]:
        return (self.pin,) if self.pin else ()

    def references(self) -> tuple[str, ...]:
        extra = tuple(x for x in (self.placement, self.layer) if x)
        return self.realizes() + extra

    def as_dict(self) -> dict:
        out = self._base_dict()
        out["pin"] = self.pin
        out["pad_number"] = self.pad_number
        for name, value in (("placement", self.placement), ("layer", self.layer)):
            if value is not None:
                out[name] = value
        if self.at is not None:
            out["at"] = self.at.as_dict()
        return out


@dataclass(frozen=True)
class Trace(PhysicalEntity):
    """One routed segment: the copper of a net."""

    kind: str = "trace"
    net: str = ""
    layer: str | None = None
    width: Quantity | None = None
    length: Quantity | None = None
    path: tuple[Point, ...] = ()

    def realizes(self) -> tuple[str, ...]:
        return (self.net,) if self.net else ()

    def physical_attributes(self) -> Mapping[str, Quantity]:
        return _attributes(
            ("trace_width", self.width), ("trace_length", self.length)
        )

    def references(self) -> tuple[str, ...]:
        return self.realizes() + ((self.layer,) if self.layer else ())

    def as_dict(self) -> dict:
        out = self._base_dict()
        out["net"] = self.net
        if self.layer is not None:
            out["layer"] = self.layer
        for name, value in (("width", self.width), ("length", self.length)):
            if value is not None:
                out[name] = value.as_dict()
        if self.path:
            out["path"] = _geometry(self.path)
        return out


@dataclass(frozen=True)
class Via(PhysicalEntity):
    """One via on a net, between two layers."""

    kind: str = "via"
    net: str = ""
    layers: tuple[str, ...] = ()
    drill: Quantity | None = None
    diameter: Quantity | None = None
    at: Point | None = None

    def realizes(self) -> tuple[str, ...]:
        return (self.net,) if self.net else ()

    def physical_attributes(self) -> Mapping[str, Quantity]:
        return _attributes(
            ("via_drill", self.drill), ("via_diameter", self.diameter)
        )

    def references(self) -> tuple[str, ...]:
        return self.realizes() + self.layers

    def as_dict(self) -> dict:
        out = self._base_dict()
        out["net"] = self.net
        if self.layers:
            # A via's layer pair is ordered: it runs from the first to the last.
            out["layers"] = list(self.layers)
        for name, value in (("drill", self.drill), ("diameter", self.diameter)):
            if value is not None:
                out[name] = value.as_dict()
        if self.at is not None:
            out["at"] = self.at.as_dict()
        return out


@dataclass(frozen=True)
class Zone(PhysicalEntity):
    """A filled copper region, usually poured on a net."""

    kind: str = "zone"
    net: str | None = None
    layer: str | None = None
    clearance: Quantity | None = None
    outline: tuple[Point, ...] = ()

    def realizes(self) -> tuple[str, ...]:
        return (self.net,) if self.net else ()

    def physical_attributes(self) -> Mapping[str, Quantity]:
        return _attributes(("clearance", self.clearance))

    def references(self) -> tuple[str, ...]:
        return self.realizes() + ((self.layer,) if self.layer else ())

    def as_dict(self) -> dict:
        out = self._base_dict()
        if self.net is not None:
            out["net"] = self.net
        if self.layer is not None:
            out["layer"] = self.layer
        if self.clearance is not None:
            out["clearance"] = self.clearance.as_dict()
        if self.outline:
            out["outline"] = _geometry(self.outline)
        return out


@dataclass(frozen=True)
class Region(PhysicalEntity):
    """A named area of the board: a keepout, a courtyard, a placement region.

    A region realizes nothing on its own; it constrains what may sit inside it.
    """

    kind: str = "region"
    region_kind: str = "keepout"
    layer: str | None = None
    applies_to: tuple[str, ...] = ()
    outline: tuple[Point, ...] = ()

    def references(self) -> tuple[str, ...]:
        return self.applies_to + ((self.layer,) if self.layer else ())

    def as_dict(self) -> dict:
        out = self._base_dict()
        out["region_kind"] = self.region_kind
        if self.layer is not None:
            out["layer"] = self.layer
        if self.applies_to:
            out["applies_to"] = sorted(self.applies_to)
        if self.outline:
            out["outline"] = _geometry(self.outline)
        return out


#: Every physical entity kind, and the root key each is collected under. The
#: `physical` root is a mapping rather than a list, so these do not belong in
#: `graph._COLLECTION_OF`.
PHYSICAL_COLLECTIONS: Mapping[str, str] = {
    "board": "boards",
    "stackup": "stackups",
    "layer": "layers",
    "placement": "placements",
    "pad": "pads",
    "trace": "traces",
    "via": "vias",
    "zone": "zones",
    "region": "regions",
}

#: In root order, so the mapping serializes with every key present.
PHYSICAL_KEYS: tuple[str, ...] = (
    "boards",
    "stackups",
    "layers",
    "placements",
    "pads",
    "traces",
    "vias",
    "zones",
    "regions",
)


# --------------------------------------------------------------------------
# Resolving a physical attribute through the entity it realizes
# --------------------------------------------------------------------------


def _index(entities: Mapping[str, Entity]) -> dict[tuple[str, str], list[Quantity]]:
    """Every scalar attribute, keyed by the entity it is an attribute *of*.

    A physical entity contributes to the entity it realizes, so a trace's width
    is an attribute of its net. An entity that realizes nothing contributes its
    attributes to itself, which is how a board's thickness is reachable.
    """
    index: dict[tuple[str, str], list[Quantity]] = {}
    for entity in entities.values():
        attributes = getattr(entity, "physical_attributes", None)
        if attributes is None:
            continue
        values = attributes()
        if not values:
            continue
        realized = entity.realizes() if isinstance(entity, PhysicalEntity) else ()
        owners = realized or (entity.id,)
        for owner in owners:
            for name, quantity in values.items():
                index.setdefault((owner, name), []).append(quantity)
    return index


def _span(quantities: Sequence[Quantity], source: str) -> Value:
    """The interval a realization spans, as one inferred value.

    Several segments realize one net, so the reference resolves to what they
    span rather than to any one of them. A rule then holds over the whole
    realization: a minimum fails if the narrowest segment fails, and a maximum
    fails if the widest does.
    """
    unit = quantities[0].unit
    if any(q.dimension != unit.dimension for q in quantities):
        # Two realizations disagreeing about what the attribute even measures is
        # not something to average. It is unknown until someone reconciles it.
        return Value.unknown()

    low = None
    high = None
    for quantity in quantities:
        bottom, top = quantity.interval()
        low = bottom if low is None or bottom < low else low
        high = top if high is None or top > high else high

    # `interval()` is in SI base units. Convert back through the first operand's
    # unit so the value reads in the unit the board was authored in.
    with _ctx():
        minimum = (low - unit.offset) / unit.factor
        maximum = (high - unit.offset) / unit.factor
    if minimum == maximum:
        quantity = Quantity.scalar(minimum, unit)
    else:
        quantity = Quantity.range(minimum, maximum, unit)
    return Value.inferred(quantity, source=source, confidence=_AGGREGATE_CONFIDENCE)


def physical_resolver(entities: Mapping[str, Entity]):
    """Resolve a `physical.`-prefixed attribute over what realizes an entity.

    An attribute outside `PHYSICAL_ATTRIBUTES`, or one nothing realizes,
    resolves unknown. Undecided is the honest answer about copper that does not
    exist yet, and it is never a pass.
    """
    index = _index(entities)

    def resolve(entity_id: str, attr: str) -> Value | None:
        if attr not in PHYSICAL_ATTRIBUTES:
            return Value.unknown()
        quantities = index.get((entity_id, attr))
        if not quantities:
            return Value.unknown()
        return _span(quantities, source=entity_id)

    return resolve
