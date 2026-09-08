"""Traits: behaviour attaches to entities without widening their classes.

Spec: "Traits As The Extension Mechanism" and "Trait Registration And
Enumeration". A trait declares the protocol it satisfies, and the kernel
enumerates the entities carrying a protocol without instantiating any backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from .provenance import Provenance


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


@dataclass
class Footprint(Trait):
    """Where a component lands physically."""

    protocol = "footprint"
    library: str = ""
    name: str = ""


@dataclass
class Sourcing(Trait):
    """Where a component is bought."""

    protocol = "sourcing"
    manufacturer: str = ""
    mpn: str = ""
    distributor_ids: Mapping[str, str] = field(default_factory=dict)


@dataclass
class DatasheetEvidence(Trait):
    """The document a component's claims are cited from."""

    protocol = "datasheet_evidence"
    document: str = ""
    evidence_ids: tuple[str, ...] = ()


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


@dataclass
class Renderable(Trait):
    """A hint for the view compiler. It carries no geometry and no meaning."""

    protocol = "renderable"
    symbol: str = ""


class TraitRegistry:
    """Which entities carry which protocols.

    Enumeration reads this table. It never touches the traits' subject matter, so
    asking "what is simulatable" costs a dictionary lookup rather than a backend.
    """

    __slots__ = ("_by_entity", "_by_protocol")

    def __init__(self) -> None:
        self._by_entity: dict[str, dict[str, Trait]] = {}
        self._by_protocol: dict[str, set[str]] = {}

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
