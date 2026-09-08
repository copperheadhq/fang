"""Net inference, designator assignment, and the netlist IR.

Spec: "Net Inference", "Deterministic Designator Assignment", and "The Netlist
Is A Projection".

A netlist is a projection of the graph. It names the snapshot it came from, it
contains nothing absent from that snapshot, and compiling one mutates nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Mapping, Sequence

from .entities import Component, Connection, ConnectionKind, Entity, Net, Pin
from .identity import derive
from .provenance import Actor, ActorKind, Provenance, ProvenanceOrigin, ProvenanceRecord
from .topology import CONDUCTIVE_KINDS
from .units import Quantity
from .values import Value

#: The parameter whose value becomes a part's netlist value, per designator
#: prefix. A part type with no obvious single value has none, and its value is
#: its type name rather than an invented number.
VALUE_PARAMETERS: Mapping[str, str] = {
    "R": "resistance",
    "C": "capacitance",
    "L": "inductance",
    "Y": "frequency",
    "F": "current_rating",
    "D": "forward_voltage",
    "DS": "forward_voltage",
}


class _DisjointSet:
    """Union-find. Nets are equivalence classes, so this is the natural shape."""

    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def add(self, item: str) -> None:
        self._parent.setdefault(item, item)

    def find(self, item: str) -> str:
        self.add(item)
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:     # path compression
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root == right_root:
            return
        # Deterministic: the lexicographically smaller root wins, so the result
        # does not depend on the order unions were applied.
        if left_root > right_root:
            left_root, right_root = right_root, left_root
        self._parent[right_root] = left_root

    def classes(self) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = {}
        for item in sorted(self._parent):
            grouped.setdefault(self.find(item), []).append(item)
        return grouped


@dataclass(frozen=True)
class Node:
    """One pin's membership in a net."""

    designator: str
    pin: str
    pin_id: str

    def as_dict(self) -> dict:
        return {"ref": self.designator, "pin": self.pin, "pin_id": self.pin_id}


@dataclass(frozen=True)
class NetlistNet:
    name: str
    code: int
    nodes: tuple[Node, ...]
    entity_id: str = ""

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "code": self.code,
            "entity_id": self.entity_id,
            "nodes": [node.as_dict() for node in self.nodes],
        }


@dataclass(frozen=True)
class NetlistComponent:
    designator: str
    value: str
    footprint: str | None
    entity_id: str
    manufacturer: str | None = None
    mpn: str | None = None

    def as_dict(self) -> dict:
        out = {
            "ref": self.designator,
            "value": self.value,
            "entity_id": self.entity_id,
        }
        for name, value in (
            ("footprint", self.footprint),
            ("manufacturer", self.manufacturer),
            ("mpn", self.mpn),
        ):
            if value is not None:
                out[name] = value
        return out


@dataclass(frozen=True)
class Netlist:
    """The compiled netlist. A projection, never a source of truth."""

    snapshot: str
    project_id: str
    components: tuple[NetlistComponent, ...]
    nets: tuple[NetlistNet, ...]

    def as_dict(self) -> dict:
        return {
            "parent_snapshot": self.snapshot,
            "project_id": self.project_id,
            "components": [c.as_dict() for c in self.components],
            "nets": [n.as_dict() for n in self.nets],
        }

    def net_of(self, designator: str, pin: str) -> NetlistNet | None:
        for net in self.nets:
            for node in net.nodes:
                if node.designator == designator and node.pin == pin:
                    return net
        return None


# --------------------------------------------------------------------------
# Designators
# --------------------------------------------------------------------------


def assign_designators(
    entities: Mapping[str, Entity], *, traits=None
) -> dict[str, str]:
    """Assign a designator to every component.

    Ordering is by canonical semantic path, so the same design always yields the
    same designator for the same part, independent of iteration order.
    """
    components = [e for e in entities.values() if isinstance(e, Component)]
    ordered = sorted(
        components,
        key=lambda c: (str(c.identity.path) if c.identity.path else "", c.id),
    )

    assigned: dict[str, str] = {}
    counters: dict[str, int] = {}
    taken: set[str] = {c.designator for c in components if c.designator}

    for component in ordered:
        if component.designator:
            # An authored designator is preserved, never renumbered.
            assigned[component.id] = component.designator
            continue
        prefix = _prefix_of(component)
        number = counters.get(prefix, 0) + 1
        while f"{prefix}{number}" in taken:
            number += 1
        counters[prefix] = number
        designator = f"{prefix}{number}"
        taken.add(designator)
        assigned[component.id] = designator

    return assigned


def _prefix_of(component: Component) -> str:
    """The declared prefix for the part type, recorded on the component."""
    declared = component.extensions.get("designator_prefix")
    if isinstance(declared, str) and declared:
        return declared
    return "U"


# --------------------------------------------------------------------------
# Net inference
# --------------------------------------------------------------------------


def infer_nets(entities: Mapping[str, Entity]) -> list[list[str]]:
    """The equivalence classes conductive pin connections form.

    A dependency or containment connection does not conduct, so it does not
    merge nets.
    """
    pins = {e.id for e in entities.values() if isinstance(e, Pin)}
    groups = _DisjointSet()
    for pin in sorted(pins):
        groups.add(pin)

    for connection in sorted(
        (e for e in entities.values() if isinstance(e, Connection)), key=lambda c: c.id
    ):
        if connection.connection_kind not in CONDUCTIVE_KINDS:
            continue
        if connection.source in pins and connection.target in pins:
            groups.union(connection.source, connection.target)

    # A net a source named states its own membership; it is not inferred.
    for net in sorted(
        (e for e in entities.values() if isinstance(e, Net) and e.members),
        key=lambda n: n.id,
    ):
        members = [pin for pin in sorted(net.members) if pin in pins]
        for other in members[1:]:
            groups.union(members[0], other)

    return [members for _, members in sorted(groups.classes().items())]


def _recorded_names(entities: Mapping[str, Entity]) -> dict[str, str]:
    """Pin identifier to the name a source gave the net that pin belongs to.

    Built once per compile rather than scanned per net, and keyed by pin so a
    net's name is found from any of its members.
    """
    names: dict[str, str] = {}
    for net in sorted(
        (e for e in entities.values() if isinstance(e, Net) and e.aliases and e.members),
        key=lambda n: n.id,
    ):
        name = sorted(net.aliases)[0]
        for pin in net.members:
            names.setdefault(pin, name)
    return names


def _net_name(
    members: Sequence[str],
    entities: Mapping[str, Entity],
    designators,
    recorded: Mapping[str, str],
) -> str:
    """The net's name.

    A name a source gave the net is engineering data and survives; discarding it
    and deriving a new one would be exactly the silent semantic loss an adapter
    must not commit. Only an unnamed net is named after its first node, which
    makes that name a function of membership rather than of writing order.
    """
    for pin in sorted(members):
        if pin in recorded:
            return recorded[pin]

    nodes = sorted(
        (
            (designators.get(entities[pin].owner, "?"), entities[pin].vendor_name)
            for pin in members
            if pin in entities
        )
    )
    if not nodes:
        return "Net-(unconnected)"
    designator, pin = nodes[0]
    return f"Net-({designator}-Pad{pin})"


# --------------------------------------------------------------------------
# Compilation
# --------------------------------------------------------------------------


def compile_netlist(snapshot, *, traits=None) -> Netlist:
    """Compile a snapshot into a netlist. Mutates nothing."""
    entities = snapshot.entities
    designators = assign_designators(entities)

    components = tuple(
        NetlistComponent(
            designator=designators[component.id],
            value=_value_of(component, designators[component.id]),
            footprint=_footprint_of(component, traits),
            entity_id=component.id,
            manufacturer=_trait_field(component, traits, "sourcing", "manufacturer"),
            mpn=_trait_field(component, traits, "sourcing", "mpn"),
        )
        for component in sorted(
            (e for e in entities.values() if isinstance(e, Component)),
            key=lambda c: designators[c.id],
        )
    )

    # Names a source gave, looked up once rather than scanned per net.
    recorded = _recorded_names(entities)

    nets: list[NetlistNet] = []
    for code, members in enumerate(infer_nets(entities), start=1):
        nodes = tuple(
            sorted(
                (
                    Node(
                        designators.get(entities[pin].owner, "?"),
                        entities[pin].vendor_name,
                        pin,
                    )
                    for pin in members
                    if pin in entities
                ),
                key=lambda node: (node.designator, node.pin),
            )
        )
        if len(nodes) < 2:
            # A net of one node is an unconnected pin, not a net.
            continue
        nets.append(
            NetlistNet(_net_name(members, entities, designators, recorded), code, nodes)
        )

    # Renumber after filtering so codes are dense and reproducible.
    nets = [
        NetlistNet(net.name, index, net.nodes, net.entity_id)
        for index, net in enumerate(sorted(nets, key=lambda n: n.name), start=1)
    ]

    return Netlist(snapshot.hash, snapshot.project_id, components, tuple(nets))


def _value_of(component: Component, designator: str) -> str:
    prefix = _prefix_of(component)
    parameter = VALUE_PARAMETERS.get(prefix)
    if parameter:
        value = component.parameters.get(parameter)
        if isinstance(value, Value) and value.known and value.quantity is not None:
            return str(value.quantity)
    # No invented value: the part's type is what is actually known about it.
    return component.part or prefix


def _footprint_of(component: Component, traits) -> str | None:
    field = _trait_field(component, traits, "footprint", "name")
    library = _trait_field(component, traits, "footprint", "library")
    if field is None:
        return None
    return f"{library}:{field}" if library else field


def _trait_field(component: Component, traits, protocol: str, field: str):
    if traits is None:
        return None
    trait = traits.get(component.id, protocol)
    if trait is None:
        return None
    value = getattr(trait, field, None)
    return value or None


def net_entities(
    netlist: Netlist,
    *,
    project_id: str,
    revision_id: str,
    built_at: datetime,
    connections_by_net: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Net]:
    """Record inferred nets as entities, with the provenance of their inference."""
    entities: dict[str, Net] = {}
    for net in netlist.nets:
        identity = derive(project_id, "net", f"net.{net.code:04d}")
        provenance = Provenance().append(
            ProvenanceRecord(
                ProvenanceOrigin.GENERATED,
                "net_inference",
                Actor(ActorKind.TOOL, "fang-netlist"),
                revision_id,
                built_at,
                derived_from=tuple(
                    sorted((connections_by_net or {}).get(net.name, ()))
                ),
            )
        )
        entities[identity.id] = Net(
            identity,
            aliases=(net.name,),
            provenance=provenance,
        )
    return entities
