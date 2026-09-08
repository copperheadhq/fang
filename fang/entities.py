"""The EIR entity model the kernel graph holds.

Spec: "Typed Connections", "Typed Interfaces, Ports, Buses, and Domains",
"Requirement State Transitions", and "Structural Validation". The kernel graph
holds these entities and nothing else; there is no second model.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Mapping, Sequence

from .diagnostics import ELAB_UNTYPED_CONNECTION, SourceLocation, error
from .identity import Identity, Origin
from .provenance import Provenance
from .values import Parameter, Value


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
        return out

    def as_dict(self) -> dict:
        return self._base_dict()


@dataclass(frozen=True)
class Requirement(Entity):
    statement: str = ""
    state: RequirementState = RequirementState.KNOWN
    priority: str = "MUST"
    source: str = "user"
    validation_method: str | None = None
    kind: str = "requirement"

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


@dataclass(frozen=True)
class Component(Entity):
    kind: str = "component"
    designator: str | None = None
    part: str | None = None
    package: str | None = None
    models: tuple[str, ...] = ()

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


@dataclass(frozen=True)
class Rail(Net):
    """A specialized net carrying rail semantics."""

    kind: str = "rail"
    source_blocks: tuple[str, ...] = ()
    load_blocks: tuple[str, ...] = ()
    power_sequence: tuple[str, ...] = ()

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


@dataclass(frozen=True)
class Interface(Entity):
    """A typed connection surface: named signals with roles and parameters."""

    kind: str = "interface"
    interface_type: str = ""
    signals: tuple[Signal, ...] = ()
    direction: str | None = None

    def as_dict(self) -> dict:
        out = self._base_dict()
        out["interface_type"] = self.interface_type
        out["signals"] = [s.as_dict() for s in self.signals]
        if self.direction is not None:
            out["direction"] = self.direction
        return out


@dataclass(frozen=True)
class Port(Entity):
    """An interface instance owned by a component, module, or block."""

    kind: str = "port"
    interface: str = ""
    owner: str = ""
    direction: str | None = None

    def references(self) -> tuple[str, ...]:
        return (self.interface, self.owner)

    def as_dict(self) -> dict:
        out = self._base_dict()
        out.update({"interface": self.interface, "owner": self.owner})
        if self.direction is not None:
            out["direction"] = self.direction
        return out


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

    def references(self) -> tuple[str, ...]:
        return (self.owner,) if self.owner else ()

    def as_dict(self) -> dict:
        out = self._base_dict()
        out.update({"owner": self.owner, "vendor_name": self.vendor_name, "role": self.role})
        if self.number is not None:
            out["number"] = self.number
        return out


@dataclass(frozen=True)
class Bus(Entity):
    """An interface whose participants are many rather than two."""

    kind: str = "bus"
    interface: str = ""
    participants: tuple[str, ...] = ()

    def references(self) -> tuple[str, ...]:
        return (self.interface,) + self.participants

    def as_dict(self) -> dict:
        out = self._base_dict()
        out["interface"] = self.interface
        out["participants"] = sorted(self.participants)
        return out


@dataclass(frozen=True)
class Domain(Entity):
    """Entities sharing a voltage, ground, isolation, or timing reference."""

    kind: str = "domain"
    domain_kind: str = "ground"
    members: tuple[str, ...] = ()

    def references(self) -> tuple[str, ...]:
        return self.members

    def as_dict(self) -> dict:
        out = self._base_dict()
        out["domain_kind"] = self.domain_kind
        out["members"] = sorted(self.members)
        return out


@dataclass(frozen=True)
class Decision(Entity):
    kind: str = "decision"
    question: str = ""
    choice: str | None = None
    rationale: tuple[str, ...] = ()
    alternatives_rejected: tuple[Mapping[str, str], ...] = ()
    requirements: tuple[str, ...] = ()

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


@dataclass(frozen=True)
class Evidence(Entity):
    kind: str = "evidence"
    claim: str = ""
    document: str | None = None
    locator: str | None = None

    def as_dict(self) -> dict:
        out = self._base_dict()
        out["claim"] = self.claim
        for name, value in (("document", self.document), ("locator", self.locator)):
            if value is not None:
                out[name] = value
        return out


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


@dataclass(frozen=True)
class Verification(Entity):
    """What was verified, how, on what evidence, and with what outcome."""

    kind: str = "verification"
    verifies: str = ""
    method: str = "analysis"
    evidence: tuple[str, ...] = ()
    result: str = "UNKNOWN"

    def references(self) -> tuple[str, ...]:
        return ((self.verifies,) if self.verifies else ()) + self.evidence

    def as_dict(self) -> dict:
        out = self._base_dict()
        out.update({"verifies": self.verifies, "method": self.method, "result": self.result})
        if self.evidence:
            out["evidence"] = sorted(self.evidence)
        return out


@dataclass(frozen=True)
class Assumption(Entity):
    """A claim with no citation behind it. Never silently promoted to evidence."""

    kind: str = "assumption"
    claim: str = ""
    rationale: str = ""

    def as_dict(self) -> dict:
        out = self._base_dict()
        out.update({"claim": self.claim, "rationale": self.rationale})
        return out


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
