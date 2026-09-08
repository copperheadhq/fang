"""Topology intent and its verification.

Spec: "Topology Intent Separate From Electrical Equivalence" and "Topology
Verification Enumerates Conductive Paths".

A netlist collapses every electrically equivalent point into one net. That is
correct as connectivity and insufficient as engineering intent, so intent lives
here as a constraint and is verified by enumerating conductive paths — naming
them, never counting them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Sequence

from .constraints import (
    CheckStatus,
    Constraint,
    ConstraintClass,
    Enforcement,
    Literal,
    Node,
    Truth,
)
from .diagnostics import Severity
from .entities import Connection, ConnectionKind, Entity

#: Connection kinds that conduct: everything realized as copper. A dependency,
#: containment, control, or mechanical edge is a relation rather than a
#: conductor, and does not join two points electrically.
CONDUCTIVE_KINDS = frozenset(
    {
        ConnectionKind.ELECTRICAL,
        ConnectionKind.POWER,
        ConnectionKind.GROUND,
        ConnectionKind.SIGNAL,
    }
)

#: A component carrying this parameter conducts only under the stated condition,
#: such as a protection diode or a test jumper. The condition becomes part of any
#: finding that names a path through it.
CONDUCTION_CONDITION = "conduction_condition"


class TopologyMode(Enum):
    STAR = "star"
    SINGLE_POINT = "single_point"
    DAISY_CHAIN = "daisy_chain"
    KELVIN = "kelvin"
    MESH = "mesh"


@dataclass(frozen=True)
class ConductivePath:
    """One conductive path, named by the elements that form it."""

    elements: tuple[str, ...]
    conditions: tuple[tuple[str, str], ...] = ()

    @property
    def conditional(self) -> bool:
        return bool(self.conditions)

    def passes_through(self, node: str) -> bool:
        return node in self.elements

    def as_dict(self) -> dict:
        out: dict = {"elements": list(self.elements)}
        if self.conditions:
            out["conditions"] = [
                {"element": element, "condition": condition}
                for element, condition in self.conditions
            ]
        return out

    def __str__(self) -> str:
        rendered = " -> ".join(self.elements)
        if self.conditions:
            qualifiers = ", ".join(f"{e} conducts when {c}" for e, c in self.conditions)
            return f"{rendered} [{qualifiers}]"
        return rendered


def _adjacency(entities: Mapping[str, Entity]) -> dict[str, set[str]]:
    """Build the conductive adjacency on demand from typed entities.

    The analysis graph is constructed from typed entities and thrown away; it is
    never a public representation.
    """
    adjacency: dict[str, set[str]] = {}
    for entity in entities.values():
        if not isinstance(entity, Connection):
            continue
        if entity.connection_kind not in CONDUCTIVE_KINDS:
            continue
        adjacency.setdefault(entity.source, set()).add(entity.target)
        adjacency.setdefault(entity.target, set()).add(entity.source)
    return adjacency


def enumerate_paths(
    entities: Mapping[str, Entity],
    sources: Iterable[str],
    targets: Iterable[str],
    *,
    max_length: int = 24,
) -> list[ConductivePath]:
    """Enumerate the simple conductive paths between two entity sets.

    Deterministic: neighbours are visited in sorted order, so the same graph
    always yields the same paths in the same order.
    """
    adjacency = _adjacency(entities)
    target_set = set(targets)
    found: list[ConductivePath] = []

    def condition_of(node: str) -> str | None:
        entity = entities.get(node)
        if entity is None:
            return None
        parameter = entity.parameters.get(CONDUCTION_CONDITION)
        rationale = getattr(parameter, "rationale", None)
        if rationale:
            return rationale
        quantity = getattr(parameter, "quantity", None)
        return str(quantity) if quantity is not None else None

    def walk(node: str, trail: list[str], seen: set[str]) -> None:
        if len(trail) > max_length:
            return
        if node in target_set and len(trail) > 1:
            conditions = tuple(
                (element, condition_of(element))
                for element in trail
                if condition_of(element) is not None
            )
            found.append(ConductivePath(tuple(trail), conditions))
            return
        for neighbour in sorted(adjacency.get(node, ())):
            if neighbour in seen:
                continue
            walk(neighbour, trail + [neighbour], seen | {neighbour})

    for source in sorted(set(sources)):
        walk(source, [source], {source})
    return found


@dataclass(frozen=True)
class TopologyConstraint(Constraint):
    """Topology intent, persisted as a constraint within the one registry.

    It names the net or domain it governs, the mode, the centre or bonding point
    where one applies, the permitted branches, and whether parallel conductive
    paths are forbidden. Domains and bonding points are entities in their own
    right and are referenced by identity.
    """

    constraint_class: ConstraintClass = ConstraintClass.TOPOLOGY
    constraint_kind: str = "topology"
    net: str = ""
    mode: TopologyMode = TopologyMode.STAR
    center: str | None = None
    branches: tuple[str, ...] = ()
    forbid_parallel_paths: bool = True
    expression: Node | None = field(default_factory=lambda: Literal.of(True))

    def __post_init__(self) -> None:
        if not self.net:
            raise ValueError("a topology constraint names the net or domain it governs")
        if self.mode in (TopologyMode.STAR, TopologyMode.SINGLE_POINT) and not self.center:
            raise ValueError(f"a {self.mode.value} topology names its centre")
        object.__setattr__(self, "targets", self.targets or (self.net,))
        super().__post_init__()

    def references(self) -> tuple[str, ...]:
        refs = (self.net,) + self.branches + tuple(self.targets)
        if self.center:
            refs += (self.center,)
        if self.source:
            refs += (self.source,)
        return refs

    def as_dict(self) -> dict:
        out = super().as_dict()
        out.update(
            {
                "net": self.net,
                "mode": self.mode.value,
                # Branch order carries the engineer's intent and is preserved.
                "branches": list(self.branches),
                "forbid_parallel_paths": self.forbid_parallel_paths,
            }
        )
        if self.center is not None:
            out["center"] = self.center
        return out

    def verify(self, entities: Mapping[str, Entity]):
        """Enumerate the conductive paths and report each unpermitted one.

        Returns findings, one per unpermitted path, each naming the elements that
        form it. A count alone would be insufficient.
        """
        from .graph import CheckResult

        findings: list[CheckResult] = []
        branches = list(self.branches)
        if len(branches) < 2:
            return [
                CheckResult(
                    "topology",
                    CheckStatus.NOT_APPLICABLE,
                    self.id,
                    "a topology constraint with fewer than two branches has no "
                    "path to compare",
                )
            ]

        unpermitted: list[ConductivePath] = []
        for index, source in enumerate(branches):
            others = branches[index + 1 :]
            for path in enumerate_paths(entities, [source], others):
                # A path is permitted when it bonds through the named centre.
                if self.center is not None and path.passes_through(self.center):
                    continue
                unpermitted.append(path)

        if not unpermitted:
            return [
                CheckResult(
                    "topology",
                    CheckStatus.PASS,
                    self.id,
                    f"{self.mode.value} topology on {self.net} holds"
                    + (f" through {self.center}" if self.center else ""),
                )
            ]

        for path in unpermitted:
            findings.append(
                CheckResult(
                    "topology",
                    CheckStatus.FAIL,
                    self.id,
                    message=(
                        f"unpermitted conductive path on {self.net}: {path}"
                        + (
                            f"; expected the bond through {self.center}"
                            if self.center
                            else ""
                        )
                    ),
                    severity=Severity.ERROR
                    if self.enforcement is Enforcement.HARD
                    else Severity.WARNING,
                    paths=(path.elements,),
                )
            )
        return findings


def topology_check(snapshot) -> list:
    """The topology check class, over every topology constraint in the graph."""
    results = []
    for entity in snapshot.entities.values():
        if isinstance(entity, TopologyConstraint):
            results.extend(entity.verify(snapshot.entities))
    return results


def topology_scope(snapshot) -> set[str]:
    scope: set[str] = set()
    for entity in snapshot.entities.values():
        if isinstance(entity, TopologyConstraint):
            scope |= {entity.id, entity.net, *entity.branches}
            if entity.center:
                scope.add(entity.center)
    return scope
