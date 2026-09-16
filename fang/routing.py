"""The layout constraint classes, and their projection to a layout tool.

Spec: "Routing And Placement Constraints Are Checked By The Gate" and "Emitted
Design Rules Are Projections".

There is one constraint registry and one evaluator. A check class here is a
selection over that registry and a scope over the entities it targets — it is
not a second rule engine, and an emitted rule file is not a second store.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Mapping, Sequence

from .constraints import (
    LAYOUT_CLASSES,
    PHYSICAL_PREFIX,
    CheckStatus,
    Constraint,
    Enforcement,
    Projection,
    Ref,
)
from .diagnostics import (
    TOPO_UNRESOLVED_PHYSICAL_REFERENCE,
    Diagnostic,
    Severity,
)
from .entities import Net
from .graph import CheckClass, CheckResult
from .physical import PhysicalEntity

# `LAYOUT_CLASSES` is imported from `constraints`, where the set is defined, and
# re-exported here: this check class covers exactly those classes, and the
# remainder stay with the structural constraint check, so every class is covered
# exactly once.

#: How an enforcement level reports. A violation's treatment is the constraint's
#: to declare; the evaluator only says whether it holds.
_SEVERITY: Mapping[Enforcement, Severity] = {
    Enforcement.HARD: Severity.ERROR,
    Enforcement.SOFT: Severity.WARNING,
    Enforcement.ADVISORY: Severity.INFO,
}


def is_layout_constraint(entity) -> bool:
    return isinstance(entity, Constraint) and entity.constraint_class in LAYOUT_CLASSES


def _realizations(entities: Mapping[str, object], target: str) -> list[str]:
    """The physical entities realizing a target, for a finding to name."""
    return sorted(
        entity.id
        for entity in entities.values()
        if isinstance(entity, PhysicalEntity) and target in entity.realizes()
    )


def _gaps(constraint: Constraint, entities: Mapping[str, object]) -> tuple[str, ...]:
    """What an undecided result was missing.

    A routing rule is undecided because the copper it is about does not exist
    yet, so the gap to name is the target with nothing realizing it.
    """
    missing = []
    for reference in constraint.expression.references():
        if reference in constraint.targets and not _realizations(entities, reference):
            missing.append(reference)
    return tuple(sorted(set(missing)))


def routing_check(snapshot) -> list[CheckResult]:
    """Evaluate every layout-class constraint in the graph."""
    resolve = snapshot.resolver()
    results: list[CheckResult] = []
    for entity in snapshot.entities.values():
        if not is_layout_constraint(entity):
            continue
        status = entity.evaluate(resolve)
        targets = ", ".join(sorted(entity.targets))
        message = f"{entity.constraint_kind} on {targets}"
        if status is CheckStatus.FAIL:
            # Name the copper that failed, not only the net it belongs to.
            realized = [
                id for target in entity.targets
                for id in _realizations(snapshot.entities, target)
            ]
            if realized:
                message += f"; realized by {', '.join(sorted(set(realized)))}"
        results.append(
            CheckResult(
                entity.constraint_class.value,
                status,
                entity.id,
                message=message,
                severity=_SEVERITY[entity.enforcement],
                missing=_gaps(entity, snapshot.entities)
                if status is CheckStatus.UNKNOWN
                else (),
            )
        )
    return results


def routing_scope(snapshot) -> set[str]:
    """The entities a layout constraint targets, plus what realizes them.

    A transaction that adds a trace touches the scope of the rule about its net,
    so the gate requires this check exactly when it should.
    """
    scope: set[str] = set()
    for entity in snapshot.entities.values():
        if not is_layout_constraint(entity):
            continue
        scope.add(entity.id)
        scope |= set(entity.targets)
        for target in entity.targets:
            scope |= set(_realizations(snapshot.entities, target))
    return scope


#: Routing, placement, and manufacturing intent, evaluated against the physical
#: layer through the one constraint evaluator.
ROUTING_CHECK = CheckClass("routing", routing_check, routing_scope)


# --------------------------------------------------------------------------
# Projections to a layout tool
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class NetClass:
    """A group of nets that exactly the same layout rules apply to.

    The grouping *is* the rules: two nets share a class when the set of
    constraints targeting them is the same set. So a net belongs to exactly one
    class by construction rather than by a policy someone has to enforce, and
    the class is a projection of the registry like the rules themselves — it
    records nothing an engineer could not read off the constraints it names.
    """

    name: str
    #: The constraint identifiers this class was grouped from: its origin.
    projects: tuple[str, ...] = ()
    #: The net entities in the class, and the names a layout tool knows them by,
    #: in the same order.
    nets: tuple[str, ...] = ()
    net_names: tuple[str, ...] = ()

    def as_dict(self) -> dict:
        return {
            "name": self.name,
            "projects": list(self.projects),
            "nets": list(self.nets),
            "net_names": list(self.net_names),
        }


def _class_name(constraints: Sequence[Constraint]) -> str:
    """A deterministic name for the class a set of constraints defines.

    Two halves, and both earn their place. The kinds make the name readable in
    the layout tool, where a person reads it; the digest over the identifiers
    makes it unique and keeps it stable when an unrelated rule is added
    elsewhere, so a regenerated file diffs to nothing.
    """
    kinds = "_".join(sorted({c.constraint_kind for c in constraints}))
    readable = "".join(c if c.isalnum() or c == "_" else "_" for c in kinds)
    digest = sha256("\n".join(c.id for c in constraints).encode("utf-8")).hexdigest()
    return f"fang_{readable}_{digest[:6]}"


#: The physical attributes that belong to a net rather than to a part. A rule
#: reading one of these is a rule about a conductor, which is what a layout tool
#: groups into net classes; a placement rule reading a position is not.
NET_ATTRIBUTES: frozenset[str] = frozenset(
    {"trace_width", "trace_length", "clearance", "via_drill", "via_diameter"}
)


def _net_name(entity) -> str:
    """The name the layout tool knows a conductor by.

    The same rule the netlist uses: a name a source gave the net survives. An
    authored design has no net entities — the conductor is the port the program
    named — so that name is used, and only something nobody named at all falls
    back to its identifier.
    """
    if isinstance(entity, Net) and entity.aliases:
        return sorted(entity.aliases)[0]
    return entity.identity.display_name or entity.id


def _net_scoped(constraint: Constraint) -> frozenset[str]:
    """The targets a constraint reads a net-scoped attribute of."""
    return frozenset(
        node.ref
        for node in _refs(constraint.expression)
        if node.attr.startswith(PHYSICAL_PREFIX)
        and node.attr[len(PHYSICAL_PREFIX):] in NET_ATTRIBUTES
    )


def _refs(node):
    """Every `Ref` in an expression tree."""
    if isinstance(node, Ref):
        yield node
        return
    for argument in getattr(node, "args", ()):
        yield from _refs(argument)


def net_classes(snapshot) -> list[NetClass]:
    """The net classes a snapshot's layout constraints imply, sorted by name.

    A conductor no layout constraint targets is in no class: the kernel states
    intent it was given and invents none, and a tool's own default covers the
    rest.
    """
    entities = snapshot.entities
    targeting: dict[str, list[Constraint]] = {}
    for entity in sorted(entities.values(), key=lambda e: e.id):
        if not is_layout_constraint(entity):
            continue
        scoped = _net_scoped(entity)
        for target in entity.targets:
            if target in scoped and target in entities:
                targeting.setdefault(target, []).append(entity)

    grouped: dict[tuple[str, ...], list[str]] = {}
    for net_id, constraints in targeting.items():
        grouped.setdefault(tuple(sorted(c.id for c in constraints)), []).append(net_id)

    classes = []
    for key, members in grouped.items():
        nets = tuple(sorted(members))
        classes.append(
            NetClass(
                _class_name([entities[id] for id in key]),
                key,
                nets,
                tuple(_net_name(entities[id]) for id in nets),
            )
        )
    return sorted(classes, key=lambda c: c.name)


def rule_projections(snapshot, *, layer: str | None = None) -> list[Projection]:
    """One projection per layout constraint, sorted by identifier.

    A projection carries the identifier of the record it projects and adds only
    class-specific fields. It never restates a field the constraint already
    defines, because it is a pointer to the registry rather than a copy of it.

    The net classes are one such field. A constraint can name more than one,
    because two nets it targets may differ in what *else* applies to them.
    """
    classes = net_classes(snapshot)
    membership: dict[str, list[str]] = {}
    for net_class in classes:
        for constraint_id in net_class.projects:
            membership.setdefault(constraint_id, []).append(net_class.name)

    projections = []
    for entity in sorted(
        (e for e in snapshot.entities.values() if is_layout_constraint(e)),
        key=lambda e: e.id,
    ):
        fields: dict[str, object] = {}
        if layer is not None:
            fields["layer"] = layer
        names = membership.get(entity.id)
        if names:
            fields["net_classes"] = sorted(names)
        projections.append(Projection(entity, fields))
    return projections


def unresolved_references(snapshot) -> list[Diagnostic]:
    """Report every physical reference that resolves to no realization.

    An undecided rule is not a defect — copper that does not exist yet is the
    ordinary state of a design mid-flight. It is worth *saying*, though, because
    the alternative reading of an undecided result is that it passed.
    """
    findings = []
    for entity in sorted(snapshot.entities.values(), key=lambda e: e.id):
        if not is_layout_constraint(entity):
            continue
        for target in _gaps(entity, snapshot.entities):
            findings.append(
                Diagnostic(
                    TOPO_UNRESOLVED_PHYSICAL_REFERENCE,
                    Severity.INFO,
                    f"{entity.constraint_kind} on {target} is undecided: "
                    "nothing physical realizes it yet",
                    entities=(entity.id, target),
                    location=entity.source_location,
                )
            )
    return findings
