"""Rationale queries and graph analysis.

Spec: "Rationale Queries Answerable From Graph State". Every query here is
computed from graph structure alone, with no model call and no inference step.

Analysis graphs are constructed from typed entities on demand. Node dictionaries
are never returned from a public API, so the analysis library stays replaceable.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from .diff import Diff, ChangeClass
from .entities import Component, Decision, Entity, Evidence, Requirement, RequirementState
from .provenance import ProvenanceOrigin
from .values import Value, ValueStatus


def _entities(source) -> Mapping[str, Entity]:
    return source.entities if hasattr(source, "entities") else source


def causing_requirements(snapshot, component_id: str) -> list[str]:
    """Which requirement caused this component to exist.

    Walks provenance ``derived_from`` and the decisions that cite requirements,
    so the answer is the recorded chain rather than a guess.
    """
    entities = _entities(snapshot)
    entity = entities.get(component_id)
    if entity is None:
        return []

    found: set[str] = set()
    frontier = [component_id]
    seen: set[str] = set()

    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        node = entities.get(current)
        if node is None:
            continue
        if isinstance(node, Requirement):
            found.add(node.id)
            continue
        for record in node.provenance:
            frontier.extend(record.derived_from)
        if isinstance(node, Decision):
            found.update(node.requirements)
        for other in entities.values():
            if isinstance(other, Decision) and other.choice == current:
                frontier.append(other.id)

    return sorted(found)


def supporting_evidence(snapshot, entity_id: str, parameter: str) -> list[str]:
    """Which datasheet claim supports this parameter."""
    entities = _entities(snapshot)
    entity = entities.get(entity_id)
    if entity is None:
        return []
    value = entity.parameters.get(parameter)
    sources: set[str] = set()
    if isinstance(value, Value) and value.source:
        sources.add(value.source)
    candidates = getattr(value, "candidates", ())
    for candidate in candidates:
        sources.add(candidate.source)
    return sorted(s for s in sources if isinstance(entities.get(s), Evidence) or s in entities)


def dependents(snapshot, entity_id: str) -> list[str]:
    """What depends on this rail, oscillator, or domain."""
    entities = _entities(snapshot)
    return sorted(
        other.id
        for other in entities.values()
        if other.id != entity_id and entity_id in other.references()
    )


def lost_verification(snapshot, changes: Diff) -> list[str]:
    """Which requirements lost verification in this change."""
    entities = _entities(snapshot)
    lost: set[str] = set()
    for change in changes:
        for reference in change.impact:
            entity = entities.get(reference)
            if isinstance(entity, Requirement) and entity.state is not RequirementState.VERIFIED:
                lost.add(entity.id)
        if change.type is ChangeClass.VERIFICATION_STATUS_CHANGED:
            subject = entities.get(change.subject)
            source = getattr(subject, "source", None)
            if isinstance(entities.get(source), Requirement):
                lost.add(source)
    return sorted(lost)


def unverified_assumptions(snapshot) -> list[str]:
    """Which assumptions are still unverified.

    Both kinds count: a requirement sitting in ASSUMED, and a parameter carrying
    an assumed value with no evidence behind it.
    """
    entities = _entities(snapshot)
    found: set[str] = set()
    for entity in entities.values():
        if isinstance(entity, Requirement) and entity.state is RequirementState.ASSUMED:
            found.add(entity.id)
        for name, value in entity.parameters.items():
            if isinstance(value, Value) and value.status is ValueStatus.ASSUMED:
                found.add(f"{entity.id}.{name}")
    return sorted(found)


def decisions_on_changed_evidence(snapshot, changed_evidence: Iterable[str]) -> list[str]:
    """Which decisions rest on evidence that has since changed."""
    entities = _entities(snapshot)
    changed = set(changed_evidence)
    found: set[str] = set()
    for entity in entities.values():
        if not isinstance(entity, Decision):
            continue
        cited = set(entity.references()) | set(entity.requirements)
        for record in entity.provenance:
            cited.update(record.derived_from)
            cited.update(i.id for i in record.inputs)
        if cited & changed:
            found.add(entity.id)
    return sorted(found)


# --------------------------------------------------------------------------
# Analysis graph
# --------------------------------------------------------------------------


def to_networkx(snapshot, *, conductive_only: bool = False):
    """Build a NetworkX graph on demand from typed entities.

    The graph is a disposable analysis artifact. It is never persisted and never
    exposed as a Copperhead representation.
    """
    try:
        import networkx as nx
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise ImportError(
            "graph analysis needs networkx; install the 'analysis' extra"
        ) from exc

    from .entities import Connection
    from .topology import CONDUCTIVE_KINDS

    entities = _entities(snapshot)
    graph = nx.Graph()
    for entity in entities.values():
        graph.add_node(entity.id, kind=entity.kind)
    for entity in entities.values():
        if not isinstance(entity, Connection):
            continue
        if conductive_only and entity.connection_kind not in CONDUCTIVE_KINDS:
            continue
        graph.add_edge(
            entity.source, entity.target, kind=entity.connection_kind.value, id=entity.id
        )
    return graph
