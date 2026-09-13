"""Provenance: an append-only record of where an engineering fact came from.

Spec: "Provenance On Every Derived Or Imported Entity". A record is immutable
once written: a later transformation appends and never rewrites or removes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from .diagnostics import SourceLocation
from .records import (
    MalformedRecord,
    expect_keys,
    listed,
    member,
    optional_text,
    required,
    text,
    texts,
)


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

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Actor":
        """The inverse of `as_dict`."""
        expect_keys(payload, ("kind", "id", "version"), "actor")
        return cls(
            member(ActorKind, required(payload, "kind", "actor.kind"), "actor.kind"),
            text(required(payload, "id", "actor.id"), "actor.id"),
            optional_text(payload, "version", "actor.version"),
        )


@dataclass(frozen=True)
class Input:
    """A declared, hashed input. Anything a program consumed is one of these."""

    id: str
    hash: str

    def as_dict(self) -> dict:
        return {"id": self.id, "hash": self.hash}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Input":
        """The inverse of `as_dict`."""
        expect_keys(payload, ("id", "hash"), "input")
        return cls(
            text(required(payload, "id", "input.id"), "input.id"),
            text(required(payload, "hash", "input.hash"), "input.hash"),
        )


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

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ProvenanceRecord":
        """The inverse of `as_dict`. The timestamp is parsed from its RFC3339 form."""
        from .serialization import parse_rfc3339

        expect_keys(
            payload,
            (
                "origin",
                "activity",
                "actor",
                "revision_id",
                "created_at",
                "derived_from",
                "inputs",
                "source_location",
                "confidence",
            ),
            "provenance record",
        )
        created_at = required(payload, "created_at", "provenance.created_at")
        if isinstance(created_at, datetime):
            moment = created_at
        else:
            try:
                moment = parse_rfc3339(created_at)
            except ValueError as failure:
                raise MalformedRecord("provenance.created_at", str(failure)) from None
        location = payload.get("source_location")
        confidence = payload.get("confidence")
        return cls(
            member(
                ProvenanceOrigin,
                required(payload, "origin", "provenance.origin"),
                "provenance.origin",
            ),
            text(required(payload, "activity", "provenance.activity"), "provenance.activity"),
            Actor.from_dict(required(payload, "actor", "provenance.actor")),
            text(
                required(payload, "revision_id", "provenance.revision_id"),
                "provenance.revision_id",
            ),
            moment,
            derived_from=texts(payload.get("derived_from", []), "provenance.derived_from"),
            inputs=tuple(
                Input.from_dict(item)
                for item in listed(payload.get("inputs", []), "provenance.inputs")
            ),
            source_location=SourceLocation.from_dict(location) if location is not None else None,
            confidence=(
                member(Confidence, confidence, "provenance.confidence")
                if confidence is not None
                else None
            ),
        )


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

    @classmethod
    def from_list(cls, payload: Sequence[Mapping[str, Any]]) -> "Provenance":
        """The inverse of `as_list`. Order is kept, because records run oldest first."""
        return cls(
            ProvenanceRecord.from_dict(record) for record in listed(payload, "provenance")
        )
