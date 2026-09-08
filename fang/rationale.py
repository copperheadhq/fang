"""Engineering rationale declared from a Fang program.

Spec: "Rationale Authored From The Program", "Calculations Are First-Class",
"Verification Results Form A Graph", and "Impact Propagation".

Requirements, decisions, evidence, and calculations are recorded where the
engineering happens rather than in a document beside it. A claim asserted
without a citation is an assumption, and is recorded as one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from .diagnostics import SourceLocation
from .entities import Entity, RequirementState
from .lang import Declared, _caller_location


class RationaleDeclaration(Declared):
    """The base of everything a program declares about its own reasoning."""

    _declaration_kind = "rationale"
    entity_kind = "requirement"

    def __init__(self) -> None:
        self.owner = None
        self.attribute = ""


@dataclass(init=False)
class Requires(RationaleDeclaration):
    """A requirement the design must meet."""

    entity_kind = "requirement"

    def __init__(
        self,
        statement: str,
        *,
        state: RequirementState = RequirementState.KNOWN,
        priority: str = "MUST",
        source: str = "user",
        validation: str | None = None,
    ) -> None:
        super().__init__()
        self.statement = statement
        self.state = state
        self.priority = priority
        self.source = source
        self.validation = validation


@dataclass(init=False)
class Assumes(RationaleDeclaration):
    """A working claim with no evidence behind it."""

    entity_kind = "assumption"

    def __init__(self, claim: str, *, rationale: str = "") -> None:
        super().__init__()
        self.claim = claim
        self.rationale = rationale or "stated without a citation"


@dataclass(init=False)
class Cites(RationaleDeclaration):
    """A claim with a document and a location within it behind it."""

    entity_kind = "evidence"

    def __init__(self, claim: str, *, document: str, locator: str = "") -> None:
        super().__init__()
        self.claim = claim
        self.document = document
        self.locator = locator


@dataclass(init=False)
class Chooses(RationaleDeclaration):
    """A decision, its alternatives, and what it rests on."""

    entity_kind = "decision"

    def __init__(
        self,
        question: str,
        *,
        selected: str,
        alternatives: Sequence[Mapping[str, str]] = (),
        requirements: Sequence[str] = (),
        evidence: Sequence[str] = (),
        rationale: Sequence[str] = (),
    ) -> None:
        super().__init__()
        self.question = question
        self.selected = selected
        self.alternatives = tuple(dict(a) for a in alternatives)
        self.requirements = tuple(requirements)
        self.evidence = tuple(evidence)
        self.rationale = tuple(rationale)


@dataclass(init=False)
class Calculates(RationaleDeclaration):
    """A computed result, with the inputs it depends on."""

    entity_kind = "calculation"

    def __init__(
        self,
        expression: str,
        *,
        inputs: Sequence[str] = (),
        result: str | None = None,
        requirements: Sequence[str] = (),
    ) -> None:
        super().__init__()
        self.expression = expression
        self.inputs = tuple(inputs)
        self.result = result
        self.requirements = tuple(requirements)


@dataclass(init=False)
class Verifies(RationaleDeclaration):
    """A verification: what it covers, how, and on what evidence."""

    entity_kind = "verification"

    def __init__(
        self,
        verifies: str,
        *,
        method: str = "analysis",
        evidence: Sequence[str] = (),
        result: str = "UNKNOWN",
    ) -> None:
        super().__init__()
        self.verifies = verifies
        self.method = method
        self.evidence = tuple(evidence)
        self.result = result


# --------------------------------------------------------------------------
# Coverage
# --------------------------------------------------------------------------


def coverage(snapshot) -> dict:
    """Which requirements are verified, and which are not.

    Answered from graph structure alone: a verification names what it verifies,
    so coverage is a join and never an inference.
    """
    from .entities import Requirement, Verification

    entities = snapshot.entities if hasattr(snapshot, "entities") else snapshot
    requirements = {
        e.id: e for e in entities.values() if isinstance(e, Requirement)
    }
    verified: dict[str, list[str]] = {}
    for entity in entities.values():
        if isinstance(entity, Verification) and entity.verifies in requirements:
            verified.setdefault(entity.verifies, []).append(entity.id)

    return {
        "total": len(requirements),
        "covered": sorted(verified),
        "uncovered": sorted(set(requirements) - set(verified)),
        "verifications": {k: sorted(v) for k, v in sorted(verified.items())},
    }


def impacted_by(snapshot, changed: Sequence[str]) -> dict[str, list[str]]:
    """What a change puts at risk.

    Walks from the changed entities to the calculations, requirements, and
    verifications that depend on them, one edge at a time, so the answer is the
    recorded structure rather than a guess.
    """
    from .constraints import Constraint
    from .entities import Calculation, Requirement, Verification

    entities = snapshot.entities if hasattr(snapshot, "entities") else snapshot
    changed_set = set(changed)

    calculations: set[str] = set()
    requirements: set[str] = set()
    verifications: set[str] = set()

    for entity in entities.values():
        references = set(entity.references())
        if not (references & changed_set) and entity.id not in changed_set:
            continue
        if isinstance(entity, Calculation):
            calculations.add(entity.id)
            requirements.update(entity.requirements)
        elif isinstance(entity, Constraint) and entity.source:
            requirements.add(entity.source)
        elif isinstance(entity, Verification):
            verifications.add(entity.id)
            requirements.add(entity.verifies)

    # A requirement whose verification is at risk is itself at risk.
    for entity in entities.values():
        if isinstance(entity, Verification) and (
            entity.id in verifications or set(entity.references()) & changed_set
        ):
            verifications.add(entity.id)
            requirements.add(entity.verifies)

    return {
        "calculations": sorted(calculations),
        "requirements": sorted(r for r in requirements if r in entities),
        "verifications": sorted(verifications),
    }
