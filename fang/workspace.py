"""The project workspace.

Spec: "Workspace Persistence" and "The Workspace Layout".

Everything outside the cache is either canonical state or recorded evidence. The
cache is reconstructible: deleting it loses no engineering fact.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import SCHEMA_VERSION, __version__
from .entities import Entity
from .graph import Snapshot
from .importing import MappingTable
from .serialization import canonical_bytes, canonical_record_stream, read_record_stream
from .validation import check_schema_version

WORKSPACE_DIR = ".copperhead"
DESIGN_FILE = "design.jsonl"
MANIFEST_FILE = "manifest.json"
MAPPING_FILE = "mapping.json"
PLAN_FILE = "plan.json"
REPORT_FILE = "import-report.json"

#: Directories the workspace owns. Only `cache` may be deleted.
DIRECTORIES = ("sources", "evidence", "simulations", "views", "cache")


@dataclass(frozen=True)
class Manifest:
    """What produced this state, so a snapshot's producer is reconstructible."""

    schema_version: str
    revision_id: str
    compiler_version: str
    snapshot: str
    project_id: str
    lock_id: str = "unlocked"
    entity_count: int = 0

    def as_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "revision_id": self.revision_id,
            "compiler_version": self.compiler_version,
            "snapshot": self.snapshot,
            "project_id": self.project_id,
            "lock_id": self.lock_id,
            "entity_count": self.entity_count,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "Manifest":
        check_schema_version(payload["schema_version"])
        return cls(
            payload["schema_version"],
            payload["revision_id"],
            payload["compiler_version"],
            payload["snapshot"],
            payload["project_id"],
            payload.get("lock_id", "unlocked"),
            payload.get("entity_count", 0),
        )


class Workspace:
    """The directory a project's state lives in."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.dir = self.root / WORKSPACE_DIR

    # -- layout ------------------------------------------------------------

    def create(self) -> "Workspace":
        self.dir.mkdir(parents=True, exist_ok=True)
        for name in DIRECTORIES:
            (self.dir / name).mkdir(exist_ok=True)
        return self

    @property
    def exists(self) -> bool:
        return self.dir.is_dir()

    @property
    def design_path(self) -> Path:
        return self.dir / DESIGN_FILE

    @property
    def manifest_path(self) -> Path:
        return self.dir / MANIFEST_FILE

    @property
    def cache(self) -> Path:
        return self.dir / "cache"

    def clear_cache(self) -> None:
        """Safe by construction: nothing outside the cache is touched."""
        if self.cache.exists():
            shutil.rmtree(self.cache)
        self.cache.mkdir(parents=True, exist_ok=True)

    # -- writing -----------------------------------------------------------

    def write_snapshot(self, snapshot: Snapshot) -> Manifest:
        """Persist the design as the canonical record stream, plus a manifest."""
        self.create()
        self.design_path.write_bytes(canonical_record_stream(snapshot.records()))

        manifest = Manifest(
            snapshot.schema_version,
            snapshot.revision_id,
            snapshot.compiler_version,
            snapshot.hash,
            snapshot.project_id,
            snapshot.lock_id,
            len(snapshot.entities),
        )
        self.manifest_path.write_bytes(canonical_bytes(manifest.as_dict()))
        return manifest

    def write_mapping(self, mapping: MappingTable) -> None:
        (self.dir / MAPPING_FILE).write_bytes(canonical_bytes(mapping.as_dict()))

    def write_plan(self, plan) -> None:
        (self.dir / PLAN_FILE).write_bytes(canonical_bytes(plan.as_dict()))

    def write_import_report(self, report) -> None:
        (self.dir / REPORT_FILE).write_bytes(canonical_bytes(report.as_dict()))

    def write_artifact(self, relative: str, data: bytes) -> Path:
        path = self.dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    # -- reading -----------------------------------------------------------

    def read_manifest(self) -> Manifest:
        return Manifest.from_dict(json.loads(self.manifest_path.read_text()))

    def read_mapping(self) -> MappingTable:
        path = self.dir / MAPPING_FILE
        if not path.exists():
            return MappingTable()
        return MappingTable(json.loads(path.read_text()))

    def read_records(self) -> list[dict]:
        if not self.design_path.exists():
            return []
        return read_record_stream(self.design_path.read_bytes())

    def read_snapshot(self, entities: Mapping[str, Entity] | None = None) -> Snapshot:
        """Rebuild the snapshot.

        Entity records round-trip as data. Rehydrating them into typed entities
        needs the entity registry, so a caller that has the live entities passes
        them; otherwise the records are returned as the snapshot's payload for
        inspection.
        """
        manifest = self.read_manifest()
        return Snapshot(
            manifest.project_id,
            manifest.revision_id,
            dict(entities or {}),
            schema_version=manifest.schema_version,
            compiler_version=manifest.compiler_version,
            lock_id=manifest.lock_id,
        )

    def as_dict(self) -> dict:
        return {
            "root": str(self.root),
            "exists": self.exists,
            "entities": len(self.read_records()) if self.exists else 0,
        }


def find_workspace(start: Path | str = ".") -> Workspace | None:
    """Walk upward for a workspace, the way a version control tool would."""
    current = Path(start).resolve()
    for candidate in (current, *current.parents):
        if (candidate / WORKSPACE_DIR).is_dir():
            return Workspace(candidate)
    return None
