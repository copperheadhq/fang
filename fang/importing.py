"""Importing external CAD into the kernel graph.

Spec: "External Adapters Report Loss", "The External Identifier Mapping Table",
and "Imports Report What They Could Not Represent".

An external identifier never becomes canonical identity. What could not be
recovered is represented as unknown; intent is never fabricated, because an
existing project carries no record of its designer's intent and the correct
representation of that absence is the absence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Mapping, MutableMapping

from .diagnostics import IMPORT_LOSSY, Diagnostic, Severity, SourceLocation
from .entities import Entity
from .identity import Identity, Origin, derive, imported


@dataclass(frozen=True)
class Unrepresented:
    """One construct an adapter could not model."""

    construct: str
    where: str
    detail: str = ""

    def as_dict(self) -> dict:
        out = {"construct": self.construct, "where": self.where}
        if self.detail:
            out["detail"] = self.detail
        return out

    def as_diagnostic(self) -> Diagnostic:
        return Diagnostic(
            IMPORT_LOSSY,
            Severity.WARNING,
            f"{self.construct} at {self.where} was not represented"
            + (f": {self.detail}" if self.detail else ""),
        )


class MappingTable:
    """External identifiers against the canonical identifiers they were given.

    The table is part of persisted state: without it, a second import of the
    same file would mint new identifiers and every reference into the design
    would break.
    """

    def __init__(self, existing: Mapping[str, str] | None = None) -> None:
        self._to_canonical: dict[str, str] = dict(existing or {})
        self._to_external: dict[str, str] = {
            canonical: external for external, canonical in self._to_canonical.items()
        }

    def record(self, external_id: str, canonical_id: str) -> str:
        self._to_canonical[external_id] = canonical_id
        self._to_external[canonical_id] = external_id
        return canonical_id

    def canonical(self, external_id: str) -> str | None:
        return self._to_canonical.get(external_id)

    def external(self, canonical_id: str) -> str | None:
        return self._to_external.get(canonical_id)

    def as_dict(self) -> dict:
        return dict(sorted(self._to_canonical.items()))

    def __len__(self) -> int:
        return len(self._to_canonical)

    def __contains__(self, external_id: object) -> bool:
        return external_id in self._to_canonical


@dataclass
class ImportReport:
    """What an import recovered, and what it could not."""

    source: str
    unrepresented: list[Unrepresented] = field(default_factory=list)
    recovered: int = 0

    @property
    def lossless(self) -> bool:
        return not self.unrepresented

    def note(self, construct: str, where: str, detail: str = "") -> None:
        self.unrepresented.append(Unrepresented(construct, where, detail))

    def diagnostics(self) -> list[Diagnostic]:
        return [item.as_diagnostic() for item in self.unrepresented]

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "recovered": self.recovered,
            "lossless": self.lossless,
            "unrepresented": [item.as_dict() for item in self.unrepresented],
        }


@dataclass(frozen=True)
class ImportResult:
    """Everything an import produced. Never a partial success in disguise."""

    entities: Mapping[str, Entity]
    mapping: MappingTable
    report: ImportReport

    @property
    def ok(self) -> bool:
        return True     # loss is reported, not fatal; a malformed file raises

    def as_dict(self) -> dict:
        return {
            "mapping": self.mapping.as_dict(),
            "report": self.report.as_dict(),
        }


def canonical_id_for(
    external_id: str,
    kind: str,
    path: str,
    *,
    project_id: str,
    mapping: MappingTable,
    recovered: str | None = None,
    taken: Iterable[str] = (),
) -> Identity:
    """The canonical identity for an imported entity.

    Three cases, in order: an identifier this exporter previously wrote into the
    file is reused; an identifier already in the mapping table is reused; and
    otherwise one is derived from the canonical path, so a second import of the
    same file lands on the same identifier.
    """
    existing = recovered or mapping.canonical(external_id)
    if existing:
        mapping.record(external_id, existing)
        return imported(existing, external_id, display_name=external_id)

    derived = derive(project_id, kind, path, taken=taken)
    mapping.record(external_id, derived.id)
    return imported(derived.id, external_id, path=derived.path, display_name=external_id)
