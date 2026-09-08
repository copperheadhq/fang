"""Value records: how well a value is known travels with the value.

Spec: "Value Status and Explicit Unknowns" and "Conflicting Values Are Preserved
Until Resolved". Unknown is explicitly representable and a null never means it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Sequence

from .units import Quantity, _decimal_str


class ValueStatus(Enum):
    """How well a value is known."""

    EXPLICIT = "explicit"   # stated by a requirement, a datasheet, or a person
    INFERRED = "inferred"   # computed or extracted; carries source and confidence
    ASSUMED = "assumed"     # a working value with no evidence; carries rationale
    UNKNOWN = "unknown"     # not known; the quantity is absent


@dataclass(frozen=True)
class Value:
    """One parameter value.

    A parameter is a value record rather than a bare quantity. A consumer must
    not treat an inferred or an assumed value as an explicit one, so the status
    is not optional and has no default.
    """

    status: ValueStatus
    quantity: Quantity | None = None
    source: str | None = None
    confidence: Decimal | None = None
    rationale: str | None = None

    def __post_init__(self) -> None:
        if self.status is ValueStatus.UNKNOWN:
            if self.quantity is not None:
                raise ValueError(
                    "an unknown value carries no quantity; "
                    "a value that does not apply is absent instead"
                )
            return

        if self.quantity is None:
            raise ValueError(
                f"a {self.status.value} value carries a quantity; "
                "use ValueStatus.UNKNOWN to say it is not known"
            )

        if self.status is ValueStatus.INFERRED:
            if self.source is None or self.confidence is None:
                raise ValueError(
                    "an inferred value carries its source and a confidence"
                )
        if self.status is ValueStatus.ASSUMED and not self.rationale:
            raise ValueError("an assumed value carries its rationale")

    # -- constructors ------------------------------------------------------

    @classmethod
    def explicit(cls, quantity: Quantity, source: str | None = None) -> "Value":
        return cls(ValueStatus.EXPLICIT, quantity, source=source)

    @classmethod
    def inferred(cls, quantity: Quantity, source: str, confidence: str | Decimal) -> "Value":
        return cls(
            ValueStatus.INFERRED,
            quantity,
            source=source,
            confidence=Decimal(str(confidence)),
        )

    @classmethod
    def assumed(cls, quantity: Quantity, rationale: str) -> "Value":
        return cls(ValueStatus.ASSUMED, quantity, rationale=rationale)

    @classmethod
    def unknown(cls) -> "Value":
        return cls(ValueStatus.UNKNOWN)

    # -- semantics ---------------------------------------------------------

    @property
    def known(self) -> bool:
        """Whether a quantity is present at all. Evaluation over an unknown
        yields undecided rather than a pass or a failure."""
        return self.status is not ValueStatus.UNKNOWN

    @property
    def is_explicit(self) -> bool:
        """An inferred or assumed value is never treated as an explicit one."""
        return self.status is ValueStatus.EXPLICIT

    def as_dict(self) -> dict:
        out: dict = {"status": self.status.value}
        if self.quantity is not None:
            out["quantity"] = self.quantity.as_dict()
        if self.source is not None:
            out["source"] = self.source
        if self.confidence is not None:
            out["confidence"] = _decimal_str(self.confidence)
        if self.rationale is not None:
            out["rationale"] = self.rationale
        return out

    def __str__(self) -> str:
        if self.status is ValueStatus.UNKNOWN:
            return "unknown"
        return f"{self.quantity} ({self.status.value})"


@dataclass(frozen=True)
class Candidate:
    """One competing value for a parameter, with the source that supplied it."""

    value: Value
    source: str

    def as_dict(self) -> dict:
        return {"value": self.value.as_dict(), "source": self.source}


@dataclass(frozen=True)
class ConflictingValue:
    """A parameter with competing candidates.

    Conflicting evidence remains preservable until resolved: every candidate and
    its source are retained, and the conflict is never silently reduced to one
    winner. A resolution names the chosen candidate and the decision that chose
    it.
    """

    candidates: tuple[Candidate, ...]
    resolution: str | None = None       # the id of the chosen candidate's source
    decision: str | None = None         # the decision entity that resolved it

    def __post_init__(self) -> None:
        if len(self.candidates) < 2:
            raise ValueError("a conflict has at least two candidates")
        if (self.resolution is None) != (self.decision is None):
            raise ValueError(
                "a resolution records both the chosen candidate and the decision "
                "that chose it"
            )
        if self.resolution is not None:
            sources = {candidate.source for candidate in self.candidates}
            if self.resolution not in sources:
                raise ValueError(
                    f"the resolution names {self.resolution!r}, which is not one "
                    "of the candidates"
                )

    @property
    def resolved(self) -> bool:
        return self.resolution is not None

    def resolve(self, source: str, decision: str) -> "ConflictingValue":
        """Choose a candidate, recording the design decision that chose it."""
        return ConflictingValue(self.candidates, source, decision)

    @property
    def chosen(self) -> Value | None:
        if not self.resolved:
            return None
        return next(c.value for c in self.candidates if c.source == self.resolution)

    def as_dict(self) -> dict:
        out: dict = {
            "candidates": [
                candidate.as_dict()
                for candidate in sorted(self.candidates, key=lambda c: c.source)
            ]
        }
        if self.resolution is not None:
            out["resolution"] = self.resolution
            out["decision"] = self.decision
        return out


#: A parameter holds either one value or an unresolved set of candidates.
Parameter = Value | ConflictingValue
