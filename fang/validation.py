"""Structural validation and the requirement state machine.

Spec: "Structural Validation", "Requirement State Transitions", and "Schema
Versioning and Compatibility".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from . import SCHEMA_VERSION
from .constraints import Constraint, Enforcement
from .diagnostics import (
    ELAB_DANGLING_REFERENCE,
    ELAB_DUPLICATE_ID,
    ELAB_CONTRADICTORY_CONSTRAINTS,
    ELAB_INVALID_STATE_TRANSITION,
    ELAB_NO_PROVENANCE,
    ELAB_PROHIBITED_CYCLE,
    ELAB_SCHEMA_MAJOR_UNSUPPORTED,
    Diagnostic,
    Severity,
    error,
)
from .entities import Entity, Requirement, RequirementState, TRANSITIONS
from .identity import Origin


@dataclass(frozen=True)
class StateTransition:
    """One requirement state change, with what the target state demands."""

    requirement: str
    from_state: RequirementState
    to_state: RequirementState
    actor: str
    reason: str
    evidence: str | None = None   # required for VERIFIED
    waiver: str | None = None     # required for WAIVED
    approval: str | None = None   # required for ASSUMED -> KNOWN


def check_transition(transition: StateTransition) -> list[Diagnostic]:
    """Validate one state transition against the permitted table."""
    problems: list[Diagnostic] = []
    permitted = TRANSITIONS[transition.from_state]

    if transition.to_state not in permitted:
        problems.append(
            Diagnostic(
                ELAB_INVALID_STATE_TRANSITION,
                Severity.ERROR,
                f"{transition.from_state.value} to {transition.to_state.value} is "
                "not a permitted requirement state transition",
                (transition.requirement,),
            )
        )

    if not transition.actor or not transition.reason:
        problems.append(
            Diagnostic(
                ELAB_INVALID_STATE_TRANSITION,
                Severity.ERROR,
                "every transition records its actor and its reason",
                (transition.requirement,),
            )
        )

    if transition.to_state is RequirementState.VERIFIED and not transition.evidence:
        problems.append(
            Diagnostic(
                ELAB_INVALID_STATE_TRANSITION,
                Severity.ERROR,
                "a transition to VERIFIED cites verification evidence",
                (transition.requirement,),
            )
        )
    if transition.to_state is RequirementState.WAIVED and not transition.waiver:
        problems.append(
            Diagnostic(
                ELAB_INVALID_STATE_TRANSITION,
                Severity.ERROR,
                "a transition to WAIVED cites a waiver",
                (transition.requirement,),
            )
        )
    if (
        transition.from_state is RequirementState.ASSUMED
        and transition.to_state is RequirementState.KNOWN
        and not (transition.approval or transition.evidence)
    ):
        problems.append(
            Diagnostic(
                ELAB_INVALID_STATE_TRANSITION,
                Severity.ERROR,
                "a transition out of ASSUMED to KNOWN cites the approval or "
                "evidence that promoted it",
                (transition.requirement,),
            )
        )

    return problems


class ValidationReport:
    """What structural validation found."""

    def __init__(self, diagnostics: Iterable[Diagnostic] = ()) -> None:
        self.diagnostics = list(diagnostics)

    @property
    def ok(self) -> bool:
        return not any(d.severity.blocking for d in self.diagnostics)

    @property
    def blocking(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity.blocking]

    def extend(self, diagnostics: Iterable[Diagnostic]) -> None:
        self.diagnostics.extend(diagnostics)

    def as_list(self) -> list[dict]:
        return [d.as_dict() for d in self.diagnostics]

    def __len__(self) -> int:
        return len(self.diagnostics)

    def __repr__(self) -> str:
        return f"<ValidationReport ok={self.ok} diagnostics={len(self.diagnostics)}>"


def check_schema_version(declared: str, implemented: str = SCHEMA_VERSION) -> None:
    """Reject an artifact whose major schema version is not implemented.

    A reader never silently downgrades one.
    """
    declared_major = declared.split(".", 1)[0]
    implemented_major = implemented.split(".", 1)[0]
    if declared_major != implemented_major:
        raise error(
            ELAB_SCHEMA_MAJOR_UNSUPPORTED,
            f"artifact declares schema version {declared}; this implementation "
            f"implements major version {implemented_major} and does not "
            "downgrade an artifact it cannot read",
        )


def validate(
    entities: Mapping[str, Entity],
    *,
    containment: Mapping[str, Sequence[str]] | None = None,
) -> ValidationReport:
    """Validate a set of entities.

    Checks identifier uniqueness, referential integrity, provenance
    traceability, prohibited cycles, and contradictory mandatory constraints.
    Type and unit correctness is enforced at construction by `units` and
    `constraints`, so an invalid expression cannot reach here.
    """
    report = ValidationReport()

    # Identifier uniqueness, across every origin.
    seen: dict[str, str] = {}
    for key, entity in entities.items():
        if entity.id in seen and seen[entity.id] != key:
            report.extend(
                [
                    Diagnostic(
                        ELAB_DUPLICATE_ID,
                        Severity.ERROR,
                        f"identifier {entity.id} is used by more than one entity",
                        (entity.id,),
                    )
                ]
            )
        seen[entity.id] = key

    # Referential integrity.
    for entity in entities.values():
        for reference in entity.references():
            if reference and reference not in entities:
                report.extend(
                    [
                        Diagnostic(
                            ELAB_DANGLING_REFERENCE,
                            Severity.ERROR,
                            f"{entity.id} references {reference}, which does not "
                            "exist in this revision",
                            (entity.id, reference),
                        )
                    ]
                )

    # Provenance: every derived or imported entity carries it, and every entity
    # traces to a source location or to an import.
    for entity in entities.values():
        origin = entity.identity.origin
        if origin in (Origin.DERIVED, Origin.IMPORTED) and entity.provenance.empty:
            report.extend(
                [
                    Diagnostic(
                        ELAB_NO_PROVENANCE,
                        Severity.ERROR,
                        f"{entity.id} is {origin.value} and carries no provenance",
                        (entity.id,),
                    )
                ]
            )
        traceable = (
            entity.source_location is not None
            or entity.provenance.traceable
            or origin is Origin.AUTHORED
        )
        if not traceable:
            report.extend(
                [
                    Diagnostic(
                        ELAB_NO_PROVENANCE,
                        Severity.ERROR,
                        f"{entity.id} traces to neither a source location nor an "
                        "import",
                        (entity.id,),
                    )
                ]
            )

    if containment:
        report.extend(_check_cycles(containment))

    report.extend(_check_contradictions(entities))
    return report


def _check_cycles(containment: Mapping[str, Sequence[str]]) -> list[Diagnostic]:
    """Report cycles in a relation where one is prohibited, such as containment."""
    problems: list[Diagnostic] = []
    WHITE, GREY, BLACK = 0, 1, 2
    colour: dict[str, int] = {node: WHITE for node in containment}

    def visit(node: str, trail: list[str]) -> None:
        colour[node] = GREY
        for child in containment.get(node, ()):
            state = colour.get(child, WHITE)
            if state is GREY:
                cycle = trail[trail.index(child):] + [child] if child in trail else [node, child]
                problems.append(
                    Diagnostic(
                        ELAB_PROHIBITED_CYCLE,
                        Severity.ERROR,
                        "containment cycle: " + " -> ".join(cycle),
                        tuple(cycle),
                    )
                )
            elif state is WHITE:
                visit(child, trail + [child])
        colour[node] = BLACK

    for node in sorted(containment):
        if colour.get(node, WHITE) is WHITE:
            visit(node, [node])
    return problems


def _check_contradictions(entities: Mapping[str, Entity]) -> list[Diagnostic]:
    """Report mandatory constraints that cannot both hold.

    Detects the tractable case: two hard constraints of the same kind bounding
    the *same* quantity, whose satisfiable intervals do not intersect. Two
    constraints on one target that bound different parameters say nothing about
    each other, so the grouping is keyed by the parameter they reference and not
    by the target alone.
    """
    problems: list[Diagnostic] = []
    grouped: dict[tuple[str, str, str, str], list[tuple[Constraint, tuple]]] = {}
    for entity in entities.values():
        if not isinstance(entity, Constraint) or entity.enforcement is not Enforcement.HARD:
            continue
        bounded = _satisfiable_bound(entity)
        if bounded is None:
            continue
        reference, bound = bounded
        for target in entity.targets:
            key = (target, entity.constraint_kind, reference[0], reference[1])
            grouped.setdefault(key, []).append((entity, bound))

    for (target, kind, _, attribute), bounded in sorted(grouped.items()):
        if len(bounded) < 2:
            continue
        low = max(bound[0] for _, bound in bounded)
        high = min(bound[1] for _, bound in bounded)
        if low > high:
            ids = tuple(sorted(c.id for c, _ in bounded))
            problems.append(
                Diagnostic(
                    ELAB_CONTRADICTORY_CONSTRAINTS,
                    Severity.ERROR,
                    f"hard constraints {', '.join(ids)} on {target}.{attribute} "
                    f"({kind}) cannot both be satisfied",
                    ids,
                )
            )
    return problems


def _satisfiable_bound(constraint: Constraint):
    """A simple ``ref <op> literal`` constraint as the quantity it bounds.

    Returns the referenced ``(entity, attribute)`` together with the interval the
    comparison permits, or None when the expression is not of that shape.
    """
    from decimal import Decimal

    from .constraints import Comparison, Literal, Ref

    expression = constraint.expression
    if not isinstance(expression, Comparison):
        return None
    left, right = expression.args
    if not (isinstance(left, Ref) and isinstance(right, Literal)):
        return None
    if right.quantity is None:
        return None
    low, high = right.quantity.interval()
    infinity = Decimal("1E999")
    reference = (left.ref, left.attr)
    if expression.op in ("le", "lt"):
        return (reference, (-infinity, high))
    if expression.op in ("ge", "gt"):
        return (reference, (low, infinity))
    if expression.op == "eq":
        return (reference, (low, high))
    return None
