"""The layout constraint classes, and their projection to a layout tool.

Spec: "Routing And Placement Constraints Are Checked By The Gate" and "Emitted
Design Rules Are Projections".

There is one constraint registry and one evaluator. A check class here is a
selection over that registry and a scope over the entities it targets — it is
not a second rule engine, and an emitted rule file is not a second store.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from .constraints import (
    CheckStatus,
    Constraint,
    ConstraintClass,
    Enforcement,
    Projection,
)
from .diagnostics import Severity
from .graph import CheckClass, CheckResult
from .physical import PHYSICAL_PREFIX, PhysicalEntity

#: The classes this check class covers. The remainder stay with the structural
#: constraint check, so every class is covered exactly once.
LAYOUT_CLASSES: frozenset[ConstraintClass] = frozenset(
    {
        ConstraintClass.ROUTING,
        ConstraintClass.PLACEMENT,
        ConstraintClass.MANUFACTURING,
    }
)

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


def rule_projections(snapshot, *, layer: str | None = None) -> list[Projection]:
    """One projection per layout constraint, sorted by identifier.

    A projection carries the identifier of the record it projects and adds only
    class-specific fields. It never restates a field the constraint already
    defines, because it is a pointer to the registry rather than a copy of it.
    """
    projections = []
    for entity in sorted(
        (e for e in snapshot.entities.values() if is_layout_constraint(e)),
        key=lambda e: e.id,
    ):
        fields: dict[str, str] = {}
        if layer is not None:
            fields["layer"] = layer
        projections.append(Projection(entity, fields))
    return projections
