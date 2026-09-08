"""Diagnostics: stable namespaced codes, severities, and the code registry.

Spec: "Namespaced Diagnostic Codes". A code has the form ``<AREA>-<NNNN>`` over
the fixed areas below. A code, once allocated, is never reused for a different
condition and never renumbered; a diagnostic no longer emitted is marked retired
and its code stays allocated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

#: The areas this specification allocates within. A vendor may add an area under
#: its own namespace but must not allocate within these.
AREAS = ("ELAB", "IFACE", "TOPO", "UNIT", "TXN", "SIM", "IMPORT", "MCP")


class Severity(Enum):
    """How a diagnostic is treated. Blocking severities stop a commit."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"

    @property
    def blocking(self) -> bool:
        return self is Severity.ERROR


@dataclass(frozen=True)
class SourceLocation:
    """The file and line that produced an entity or a diagnostic."""

    file: str
    line: int
    column: int | None = None

    def as_dict(self) -> dict:
        out = {"file": self.file, "line": self.line}
        if self.column is not None:
            out["column"] = self.column
        return out


@dataclass(frozen=True)
class Code:
    """An allocated diagnostic code."""

    code: str
    area: str
    number: int
    description: str
    retired: bool = False


class CodeRegistry:
    """The allocated diagnostic codes.

    The registry refuses to reallocate a code for a different condition and
    refuses to renumber one, because suppressions and waivers reference codes by
    value and must stay meaningful across releases.
    """

    def __init__(self) -> None:
        self._codes: dict[str, Code] = {}

    def allocate(self, code: str, description: str) -> Code:
        area, _, number = code.partition("-")
        if area not in AREAS:
            raise ValueError(
                f"{code!r}: area {area!r} is not one of {', '.join(AREAS)}; "
                "a vendor area must carry its own namespace"
            )
        if len(number) != 4 or not number.isdigit():
            raise ValueError(f"{code!r}: the number must be four digits")

        existing = self._codes.get(code)
        if existing is not None:
            if existing.description != description:
                raise ValueError(
                    f"{code} is already allocated to {existing.description!r}; "
                    "a code is never reused for a different condition"
                )
            return existing

        allocated = Code(code, area, int(number), description)
        self._codes[code] = allocated
        return allocated

    def retire(self, code: str) -> Code:
        """Mark a code retired. It stays allocated and is never reissued."""
        current = self._codes[code]
        retired = Code(
            current.code, current.area, current.number, current.description, retired=True
        )
        self._codes[code] = retired
        return retired

    def get(self, code: str) -> Code:
        return self._codes[code]

    def __contains__(self, code: object) -> bool:
        return code in self._codes

    def __iter__(self) -> Iterable[Code]:
        return iter(sorted(self._codes.values(), key=lambda c: c.code))


#: The released registry. Codes are added here, never removed.
REGISTRY = CodeRegistry()


def _allocate(code: str, description: str) -> str:
    REGISTRY.allocate(code, description)
    return code


# Unit and dimension conditions.
UNIT_DIMENSION_MISMATCH = _allocate(
    "UNIT-0001", "operands of unequal dimension combined"
)
UNIT_UNKNOWN_SYMBOL = _allocate("UNIT-0002", "unit symbol not recognized")
UNIT_BAD_EXPONENT = _allocate("UNIT-0003", "exponent is not a dimensionless rational")
UNIT_INEXACT_CONVERSION = _allocate("UNIT-0004", "unit conversion rounded")

# Elaboration and identity conditions.
ELAB_PATH_INVALID = _allocate("ELAB-0001", "canonical semantic path is not well formed")
ELAB_PATH_COLLISION = _allocate("ELAB-0002", "two entities share a canonical semantic path")
ELAB_DUPLICATE_ID = _allocate("ELAB-0003", "identifier is not unique within the revision")
ELAB_NO_PROVENANCE = _allocate(
    "ELAB-0004", "entity traceable to neither a source location nor an import"
)
ELAB_UNTYPED_CONNECTION = _allocate("ELAB-0005", "connection has no kind")
ELAB_DANGLING_REFERENCE = _allocate("ELAB-0006", "required reference names no entity")
ELAB_INVALID_STATE_TRANSITION = _allocate(
    "ELAB-0007", "requirement state transition outside the permitted table"
)
ELAB_HANDLE_READ = _allocate(
    "ELAB-0008", "tool handle read during elaboration"
)
ELAB_SCHEMA_MAJOR_UNSUPPORTED = _allocate(
    "ELAB-0009", "artifact declares an unimplemented major schema version"
)
ELAB_PROHIBITED_CYCLE = _allocate("ELAB-0010", "cycle where one is prohibited")
ELAB_CONTRADICTORY_CONSTRAINTS = _allocate(
    "ELAB-0011", "contradictory mandatory constraints"
)
ELAB_SECOND_REGISTRY = _allocate(
    "ELAB-0012", "a second constraint registry was created"
)

# Transaction conditions.
TXN_STALE_SNAPSHOT = _allocate(
    "TXN-0001", "transaction proposed against a snapshot that is no longer current"
)
TXN_GATE_BLOCKED = _allocate("TXN-0002", "a required check reported a blocking severity")
TXN_UNDECIDED_BLOCKED = _allocate(
    "TXN-0003", "an undecided result covers a must-be-decided requirement"
)
TXN_APPROVAL_REQUIRED = _allocate("TXN-0004", "policy approval requirements unsatisfied")
TXN_MALFORMED_ENTITY = _allocate("TXN-0005", "operation did not normalize into a well-formed entity")

# Interface conditions.
IFACE_UNSATISFIABLE_SIGNAL = _allocate(
    "IFACE-0001", "a required interface signal has no pin"
)
IFACE_MEMBERSHIP_DISAGREEMENT = _allocate(
    "IFACE-0002", "two interfaces disagree on membership"
)

# Import conditions.
IMPORT_LOSSY = _allocate("IMPORT-0001", "adapter could not represent a construct")

# Agent surface conditions. A refusal at the protocol boundary is its own area:
# it describes the boundary, not the transaction the boundary was asked about.
MCP_PATH_OUTSIDE_ROOT = _allocate(
    "MCP-0001", "a path outside the bound project root was named"
)
MCP_UNKNOWN_TOOL = _allocate("MCP-0002", "no tool by that name is exposed")
MCP_MALFORMED_ARGUMENT = _allocate("MCP-0003", "an argument did not parse")
MCP_UNACCEPTED_PROPOSAL = _allocate(
    "MCP-0004", "commit named a proposal the gate did not accept"
)
MCP_DEPENDENCY_MISSING = _allocate(
    "MCP-0005", "the protocol dependency is not installed"
)
MCP_UNKNOWN_OPERATION = _allocate(
    "MCP-0006", "operation kind is not one the commit gate evaluates"
)


@dataclass(frozen=True)
class Diagnostic:
    """One diagnostic: a stable code, a severity, entities, a location, a message."""

    code: str
    severity: Severity
    message: str
    entities: tuple[str, ...] = ()
    location: SourceLocation | None = None

    def __post_init__(self) -> None:
        if self.code not in REGISTRY:
            raise ValueError(f"{self.code} is not an allocated diagnostic code")

    def as_dict(self) -> dict:
        out: dict = {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
        }
        if self.entities:
            out["entities"] = list(self.entities)
        if self.location is not None:
            out["source_location"] = self.location.as_dict()
        return out


class FangError(Exception):
    """An error carrying a diagnostic."""

    def __init__(self, diagnostic: Diagnostic) -> None:
        super().__init__(f"{diagnostic.code}: {diagnostic.message}")
        self.diagnostic = diagnostic


def error(code: str, message: str, *, entities: Iterable[str] = (), location: SourceLocation | None = None) -> FangError:
    """Build a `FangError` carrying an ERROR-severity diagnostic."""
    return FangError(
        Diagnostic(code, Severity.ERROR, message, tuple(entities), location)
    )
