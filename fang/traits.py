"""Traits: behaviour attaches to entities without widening their classes.

Spec: "Traits As The Extension Mechanism", "Trait Registration And
Enumeration", and "A Persisted Snapshot Reloads Without Running A Program". A
trait declares the protocol it satisfies, and the kernel enumerates the entities
carrying a protocol without instantiating any backend. A trait is state: it
travels on the entity that carries it, serializes inside that entity's record,
and is read back with it.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

from .provenance import Provenance
from .records import (
    MalformedRecord,
    UnmodelledKeys,
    boolean,
    expect_keys,
    required,
    text,
    text_mapping,
    texts,
)


class Trait:
    """A capability attached to an entity.

    Subclasses declare ``protocol``. A trait is data plus a declared protocol; it
    never holds a live backend object, which is what lets the kernel enumerate
    traits without constructing a simulator, a layout engine, or a renderer.
    """

    protocol: str = ""

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.__dict__.get("protocol") and not cls.protocol:
            cls.protocol = cls.__name__.lower()

    def as_dict(self) -> dict:
        payload = {
            key: value
            for key, value in vars(self).items()
            if not key.startswith("_") and key != "provenance"
        }
        out: dict = {"protocol": self.protocol}
        out.update({k: _plain(v) for k, v in sorted(payload.items())})
        provenance = getattr(self, "provenance", None)
        if isinstance(provenance, Provenance) and not provenance.empty:
            out["provenance"] = provenance.as_list()
        return out


def _plain(value: Any):
    if hasattr(value, "as_dict"):
        return value.as_dict()
    if isinstance(value, Mapping):
        return {k: _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value


def _expect(payload: Any, cls: type[Trait], fields: Iterable[str]) -> Mapping[str, Any]:
    """Refuse a trait payload carrying a key its class does not write."""
    return expect_keys(payload, ("protocol", *fields), f"trait {cls.protocol}")


@dataclass
class Footprint(Trait):
    """Where a component lands physically."""

    protocol = "footprint"
    library: str = ""
    name: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Footprint":
        """The inverse of `as_dict`."""
        _expect(payload, cls, ("library", "name"))
        return cls(
            library=text(required(payload, "library", "footprint.library"), "footprint.library"),
            name=text(required(payload, "name", "footprint.name"), "footprint.name"),
        )


@dataclass
class Sourcing(Trait):
    """Where a component is bought."""

    protocol = "sourcing"
    manufacturer: str = ""
    mpn: str = ""
    distributor_ids: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Sourcing":
        """The inverse of `as_dict`."""
        _expect(payload, cls, ("manufacturer", "mpn", "distributor_ids"))
        return cls(
            manufacturer=text(
                required(payload, "manufacturer", "sourcing.manufacturer"),
                "sourcing.manufacturer",
            ),
            mpn=text(required(payload, "mpn", "sourcing.mpn"), "sourcing.mpn"),
            distributor_ids=text_mapping(
                required(payload, "distributor_ids", "sourcing.distributor_ids"),
                "sourcing.distributor_ids",
            ),
        )


@dataclass
class DatasheetEvidence(Trait):
    """The document a component's claims are cited from."""

    protocol = "datasheet_evidence"
    document: str = ""
    evidence_ids: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "DatasheetEvidence":
        """The inverse of `as_dict`."""
        _expect(payload, cls, ("document", "evidence_ids"))
        return cls(
            document=text(
                required(payload, "document", "datasheet_evidence.document"),
                "datasheet_evidence.document",
            ),
            evidence_ids=texts(
                required(payload, "evidence_ids", "datasheet_evidence.evidence_ids"),
                "datasheet_evidence.evidence_ids",
            ),
        )


@dataclass
class Simulatable(Trait):
    """A component carries a model. The model is data; the backend is not here."""

    protocol = "simulatable"
    model_kind: str = "spice_subckt"
    backends: tuple[str, ...] = ()
    source: str | None = None
    pin_map: Mapping[str, str] = field(default_factory=dict)
    conditions: Mapping[str, str] = field(default_factory=dict)
    distribution_restricted: bool = False
    provenance: Provenance = field(default_factory=Provenance)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Simulatable":
        """The inverse of `as_dict`, provenance included where it was written."""
        _expect(
            payload,
            cls,
            (
                "model_kind",
                "backends",
                "source",
                "pin_map",
                "conditions",
                "distribution_restricted",
                "provenance",
            ),
        )
        source = required(payload, "source", "simulatable.source")
        return cls(
            model_kind=text(
                required(payload, "model_kind", "simulatable.model_kind"),
                "simulatable.model_kind",
            ),
            backends=texts(
                required(payload, "backends", "simulatable.backends"), "simulatable.backends"
            ),
            source=text(source, "simulatable.source") if source is not None else None,
            pin_map=text_mapping(
                required(payload, "pin_map", "simulatable.pin_map"), "simulatable.pin_map"
            ),
            conditions=text_mapping(
                required(payload, "conditions", "simulatable.conditions"),
                "simulatable.conditions",
            ),
            distribution_restricted=boolean(
                required(
                    payload,
                    "distribution_restricted",
                    "simulatable.distribution_restricted",
                ),
                "simulatable.distribution_restricted",
            ),
            provenance=(
                Provenance.from_list(payload["provenance"])
                if "provenance" in payload
                else Provenance()
            ),
        )


@dataclass
class Renderable(Trait):
    """A hint for the view compiler. It carries no geometry and no meaning."""

    protocol = "renderable"
    symbol: str = ""

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Renderable":
        """The inverse of `as_dict`."""
        _expect(payload, cls, ("symbol",))
        return cls(symbol=text(required(payload, "symbol", "renderable.symbol"), "renderable.symbol"))


class OpaqueTrait(Trait):
    """A trait whose protocol has no registered decoder, kept exactly as read.

    It serializes back to the payload it was read from, so a trait a newer
    producer wrote survives a reader that cannot interpret it.
    """

    def __init__(self, protocol: str, payload: Mapping[str, Any]) -> None:
        self.protocol = protocol
        self._payload = deepcopy(dict(payload))

    def as_dict(self) -> dict:
        return deepcopy(self._payload)

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, OpaqueTrait)
            and other.protocol == self.protocol
            and other._payload == self._payload
        )

    __hash__ = None  # type: ignore[assignment]


#: A trait decoder turns a serialized payload back into the trait it describes.
TraitDecoder = Callable[[Mapping[str, Any]], Trait]

_DECODERS: dict[str, TraitDecoder] = {}


def register_trait(protocol: str, decoder: TraitDecoder) -> None:
    """Register the decoder for a protocol, so records carrying it read back typed."""
    if not protocol:
        raise ValueError("a trait decoder is registered for a protocol")
    _DECODERS[protocol] = decoder


def trait_decoders() -> dict[str, TraitDecoder]:
    return dict(_DECODERS)


def decode_trait(protocol: str, payload: Mapping[str, Any]) -> Trait:
    """Decode one trait.

    A protocol with no decoder, or a payload carrying a key its decoder does not
    model, is kept as an `OpaqueTrait`. The entity carrying it stays typed.
    """
    if not isinstance(payload, Mapping):
        raise MalformedRecord(
            f"traits.{protocol}", f"expected an object, found {type(payload).__name__}"
        )
    if payload.get("protocol") != protocol:
        raise MalformedRecord(
            f"traits.{protocol}.protocol",
            f"the payload names protocol {payload.get('protocol')!r}",
        )
    decoder = _DECODERS.get(protocol)
    if decoder is None:
        return OpaqueTrait(protocol, payload)
    try:
        return decoder(payload)
    except UnmodelledKeys:
        return OpaqueTrait(protocol, payload)


for _trait in (Footprint, Sourcing, DatasheetEvidence, Simulatable, Renderable):
    register_trait(_trait.protocol, _trait.from_dict)


class TraitRegistry:
    """Which entities carry which protocols.

    Enumeration reads this table. It never touches the traits' subject matter, so
    asking "what is simulatable" costs a dictionary lookup rather than a backend.
    """

    __slots__ = ("_by_entity", "_by_protocol", "_untyped")

    def __init__(self) -> None:
        self._by_entity: dict[str, dict[str, Trait]] = {}
        self._by_protocol: dict[str, set[str]] = {}
        self._untyped: dict[str, frozenset[str]] = {}

    @classmethod
    def from_entities(cls, entities: Mapping[str, Any]) -> "TraitRegistry":
        """The traits a set of entities carries, as a registry.

        The entities hold the traits and this is built from them, so the two
        cannot disagree. Each trait is copied, so a consumer that changes what it
        is handed does not reach into a frozen snapshot. A trait that loaded
        untyped is not attached under its protocol, because it does not satisfy
        it. It is recorded instead, so a consumer that needs it can refuse rather
        than read a gap as an absence.
        """
        registry = cls()
        for entity_id in sorted(entities):
            untyped = []
            for protocol, trait in sorted(getattr(entities[entity_id], "traits", {}).items()):
                if isinstance(trait, OpaqueTrait):
                    untyped.append(protocol)
                else:
                    registry.attach(entity_id, deepcopy(trait))
            if untyped:
                registry._untyped[entity_id] = frozenset(untyped)
        return registry

    def untyped(self, entity_id: str, protocol: str) -> bool:
        """Whether the entity carries this protocol in a form no decoder could type."""
        return protocol in self._untyped.get(entity_id, ())

    def attach(self, entity_id: str, trait: Trait) -> Trait:
        if not trait.protocol:
            raise ValueError("a trait declares the protocol it satisfies")
        self._by_entity.setdefault(entity_id, {})[trait.protocol] = trait
        self._by_protocol.setdefault(trait.protocol, set()).add(entity_id)
        return trait

    def of(self, entity_id: str) -> dict[str, Trait]:
        return dict(self._by_entity.get(entity_id, {}))

    def get(self, entity_id: str, protocol: str) -> Trait | None:
        return self._by_entity.get(entity_id, {}).get(protocol)

    def has(self, entity_id: str, protocol: str) -> bool:
        return protocol in self._by_entity.get(entity_id, {})

    def entities_with(self, protocol: str) -> list[str]:
        """Every entity carrying the protocol, with no backend instantiated."""
        return sorted(self._by_protocol.get(protocol, ()))

    def protocols(self) -> list[str]:
        return sorted(self._by_protocol)

    def as_dict(self) -> dict:
        return {
            entity_id: {
                protocol: trait.as_dict() for protocol, trait in sorted(traits.items())
            }
            for entity_id, traits in sorted(self._by_entity.items())
        }

    def __len__(self) -> int:
        return sum(len(traits) for traits in self._by_entity.values())
