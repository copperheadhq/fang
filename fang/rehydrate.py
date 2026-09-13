"""Rehydration: a persisted record stream becomes typed entities again.

Spec: "A Persisted Snapshot Reloads Without Running A Program".

There is one registry, keyed by entity kind here and by trait protocol in
`fang.traits`. Each decoder inverts its own type's `as_dict` and sits beside it;
this module dispatches to them, keeps what they cannot type, and refuses what
cannot be read. A record comes out one of three ways, never a fourth:

- decoded, as a typed entity that reserializes to the bytes it was read from;
- untyped, kept verbatim as an `OpaqueEntity` and named in the load report;
- malformed, which refuses the whole load with ELAB-0013.

A trait the registry cannot type stays on its typed entity as an `OpaqueTrait`,
and is named in the load report too.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

from .constraints import Constraint
from .diagnostics import ELAB_DUPLICATE_ID, ELAB_MALFORMED_RECORD, FangError, error
from .entities import (
    Assumption,
    Bus,
    Calculation,
    Component,
    Connection,
    Decision,
    Domain,
    Entity,
    Evidence,
    Interface,
    Model,
    Net,
    Pin,
    Port,
    Rail,
    Requirement,
    Verification,
)
from .identity import Identity, Origin
from .provenance import Provenance
from .records import MalformedRecord, UnmodelledKeys
from .serialization import canonical_dumps
from .topology import TopologyConstraint

# Trait registration lives beside the trait classes; it is re-exported here so
# that one module names both halves of the registry.
from .traits import OpaqueTrait, register_trait, trait_decoders

#: An entity decoder turns a record back into the entity it serializes.
EntityDecoder = Callable[[Mapping[str, Any]], Entity]

_DECODERS: dict[str, EntityDecoder] = {}


def register_entity(kind: str, decoder: EntityDecoder) -> None:
    """Register the decoder for a kind, so records of that kind read back typed.

    A kind with more than one class dispatches inside its decoder, as
    `constraint` does.
    """
    if not kind:
        raise ValueError("an entity decoder is registered for a kind")
    _DECODERS[kind] = decoder


def entity_decoders() -> dict[str, EntityDecoder]:
    return dict(_DECODERS)


@dataclass(frozen=True)
class OpaqueEntity(Entity):
    """A record no decoder could type, kept exactly as it was read.

    It carries the record's id, so a snapshot can hold it and a diff can name
    it, and no references, because what it refers to is not known here. It
    serializes back to the record it was read from, so the hash is unchanged.
    """

    kind: str = ""
    record: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return deepcopy(dict(self.record))


@dataclass(frozen=True)
class Untyped:
    """One record, or one trait inside a record, that loaded untyped, and why."""

    subject: str
    construct: str
    reason: str

    def as_dict(self) -> dict:
        return {"subject": self.subject, "construct": self.construct, "reason": self.reason}


@dataclass(frozen=True)
class LoadReport:
    """How many records a load typed, and what it kept verbatim instead."""

    decoded: int = 0
    untyped: tuple[Untyped, ...] = ()

    @property
    def complete(self) -> bool:
        """Whether every record and every trait came back typed."""
        return not self.untyped

    def as_dict(self) -> dict:
        return {"decoded": self.decoded, "untyped": [item.as_dict() for item in self.untyped]}


def _malformed(subject: str | None, field: str, detail: str) -> FangError:
    named = f"record {subject}" if subject else "a record"
    return error(
        ELAB_MALFORMED_RECORD,
        f"{named} cannot be decoded: {field}: {detail}; nothing was loaded",
        entities=[subject] if subject else [],
    )


def _opaque(record: Mapping[str, Any], subject: str, kind: str) -> OpaqueEntity:
    """Keep a record verbatim, with whatever identity and provenance it yields."""
    try:
        identity = Identity.from_dict(record["identity"])
    except (FangError, LookupError, TypeError, ValueError):
        identity = None
    if identity is None or identity.id != subject:
        identity = Identity(subject, Origin.AUTHORED)
    try:
        provenance = Provenance.from_list(record.get("provenance", []))
    except (LookupError, TypeError, ValueError):
        provenance = Provenance()
    return OpaqueEntity(
        identity=identity, kind=kind, provenance=provenance, record=deepcopy(dict(record))
    )


def decode_record(record: Any) -> tuple[Entity, tuple[Untyped, ...]]:
    """Decode one record through the registry.

    Returns the entity and whatever in it loaded untyped. Raises ELAB-0013 for a
    record that cannot be read at all.
    """
    if not isinstance(record, Mapping):
        raise _malformed(None, "record", f"expected an object, found {type(record).__name__}")
    subject = record.get("id")
    if not isinstance(subject, str) or not subject:
        raise _malformed(None, "id", "a record carries its id as a non-empty string")
    kind = record.get("kind")
    if not isinstance(kind, str) or not kind:
        raise _malformed(subject, "kind", "a record carries its kind as a non-empty string")

    decoder = _DECODERS.get(kind)
    if decoder is None:
        return _opaque(record, subject, kind), (
            Untyped(subject, f"kind {kind}", "no decoder is registered for this kind"),
        )
    try:
        entity = decoder(record)
    except UnmodelledKeys as unmodelled:
        return _opaque(record, subject, kind), (Untyped(subject, f"kind {kind}", str(unmodelled)),)
    except MalformedRecord as failure:
        raise _malformed(subject, failure.field, failure.detail) from None
    except FangError as failure:
        raise _malformed(subject, kind, failure.diagnostic.message) from None
    except (LookupError, TypeError, ValueError, ArithmeticError) as failure:
        raise _malformed(subject, kind, str(failure)) from None

    # A decoder that does not reproduce its record would move the hash. Keeping
    # the record verbatim instead is lossless, and the report says so.
    if canonical_dumps(entity.as_dict()) != canonical_dumps(record):
        return _opaque(record, subject, kind), (
            Untyped(
                subject,
                f"kind {kind}",
                "the decoded entity does not reserialize to the record it was read from",
            ),
        )

    decoders = trait_decoders()
    untyped = tuple(
        Untyped(
            subject,
            f"trait {protocol}",
            "the trait carries a key its decoder does not model"
            if protocol in decoders
            else "no decoder is registered for this protocol",
        )
        for protocol, trait in sorted(entity.traits.items())
        if isinstance(trait, OpaqueTrait)
    )
    return entity, untyped


def decode_records(records: Iterable[Any]) -> tuple[dict[str, Entity], LoadReport]:
    """Decode a whole record stream, or refuse the whole of it."""
    entities: dict[str, Entity] = {}
    untyped: list[Untyped] = []
    decoded = 0
    for record in records:
        entity, missed = decode_record(record)
        if entity.id in entities:
            raise error(
                ELAB_DUPLICATE_ID,
                f"two records carry the id {entity.id}; nothing was loaded",
                entities=[entity.id],
            )
        entities[entity.id] = entity
        untyped.extend(missed)
        if not isinstance(entity, OpaqueEntity):
            decoded += 1
    return entities, LoadReport(decoded, tuple(untyped))


def _decode_constraint(record: Mapping[str, Any]) -> Constraint:
    """A constraint record, or a topology constraint when it carries a topology's fields."""
    if record.get("class") == "topology" and "mode" in record:
        return TopologyConstraint.from_dict(record)
    return Constraint.from_dict(record)


for _kind, _decoder in (
    ("block", Entity.from_dict),
    ("requirement", Requirement.from_dict),
    ("connection", Connection.from_dict),
    ("component", Component.from_dict),
    ("net", Net.from_dict),
    ("rail", Rail.from_dict),
    ("interface", Interface.from_dict),
    ("port", Port.from_dict),
    ("pin", Pin.from_dict),
    ("bus", Bus.from_dict),
    ("domain", Domain.from_dict),
    ("decision", Decision.from_dict),
    ("evidence", Evidence.from_dict),
    ("calculation", Calculation.from_dict),
    ("verification", Verification.from_dict),
    ("assumption", Assumption.from_dict),
    ("model", Model.from_dict),
    ("constraint", _decode_constraint),
):
    register_entity(_kind, _decoder)
