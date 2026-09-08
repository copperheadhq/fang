"""Provenance: an append-only record of where an engineering fact came from.

Spec: "Provenance On Every Derived Or Imported Entity". A record is immutable
once written: a later transformation appends and never rewrites or removes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Iterable, Sequence

from .diagnostics import SourceLocation


class ProvenanceOrigin(Enum):
    GENERATED = "generated"
    AUTHORED = "authored"
    IMPORTED = "imported"
    INFERRED = "inferred"


class ActorKind(Enum):
    TOOL = "tool"
    MODEL = "model"
    HUMAN = "human"
    ADAPTER = "adapter"


class Confidence(Enum):
    ASSERTED = "asserted"
    INFERRED = "inferred"
    UNVERIFIED = "unverified"


@dataclass(frozen=True)
class Actor:
    kind: ActorKind
    id: str
    version: str | None = None

    def as_dict(self) -> dict:
        out = {"kind": self.kind.value, "id": self.id}
        if self.version is not None:
            out["version"] = self.version
        return out


@dataclass(frozen=True)
class Input:
    """A declared, hashed input. Anything a program consumed is one of these."""

    id: str
    hash: str

    def as_dict(self) -> dict:
        return {"id": self.id, "hash": self.hash}


@dataclass(frozen=True)
class ProvenanceRecord:
    """One immutable provenance record."""

    origin: ProvenanceOrigin
    activity: str
    actor: Actor
    revision_id: str
    created_at: datetime
    derived_from: tuple[str, ...] = ()
    inputs: tuple[Input, ...] = ()
    source_location: SourceLocation | None = None
    confidence: Confidence | None = None

    def __post_init__(self) -> None:
        if self.origin is ProvenanceOrigin.INFERRED and self.confidence is None:
            raise ValueError(
                "an inferred provenance record carries a confidence; an "
                "inference is never recorded as an asserted fact"
            )

    def as_dict(self) -> dict:
        out: dict = {
            "origin": self.origin.value,
            "activity": self.activity,
            "actor": self.actor.as_dict(),
            "revision_id": self.revision_id,
            "created_at": self.created_at,
        }
        if self.derived_from:
            out["derived_from"] = sorted(self.derived_from)
        if self.inputs:
            out["inputs"] = [i.as_dict() for i in self.inputs]
        if self.source_location is not None:
            out["source_location"] = self.source_location.as_dict()
        if self.confidence is not None:
            out["confidence"] = self.confidence.value
        return out


class Provenance:
    """An append-only list of records, ordered oldest first."""

    __slots__ = ("_records",)

    def __init__(self, records: Iterable[ProvenanceRecord] = ()) -> None:
        self._records: tuple[ProvenanceRecord, ...] = tuple(records)

    def append(self, record: ProvenanceRecord) -> "Provenance":
        """Return a new chain with the record appended. Nothing is rewritten."""
        return Provenance(self._records + (record,))

    @property
    def records(self) -> tuple[ProvenanceRecord, ...]:
        return self._records

    @property
    def empty(self) -> bool:
        return not self._records

    @property
    def traceable(self) -> bool:
        """Whether the entity traces to a source location or to an import.

        An entity traceable to neither is a defect, which validation reports.
        """
        return any(
            record.source_location is not None
            or record.origin is ProvenanceOrigin.IMPORTED
            for record in self._records
        )

    def __len__(self) -> int:
        return len(self._records)

    def __iter__(self):
        return iter(self._records)

    def as_list(self) -> list[dict]:
        return [record.as_dict() for record in self._records]
