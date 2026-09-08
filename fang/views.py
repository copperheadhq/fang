"""Views: deterministic projections of graph state.

Spec: "Views Are Deterministic Projections", "The View Specification", "The
Required Views", "A View Contains Nothing Absent From Its Snapshot", and "The
Layout Boundary".

A view answers one engineering question. It is generated only from facts in the
graph, and it exposes what is incomplete rather than hiding it, because an
attractive diagram over incomplete data is worse than no diagram.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Mapping, Sequence

from .constraints import Constraint, ConstraintClass
from .entities import (
    Component,
    Connection,
    ConnectionKind,
    Domain,
    Entity,
    Interface,
    Net,
    Pin,
    Port,
    Rail,
    Requirement,
)
from .topology import TopologyConstraint
from .values import Value, ValueStatus


@dataclass(frozen=True)
class ViewSpec:
    """What a view includes and what it annotates.

    Recorded with the compiled view, so the question a diagram answers is
    inspectable and the diagram is reproducible without a model.
    """

    name: str
    question: str
    include_kinds: tuple[str, ...] = ()
    edge_kinds: tuple[ConnectionKind, ...] = ()
    annotations: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "question": self.question,
            "include_kinds": list(self.include_kinds),
            "edge_kinds": [kind.value for kind in self.edge_kinds],
            "annotations": list(self.annotations),
        }


@dataclass(frozen=True)
class ViewNode:
    id: str                 # the entity this node is
    label: str
    kind: str
    detail: str = ""        # the second line: what the label alone leaves out
    parent: str | None = None
    ports: tuple[str, ...] = ()
    annotations: tuple[str, ...] = ()
    incomplete: tuple[str, ...] = ()     # parameters this node does not know

    def as_dict(self) -> dict:
        out: dict = {"id": self.id, "label": self.label, "kind": self.kind}
        if self.detail:
            out["detail"] = self.detail
        if self.parent:
            out["parent"] = self.parent
        if self.ports:
            out["ports"] = list(self.ports)
        if self.annotations:
            out["annotations"] = list(self.annotations)
        if self.incomplete:
            out["incomplete"] = list(self.incomplete)
        return out


@dataclass(frozen=True)
class ViewEdge:
    id: str                 # the connection entity this edge is
    source: str
    target: str
    edge_class: str
    annotations: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        out = {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "class": self.edge_class,
        }
        if self.annotations:
            out["annotations"] = list(self.annotations)
        return out


@dataclass(frozen=True)
class ViewGraph:
    """A compiled view. Everything in it names an entity in the snapshot."""

    spec: ViewSpec
    snapshot: str
    nodes: tuple[ViewNode, ...]
    edges: tuple[ViewEdge, ...]
    notes: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        return not any(node.incomplete for node in self.nodes)

    def completeness(self) -> dict:
        """What this view does not know. Reported, never hidden."""
        unknown = {node.id: list(node.incomplete) for node in self.nodes if node.incomplete}
        return {
            "complete": not unknown,
            "nodes_with_unknowns": len(unknown),
            "unknown": unknown,
        }

    def as_dict(self) -> dict:
        return {
            "spec": self.spec.as_dict(),
            "snapshot": self.snapshot,
            "nodes": [node.as_dict() for node in self.nodes],
            "edges": [edge.as_dict() for edge in self.edges],
            "completeness": self.completeness(),
            "notes": list(self.notes),
        }


# --------------------------------------------------------------------------
# The compiler
# --------------------------------------------------------------------------


def _incomplete_parameters(entity: Entity) -> tuple[str, ...]:
    return tuple(
        sorted(
            name
            for name, value in entity.parameters.items()
            if isinstance(value, Value) and value.status is ValueStatus.UNKNOWN
        )
    )


def _label(entity: Entity) -> tuple[str, str]:
    """What to write on a node: a name, and the line under it.

    The name has to be the one the reader can find again — the instance name
    the program gave it. A class name is not that: a board with four resistors
    on it draws four boxes that all say Resistor, which tells the reader
    nothing about which one carries the fault. So the instance name leads and
    the class goes underneath, where it is still worth having.
    """
    path = str(entity.identity.path) if entity.identity.path else ""
    name = entity.identity.display_name
    leaf = path.rsplit(".", 1)[-1] if path else ""
    kind = str(
        getattr(entity, "interface_type", None)
        or getattr(entity, "vendor_name", None)
        or entity.kind
    )

    # Inside a repeated block the leaf alone is ambiguous — three half bridges
    # each own a transistor called `high` — so a nested node carries its parent
    # with it, which is also how the program names it.
    segments = path.split(".")
    qualified = ".".join(segments[-2:]) if len(segments) > 2 else leaf

    if designator := getattr(entity, "designator", None):
        label, detail = str(designator), name or kind
    elif name and leaf and leaf != name and "." in path:
        label, detail = qualified, name
    else:
        label, detail = name or leaf or entity.id, kind

    # A second line repeating the first one is a line that says nothing; the
    # renderer falls back to the entity kind, which at least says what it is.
    return label, "" if detail == label else detail


def compile_view(snapshot, spec: ViewSpec) -> ViewGraph:
    """Project a snapshot into a view graph.

    Deterministic: entities are visited in identifier order, so repeated
    generation from unchanged state gives an identical graph.
    """
    entities = snapshot.entities
    included: dict[str, Entity] = {
        entity.id: entity
        for entity in sorted(entities.values(), key=lambda e: e.id)
        if entity.kind in spec.include_kinds
    }

    # Pins and ports are drawn on their owner rather than as nodes of their own.
    owner_of: dict[str, str] = {}
    for entity in entities.values():
        if isinstance(entity, (Pin, Port)) and entity.owner in included:
            owner_of[entity.id] = entity.owner

    annotations = _annotations(entities, spec)

    nodes = []
    for entity in included.values():
        label, detail = _label(entity)
        nodes.append(
            ViewNode(
                entity.id,
                label,
                entity.kind,
                detail=detail,
                ports=tuple(sorted(k for k, v in owner_of.items() if v == entity.id)),
                annotations=tuple(sorted(annotations.get(entity.id, ()))),
                incomplete=_incomplete_parameters(entity),
            )
        )

    edges: list[ViewEdge] = []
    for entity in sorted(entities.values(), key=lambda e: e.id):
        if not isinstance(entity, Connection):
            continue
        if spec.edge_kinds and entity.connection_kind not in spec.edge_kinds:
            continue
        source = owner_of.get(entity.source, entity.source)
        target = owner_of.get(entity.target, entity.target)
        if source not in included or target not in included:
            continue
        edges.append(
            ViewEdge(
                entity.id,
                source,
                target,
                entity.connection_kind.value,
                annotations=tuple(sorted(annotations.get(entity.id, ()))),
            )
        )

    notes = _notes(entities, spec)
    return ViewGraph(spec, snapshot.hash, tuple(nodes), tuple(edges), notes)


def _annotations(entities: Mapping[str, Entity], spec: ViewSpec) -> dict[str, list[str]]:
    """Annotations come from graph facts, never from anything invented."""
    found: dict[str, list[str]] = {}
    if not spec.annotations:
        return found

    for entity in sorted(entities.values(), key=lambda e: e.id):
        if "star_point" in spec.annotations and isinstance(entity, TopologyConstraint):
            if entity.center:
                found.setdefault(entity.center, []).append(f"star point of {entity.net}")
            for branch in entity.branches:
                found.setdefault(branch, []).append(f"branch of {entity.id}")
        if "topology_intent" in spec.annotations and isinstance(entity, TopologyConstraint):
            found.setdefault(entity.net, []).append(
                f"{entity.mode.value} topology, {len(entity.branches)} branches"
            )
        if "domain" in spec.annotations and isinstance(entity, Domain):
            for member in entity.members:
                found.setdefault(member, []).append(f"{entity.domain_kind} domain {entity.id}")
        if "hard_constraint" in spec.annotations and isinstance(entity, Constraint):
            for target in entity.targets:
                found.setdefault(target, []).append(
                    f"{entity.constraint_kind} ({entity.enforcement.value})"
                )
        if "requirement" in spec.annotations and isinstance(entity, Requirement):
            found.setdefault(entity.id, []).append(entity.state.value)
    return found


def _notes(entities: Mapping[str, Entity], spec: ViewSpec) -> tuple[str, ...]:
    notes: list[str] = []
    if "topology_intent" in spec.annotations:
        constraints = [e for e in entities.values() if isinstance(e, TopologyConstraint)]
        if constraints:
            notes.append(
                f"{len(constraints)} topology constraint(s) express intent that net "
                "membership alone does not carry"
            )
        else:
            notes.append("no topology intent is recorded for this design")
    return tuple(notes)


# --------------------------------------------------------------------------
# The required views
# --------------------------------------------------------------------------

SYSTEM = ViewSpec(
    "system",
    "What blocks and parts does this design contain, and how do they nest?",
    include_kinds=("block", "component"),
    annotations=("hard_constraint",),
)

INTERCONNECT = ViewSpec(
    "interconnect",
    "What is connected to what?",
    include_kinds=("component", "block"),
    edge_kinds=(
        ConnectionKind.ELECTRICAL,
        ConnectionKind.POWER,
        ConnectionKind.GROUND,
        ConnectionKind.SIGNAL,
    ),
)

POWER = ViewSpec(
    "power",
    "Where does power come from and where does it go?",
    include_kinds=("component", "block", "rail"),
    edge_kinds=(ConnectionKind.POWER,),
    annotations=("domain",),
)

GROUND = ViewSpec(
    "ground",
    "How do returns get home, and is the intended topology held?",
    include_kinds=("component", "block", "net", "domain"),
    edge_kinds=(ConnectionKind.GROUND,),
    annotations=("star_point", "topology_intent", "domain"),
)

INTERFACES = ViewSpec(
    "interfaces",
    "Which typed interfaces exist and what do they join?",
    include_kinds=("component", "block", "interface"),
    edge_kinds=(ConnectionKind.SIGNAL,),
)

SAFETY = ViewSpec(
    "safety",
    "Which requirements and hard constraints govern this design?",
    include_kinds=("component", "block", "requirement"),
    annotations=("requirement", "hard_constraint"),
)

#: Every view the implementation provides, by name.
REGISTRY: Mapping[str, ViewSpec] = {
    spec.name: spec
    for spec in (SYSTEM, INTERCONNECT, POWER, GROUND, INTERFACES, SAFETY)
}

REQUIRED_VIEWS = ("system", "interconnect", "power", "ground", "interfaces", "safety")


def view(snapshot, name: str) -> ViewGraph:
    """Compile a named view."""
    if name not in REGISTRY:
        raise KeyError(f"no view named {name!r}; known views: {', '.join(sorted(REGISTRY))}")
    return compile_view(snapshot, REGISTRY[name])
