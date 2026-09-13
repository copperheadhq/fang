"""The EIR entity model the kernel graph holds.

Spec: "Typed Connections", "Typed Interfaces, Ports, Buses, and Domains",
"Requirement State Transitions", "Structural Validation", and "A Persisted
Snapshot Reloads Without Running A Program". The kernel graph holds these
entities and nothing else; there is no second model.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Mapping, Sequence

from .diagnostics import ELAB_UNTYPED_CONNECTION, SourceLocation, error
from .identity import Identity, Origin
from .provenance import Provenance
from .records import (
    MalformedRecord,
    boolean,
    expect_keys,
    freeze,
    listed,
    member,
    optional_text,
    required,
    text,
    text_mapping,
    texts,
)
from .traits import Trait, decode_trait
from .values import Parameter, Value, parameter_from_dict


class ConnectionKind(Enum):
    """The minimum set of connection kinds. An untyped connection is not
    representable, so this enum has no default and no ``UNKNOWN`` member."""

    ELECTRICAL = "electrical"
    POWER = "power"
    SIGNAL = "signal"
    GROUND = "ground"
    MECHANICAL = "mechanical"
    CONTROL = "control"
    DEPENDENCY = "dependency"
    CONTAINMENT = "containment"


class RequirementState(Enum):
    KNOWN = "KNOWN"
    ASSUMED = "ASSUMED"
    DERIVED = "DERIVED"
    MISSING = "MISSING"
    CONFLICTING = "CONFLICTING"
    WAIVED = "WAIVED"
    VERIFIED = "VERIFIED"


#: The permitted transitions. No transition enters MISSING, and none reaches
#: VERIFIED from MISSING or ASSUMED.
TRANSITIONS: Mapping[RequirementState, frozenset[RequirementState]] = {
    RequirementState.MISSING: frozenset(
        {RequirementState.KNOWN, RequirementState.ASSUMED,
         RequirementState.DERIVED, RequirementState.WAIVED}
    ),
    RequirementState.ASSUMED: frozenset(
        {RequirementState.KNOWN, RequirementState.DERIVED,
         RequirementState.CONFLICTING, RequirementState.WAIVED}
    ),
    RequirementState.DERIVED: frozenset(
        {RequirementState.KNOWN, RequirementState.CONFLICTING,
         RequirementState.WAIVED, RequirementState.VERIFIED}
    ),
    RequirementState.KNOWN: frozenset(
        {RequirementState.DERIVED, RequirementState.CONFLICTING,
         RequirementState.WAIVED, RequirementState.VERIFIED}
    ),
    RequirementState.CONFLICTING: frozenset(
        {RequirementState.KNOWN, RequirementState.ASSUMED,
         RequirementState.DERIVED, RequirementState.WAIVED}
    ),
    RequirementState.WAIVED: frozenset(
        {RequirementState.KNOWN, RequirementState.ASSUMED, RequirementState.DERIVED}
    ),
    RequirementState.VERIFIED: frozenset(
        {RequirementState.KNOWN, RequirementState.CONFLICTING, RequirementState.WAIVED}
    ),
}


@dataclass(frozen=True)
class Entity:
    """The base of every first-class entity.

    Identity, provenance, and a source location travel with every entity,
    because an entity traceable to neither a source location nor an import is a
    defect.
    """

    identity: Identity
    kind: str
    parameters: Mapping[str, Parameter] = field(default_factory=dict)
    provenance: Provenance = field(default_factory=Provenance)
    source_location: SourceLocation | None = None
    extensions: Mapping[str, Any] = field(default_factory=dict)
    #: The traits the entity carries, keyed by protocol. A trait is state: it
    #: serializes inside this entity's record and is read back with it.
    traits: Mapping[str, Trait] = field(default_factory=dict)

    #: The keys `_base_dict` writes, and the keys a subclass's `as_dict` adds. A
    #: decoder refuses a key outside both rather than guess at it.
    _BASE_KEYS = frozenset(
        {"kind", "identity", "id", "parameters", "provenance", "source_location",
         "extensions", "traits"}
    )
    _RECORD_KEYS = frozenset()

    @property
    def id(self) -> str:
        return self.identity.id

    def with_parameter(self, name: str, value: Parameter) -> "Entity":
        parameters = dict(self.parameters)
        parameters[name] = value
        return replace(self, parameters=parameters)

    def references(self) -> tuple[str, ...]:
        """The identifiers this entity requires to exist. Validation checks them."""
        return ()

    def _base_dict(self) -> dict:
        out: dict = {"kind": self.kind, "identity": self.identity.as_dict()}
        out["id"] = self.identity.id
        if self.parameters:
            out["parameters"] = {
                name: value.as_dict() for name, value in self.parameters.items()
            }
        if not self.provenance.empty:
            out["provenance"] = self.provenance.as_list()
        if self.source_location is not None:
            out["source_location"] = self.source_location.as_dict()
        if self.extensions:
            out["extensions"] = dict(self.extensions)
        if self.traits:
            out["traits"] = {
                protocol: trait.as_dict() for protocol, trait in self.traits.items()
            }
        return out

    def as_dict(self) -> dict:
        return self._base_dict()

    @classmethod
    def _decode_base(cls, record: Mapping[str, Any]) -> dict[str, Any]:
        """Decode what `_base_dict` wrote, refusing any key `as_dict` does not write."""
        if not isinstance(record, Mapping):
            raise MalformedRecord("record", f"expected an object, found {type(record).__name__}")
        expect_keys(record, cls._BASE_KEYS | cls._RECORD_KEYS, f"{record.get('kind')} record")
        identity = Identity.from_dict(required(record, "identity"))
        if required(record, "id") != identity.id:
            raise MalformedRecord("id", f"{record['id']!r} is not the identity's id {identity.id!r}")
        parameters = record.get("parameters", {})
        extensions = record.get("extensions", {})
        traits = record.get("traits", {})
        for name, value in (("parameters", parameters), ("extensions", extensions), ("traits", traits)):
            if not isinstance(value, Mapping):
                raise MalformedRecord(name, f"expected an object, found {type(value).__name__}")
        location = record.get("source_location")
        return {
            "identity": identity,
            "parameters": {
                text(name, "parameters"): parameter_from_dict(value)
                for name, value in parameters.items()
            },
            "provenance": Provenance.from_list(record.get("provenance", [])),
            "source_location": SourceLocation.from_dict(location) if location is not None else None,
            "extensions": freeze(extensions),
            "traits": {
                text(protocol, "traits"): decode_trait(protocol, payload)
                for protocol, payload in traits.items()
            },
        }

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> "Entity":
        """The inverse of `as_dict`, for an entity with no fields of its own."""
        return cls(kind=text(required(record, "kind"), "kind"), **cls._decode_base(record))


@dataclass(frozen=True)
class Requirement(Entity):
    statement: str = ""
    state: RequirementState = RequirementState.KNOWN
    priority: str = "MUST"
    source: str = "user"
    validation_method: str | None = None
    kind: str = "requirement"

    _RECORD_KEYS = frozenset({"statement", "state", "priority", "source", "validation"})

    def as_dict(self) -> dict:
        out = self._base_dict()
        out.update(
            {
                "statement": self.statement,
                "state": self.state.value,
                "priority": self.priority,
                "source": self.source,
            }
        )
        if self.validation_method is not None:
            out["validation"] = {"method": self.validation_method}
        return out

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> "Requirement":
        """The inverse of `as_dict`."""
        base = cls._decode_base(record)
        validation = record.get("validation")
        method = None
        if validation is not None:
            expect_keys(validation, ("method",), "validation")
            method = text(required(validation, "method", "validation.method"), "validation.method")
        return cls(
            **base,
            statement=text(required(record, "statement"), "statement"),
            state=member(RequirementState, required(record, "state"), "state"),
            priority=text(required(record, "priority"), "priority"),
            source=text(required(record, "source"), "source"),
            validation_method=method,
        )


@dataclass(frozen=True)
class Connection(Entity):
    """A typed connection between two entities.

    The kind is required and has no default: an untyped connection must not be
    representable.
    """

    kind: str = "connection"
    connection_kind: ConnectionKind | None = None
    source: str = ""
    target: str = ""
    derived_from_interface: str | None = None

    _RECORD_KEYS = frozenset({"connection_kind", "source", "target", "derived_from_interface"})

    def __post_init__(self) -> None:
        if self.connection_kind is None:
            raise error(
                ELAB_UNTYPED_CONNECTION,
                f"connection {self.identity.id} has no kind; every connection is "
                "typed",
                entities=[self.identity.id],
            )
        if not self.source or not self.target:
            raise ValueError("a connection names both endpoints")

    def references(self) -> tuple[str, ...]:
        refs = (self.source, self.target)
        if self.derived_from_interface is not None:
            refs += (self.derived_from_interface,)
        return refs

    def as_dict(self) -> dict:
        out = self._base_dict()
        out.update(
            {
                "connection_kind": self.connection_kind.value,
                "source": self.source,
                "target": self.target,
            }
        )
        if self.derived_from_interface is not None:
            out["derived_from_interface"] = self.derived_from_interface
        return out

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> "Connection":
        """The inverse of `as_dict`."""
        base = cls._decode_base(record)
        return cls(
            **base,
            connection_kind=member(
                ConnectionKind, required(record, "connection_kind"), "connection_kind"
            ),
            source=text(required(record, "source"), "source"),
            target=text(required(record, "target"), "target"),
            derived_from_interface=optional_text(record, "derived_from_interface"),
        )


@dataclass(frozen=True)
class Component(Entity):
    kind: str = "component"
    designator: str | None = None
    part: str | None = None
    package: str | None = None
    models: tuple[str, ...] = ()

    _RECORD_KEYS = frozenset({"designator", "part", "package", "models"})

    def references(self) -> tuple[str, ...]:
        return self.models

    def as_dict(self) -> dict:
        out = self._base_dict()
        for name, value in (
            ("designator", self.designator),
            ("part", self.part),
            ("package", self.package),
        ):
            if value is not None:
                out[name] = value
        if self.models:
            out["models"] = sorted(self.models)
        return out

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> "Component":
        """The inverse of `as_dict`."""
        base = cls._decode_base(record)
        return cls(
            **base,
            designator=optional_text(record, "designator"),
            part=optional_text(record, "part"),
            package=optional_text(record, "package"),
            models=texts(record.get("models", []), "models"),
        )


@dataclass(frozen=True)
class Net(Entity):
    kind: str = "net"
    aliases: tuple[str, ...] = ()
    domain: str | None = None
    #: The pins this net joins, where a source named the net rather than leaving
    #: it to be inferred from connections. A design authored in Fang has
    #: connections and no net entities; an imported one has net entities and no
    #: synthetic connection chain. Never both for the same facts.
    members: tuple[str, ...] = ()

    _RECORD_KEYS = frozenset({"aliases", "domain", "members"})

    def references(self) -> tuple[str, ...]:
        return ((self.domain,) if self.domain else ()) + self.members

    def as_dict(self) -> dict:
        out = self._base_dict()
        if self.aliases:
            out["aliases"] = sorted(self.aliases)
        if self.domain is not None:
            out["domain"] = self.domain
        if self.members:
            out["members"] = sorted(self.members)
        return out

    @classmethod
    def _net_fields(cls, record: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "aliases": texts(record.get("aliases", []), "aliases"),
            "domain": optional_text(record, "domain"),
            "members": texts(record.get("members", []), "members"),
        }

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> "Net":
        """The inverse of `as_dict`."""
        base = cls._decode_base(record)
        return cls(**base, **cls._net_fields(record))


@dataclass(frozen=True)
class Rail(Net):
    """A specialized net carrying rail semantics."""

    kind: str = "rail"
    source_blocks: tuple[str, ...] = ()
    load_blocks: tuple[str, ...] = ()
    power_sequence: tuple[str, ...] = ()

    _RECORD_KEYS = Net._RECORD_KEYS | frozenset(
        {"source_blocks", "load_blocks", "power_sequence"}
    )

    def references(self) -> tuple[str, ...]:
        return super().references() + self.source_blocks + self.load_blocks

    def as_dict(self) -> dict:
        out = super().as_dict()
        if self.source_blocks:
            out["source_blocks"] = sorted(self.source_blocks)
        if self.load_blocks:
            out["load_blocks"] = sorted(self.load_blocks)
        if self.power_sequence:
            # Order carries meaning here; it is preserved, not sorted.
            out["power_sequence"] = list(self.power_sequence)
        return out

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> "Rail":
        """The inverse of `as_dict`. The power sequence keeps its order."""
        base = cls._decode_base(record)
        return cls(
            **base,
            **cls._net_fields(record),
            source_blocks=texts(record.get("source_blocks", []), "source_blocks"),
            load_blocks=texts(record.get("load_blocks", []), "load_blocks"),
            power_sequence=texts(record.get("power_sequence", []), "power_sequence"),
        )


@dataclass(frozen=True)
class Signal:
    """One member signal of an interface definition."""

    name: str
    role: str
    direction: str | None = None
    required: bool = True

    def as_dict(self) -> dict:
        out = {"name": self.name, "role": self.role, "required": self.required}
        if self.direction is not None:
            out["direction"] = self.direction
        return out

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Signal":
        """The inverse of `as_dict`."""
        expect_keys(payload, ("name", "role", "required", "direction"), "signal")
        return cls(
            text(required(payload, "name", "signal.name"), "signal.name"),
            text(required(payload, "role", "signal.role"), "signal.role"),
            direction=optional_text(payload, "direction", "signal.direction"),
            required=boolean(required(payload, "required", "signal.required"), "signal.required"),
        )


@dataclass(frozen=True)
class Interface(Entity):
    """A typed connection surface: named signals with roles and parameters."""

    kind: str = "interface"
    interface_type: str = ""
    signals: tuple[Signal, ...] = ()
    direction: str | None = None

    _RECORD_KEYS = frozenset({"interface_type", "signals", "direction"})

    def as_dict(self) -> dict:
        out = self._base_dict()
        out["interface_type"] = self.interface_type
        out["signals"] = [s.as_dict() for s in self.signals]
        if self.direction is not None:
            out["direction"] = self.direction
        return out

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> "Interface":
        """The inverse of `as_dict`."""
        base = cls._decode_base(record)
        return cls(
            **base,
            interface_type=text(required(record, "interface_type"), "interface_type"),
            signals=tuple(
                Signal.from_dict(item)
                for item in listed(required(record, "signals"), "signals")
            ),
            direction=optional_text(record, "direction"),
        )


@dataclass(frozen=True)
class Port(Entity):
    """An interface instance owned by a component, module, or block."""

    kind: str = "port"
    interface: str = ""
    owner: str = ""
    direction: str | None = None

    _RECORD_KEYS = frozenset({"interface", "owner", "direction"})

    def references(self) -> tuple[str, ...]:
        return (self.interface, self.owner)

    def as_dict(self) -> dict:
        out = self._base_dict()
        out.update({"interface": self.interface, "owner": self.owner})
        if self.direction is not None:
            out["direction"] = self.direction
        return out

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> "Port":
        """The inverse of `as_dict`."""
        base = cls._decode_base(record)
        return cls(
            **base,
            interface=text(required(record, "interface"), "interface"),
            owner=text(required(record, "owner"), "owner"),
            direction=optional_text(record, "direction"),
        )


@dataclass(frozen=True)
class Pin(Entity):
    """One pin of a component.

    The canonical electrical role is what the kernel reasons about; the vendor
    name is what the datasheet calls it, and is preserved.
    """

    kind: str = "pin"
    owner: str = ""
    vendor_name: str = ""
    role: str = "unknown"
    number: str | None = None

    _RECORD_KEYS = frozenset({"owner", "vendor_name", "role", "number"})

    def references(self) -> tuple[str, ...]:
        return (self.owner,) if self.owner else ()

    def as_dict(self) -> dict:
        out = self._base_dict()
        out.update({"owner": self.owner, "vendor_name": self.vendor_name, "role": self.role})
        if self.number is not None:
            out["number"] = self.number
        return out

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> "Pin":
        """The inverse of `as_dict`."""
        base = cls._decode_base(record)
        return cls(
            **base,
            owner=text(required(record, "owner"), "owner"),
            vendor_name=text(required(record, "vendor_name"), "vendor_name"),
            role=text(required(record, "role"), "role"),
            number=optional_text(record, "number"),
        )


@dataclass(frozen=True)
class Bus(Entity):
    """An interface whose participants are many rather than two."""

    kind: str = "bus"
    interface: str = ""
    participants: tuple[str, ...] = ()

    _RECORD_KEYS = frozenset({"interface", "participants"})

    def references(self) -> tuple[str, ...]:
        return (self.interface,) + self.participants

    def as_dict(self) -> dict:
        out = self._base_dict()
        out["interface"] = self.interface
        out["participants"] = sorted(self.participants)
        return out

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> "Bus":
        """The inverse of `as_dict`."""
        base = cls._decode_base(record)
        return cls(
            **base,
            interface=text(required(record, "interface"), "interface"),
            participants=texts(required(record, "participants"), "participants"),
        )


@dataclass(frozen=True)
class Domain(Entity):
    """Entities sharing a voltage, ground, isolation, or timing reference."""

    kind: str = "domain"
    domain_kind: str = "ground"
    members: tuple[str, ...] = ()

    _RECORD_KEYS = frozenset({"domain_kind", "members"})

    def references(self) -> tuple[str, ...]:
        return self.members

    def as_dict(self) -> dict:
        out = self._base_dict()
        out["domain_kind"] = self.domain_kind
        out["members"] = sorted(self.members)
        return out

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> "Domain":
        """The inverse of `as_dict`."""
        base = cls._decode_base(record)
        return cls(
            **base,
            domain_kind=text(required(record, "domain_kind"), "domain_kind"),
            members=texts(required(record, "members"), "members"),
        )


@dataclass(frozen=True)
class Decision(Entity):
    kind: str = "decision"
    question: str = ""
    choice: str | None = None
    rationale: tuple[str, ...] = ()
    alternatives_rejected: tuple[Mapping[str, str], ...] = ()
    requirements: tuple[str, ...] = ()

    _RECORD_KEYS = frozenset(
        {"question", "choice", "rationale", "alternatives_rejected", "requirements"}
    )

    def references(self) -> tuple[str, ...]:
        return self.requirements

    def as_dict(self) -> dict:
        out = self._base_dict()
        out["question"] = self.question
        if self.choice is not None:
            out["choice"] = self.choice
        if self.rationale:
            out["rationale"] = list(self.rationale)
        if self.alternatives_rejected:
            out["alternatives_rejected"] = [dict(a) for a in self.alternatives_rejected]
        if self.requirements:
            out["requirements"] = sorted(self.requirements)
        return out

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> "Decision":
        """The inverse of `as_dict`. The rationale and the rejections keep their order."""
        base = cls._decode_base(record)
        return cls(
            **base,
            question=text(required(record, "question"), "question"),
            choice=optional_text(record, "choice"),
            rationale=texts(record.get("rationale", []), "rationale"),
            alternatives_rejected=tuple(
                text_mapping(item, "alternatives_rejected")
                for item in listed(record.get("alternatives_rejected", []), "alternatives_rejected")
            ),
            requirements=texts(record.get("requirements", []), "requirements"),
        )


@dataclass(frozen=True)
class Evidence(Entity):
    kind: str = "evidence"
    claim: str = ""
    document: str | None = None
    locator: str | None = None

    _RECORD_KEYS = frozenset({"claim", "document", "locator"})

    def as_dict(self) -> dict:
        out = self._base_dict()
        out["claim"] = self.claim
        for name, value in (("document", self.document), ("locator", self.locator)):
            if value is not None:
                out[name] = value
        return out

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> "Evidence":
        """The inverse of `as_dict`."""
        base = cls._decode_base(record)
        return cls(
            **base,
            claim=text(required(record, "claim"), "claim"),
            document=optional_text(record, "document"),
            locator=optional_text(record, "locator"),
        )


@dataclass(frozen=True)
class Calculation(Entity):
    """A computed engineering result, with what it depends on.

    Recorded so that a later change can invalidate it: a number nobody can trace
    to its inputs cannot be re-checked when one of them moves.
    """

    kind: str = "calculation"
    expression: str = ""
    inputs: tuple[str, ...] = ()
    result: str | None = None
    requirements: tuple[str, ...] = ()

    _RECORD_KEYS = frozenset({"expression", "inputs", "result", "requirements"})

    def references(self) -> tuple[str, ...]:
        return self.inputs + self.requirements

    def as_dict(self) -> dict:
        out = self._base_dict()
        out["expression"] = self.expression
        out["inputs"] = sorted(self.inputs)
        if self.result is not None:
            out["result"] = self.result
        if self.requirements:
            out["requirements"] = sorted(self.requirements)
        return out

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> "Calculation":
        """The inverse of `as_dict`."""
        base = cls._decode_base(record)
        return cls(
            **base,
            expression=text(required(record, "expression"), "expression"),
            inputs=texts(required(record, "inputs"), "inputs"),
            result=optional_text(record, "result"),
            requirements=texts(record.get("requirements", []), "requirements"),
        )


@dataclass(frozen=True)
class Verification(Entity):
    """What was verified, how, on what evidence, and with what outcome."""

    kind: str = "verification"
    verifies: str = ""
    method: str = "analysis"
    evidence: tuple[str, ...] = ()
    result: str = "UNKNOWN"

    _RECORD_KEYS = frozenset({"verifies", "method", "result", "evidence"})

    def references(self) -> tuple[str, ...]:
        return ((self.verifies,) if self.verifies else ()) + self.evidence

    def as_dict(self) -> dict:
        out = self._base_dict()
        out.update({"verifies": self.verifies, "method": self.method, "result": self.result})
        if self.evidence:
            out["evidence"] = sorted(self.evidence)
        return out

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> "Verification":
        """The inverse of `as_dict`."""
        base = cls._decode_base(record)
        return cls(
            **base,
            verifies=text(required(record, "verifies"), "verifies"),
            method=text(required(record, "method"), "method"),
            result=text(required(record, "result"), "result"),
            evidence=texts(record.get("evidence", []), "evidence"),
        )


@dataclass(frozen=True)
class Assumption(Entity):
    """A claim with no citation behind it. Never silently promoted to evidence."""

    kind: str = "assumption"
    claim: str = ""
    rationale: str = ""

    _RECORD_KEYS = frozenset({"claim", "rationale"})

    def as_dict(self) -> dict:
        out = self._base_dict()
        out.update({"claim": self.claim, "rationale": self.rationale})
        return out

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> "Assumption":
        """The inverse of `as_dict`."""
        base = cls._decode_base(record)
        return cls(
            **base,
            claim=text(required(record, "claim"), "claim"),
            rationale=text(required(record, "rationale"), "rationale"),
        )


@dataclass(frozen=True)
class Model(Entity):
    """A behaviour or simulation model attached to a component as a trait."""

    kind: str = "model"
    model_kind: str = "spice_subckt"
    component: str = ""
    backends: tuple[str, ...] = ()
    source: str | None = None
    pin_map: Mapping[str, str] = field(default_factory=dict)
    conditions: Mapping[str, str] = field(default_factory=dict)
    distribution_restricted: bool = False

    _RECORD_KEYS = frozenset(
        {"model_kind", "component", "backends", "distribution_restricted", "source",
         "pin_map", "conditions"}
    )

    def references(self) -> tuple[str, ...]:
        return (self.component,) if self.component else ()

    def as_dict(self) -> dict:
        out = self._base_dict()
        out.update(
            {
                "model_kind": self.model_kind,
                "component": self.component,
                "backends": sorted(self.backends),
                "distribution_restricted": self.distribution_restricted,
            }
        )
        if self.source is not None:
            out["source"] = self.source
        if self.pin_map:
            out["pin_map"] = dict(self.pin_map)
        if self.conditions:
            out["conditions"] = dict(self.conditions)
        return out

    @classmethod
    def from_dict(cls, record: Mapping[str, Any]) -> "Model":
        """The inverse of `as_dict`."""
        base = cls._decode_base(record)
        return cls(
            **base,
            model_kind=text(required(record, "model_kind"), "model_kind"),
            component=text(required(record, "component"), "component"),
            backends=texts(required(record, "backends"), "backends"),
            distribution_restricted=boolean(
                required(record, "distribution_restricted"), "distribution_restricted"
            ),
            source=optional_text(record, "source"),
            pin_map=text_mapping(record.get("pin_map", {}), "pin_map"),
            conditions=text_mapping(record.get("conditions", {}), "conditions"),
        )


#: Every collection key of the project root. All are present in machine-generated
#: state even when empty, so a missing key identifies an older schema rather than
#: an empty layer.
ROOT_COLLECTIONS: tuple[str, ...] = (
    "requirements",
    "architecture",
    "interfaces",
    "ports",
    "buses",
    "domains",
    "components",
    "models",
    "nets",
    "circuits",
    "connections",
    "decisions",
    "evidence",
    "constraints",
    "calculations",
    "verifications",
    "assumptions",
    "outcomes",
)

#: Root keys that are mappings rather than collections.
ROOT_MAPPINGS: tuple[str, ...] = ("physical", "manufacturing", "provenance")
