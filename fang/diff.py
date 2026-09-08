"""Semantic diff.

Spec: "Semantic Diff Classification". A change that alters only coordinates or
presentation is separable from one that alters electrical meaning, and a
preserved-identity rename is reported as a rename rather than as an addition and
a removal.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

from .entities import Entity


class ChangeClass(Enum):
    COMPONENT_ADDED = "component_added"
    COMPONENT_REMOVED = "component_removed"
    COMPONENT_CHANGED = "component_changed"
    CONNECTION_ADDED = "connection_added"
    CONNECTION_REMOVED = "connection_removed"
    PARAMETER_CHANGED = "parameter_changed"
    INTERFACE_CHANGED = "interface_changed"
    PIN_ASSIGNMENT_CHANGED = "pin_assignment_changed"
    DOMAIN_CHANGED = "domain_changed"
    TOPOLOGY_CHANGED = "topology_intent_changed"
    MODEL_CHANGED = "model_or_trait_changed"
    REQUIREMENT_CHANGED = "requirement_changed"
    DECISION_CHANGED = "decision_changed"
    EVIDENCE_CHANGED = "evidence_changed"
    VERIFICATION_STATUS_CHANGED = "verification_status_changed"
    CONSTRAINT_CHANGED = "constraint_changed"
    PHYSICAL_CHANGED = "physical_changed"
    MANUFACTURING_CHANGED = "manufacturing_data_changed"
    RENAME = "rename"
    PRESENTATION_CHANGED = "presentation_changed"
    ENTITY_ADDED = "entity_added"
    ENTITY_REMOVED = "entity_removed"


#: Fields that carry presentation only. A change confined to these is a
#: presentation change and never an electrical one.
PRESENTATION_FIELDS = frozenset({"display_name", "placement_seed", "position", "geometry"})

#: Which change classes alter electrical meaning.
ELECTRICAL_CLASSES = frozenset(
    {
        ChangeClass.COMPONENT_ADDED,
        ChangeClass.COMPONENT_REMOVED,
        ChangeClass.COMPONENT_CHANGED,
        ChangeClass.CONNECTION_ADDED,
        ChangeClass.CONNECTION_REMOVED,
        ChangeClass.PARAMETER_CHANGED,
        ChangeClass.INTERFACE_CHANGED,
        ChangeClass.PIN_ASSIGNMENT_CHANGED,
        ChangeClass.DOMAIN_CHANGED,
        ChangeClass.TOPOLOGY_CHANGED,
        ChangeClass.CONSTRAINT_CHANGED,
    }
)

_KIND_TO_CHANGED = {
    "component": ChangeClass.COMPONENT_CHANGED,
    "interface": ChangeClass.INTERFACE_CHANGED,
    "port": ChangeClass.PIN_ASSIGNMENT_CHANGED,
    "pin": ChangeClass.PIN_ASSIGNMENT_CHANGED,
    "domain": ChangeClass.DOMAIN_CHANGED,
    "model": ChangeClass.MODEL_CHANGED,
    "requirement": ChangeClass.REQUIREMENT_CHANGED,
    "decision": ChangeClass.DECISION_CHANGED,
    "evidence": ChangeClass.EVIDENCE_CHANGED,
    "constraint": ChangeClass.CONSTRAINT_CHANGED,
    "board": ChangeClass.PHYSICAL_CHANGED,
    "region": ChangeClass.PHYSICAL_CHANGED,
}

_KIND_TO_ADDED = {
    "component": ChangeClass.COMPONENT_ADDED,
    "connection": ChangeClass.CONNECTION_ADDED,
}

_KIND_TO_REMOVED = {
    "component": ChangeClass.COMPONENT_REMOVED,
    "connection": ChangeClass.CONNECTION_REMOVED,
}


@dataclass(frozen=True)
class Change:
    """One classified change."""

    type: ChangeClass
    subject: str
    before: Any = None
    after: Any = None
    impact: tuple[str, ...] = ()

    @property
    def electrical(self) -> bool:
        return self.type in ELECTRICAL_CLASSES

    @property
    def presentation(self) -> bool:
        return self.type is ChangeClass.PRESENTATION_CHANGED

    def as_dict(self) -> dict:
        out: dict = {"type": self.type.value, "subject": self.subject}
        if self.before is not None:
            out["before"] = self.before
        if self.after is not None:
            out["after"] = self.after
        if self.impact:
            out["impact"] = sorted(self.impact)
        return out


@dataclass(frozen=True)
class Diff:
    changes: tuple[Change, ...] = ()

    @property
    def electrical(self) -> tuple[Change, ...]:
        return tuple(c for c in self.changes if c.electrical)

    @property
    def presentation_only(self) -> tuple[Change, ...]:
        return tuple(c for c in self.changes if c.presentation)

    @property
    def invalidated(self) -> tuple[str, ...]:
        """Everything any change in this diff invalidates."""
        return tuple(sorted({ref for change in self.changes for ref in change.impact}))

    def as_list(self) -> list[dict]:
        return [c.as_dict() for c in sorted(self.changes, key=lambda c: (c.subject, c.type.value))]

    def __len__(self) -> int:
        return len(self.changes)

    def __iter__(self):
        return iter(self.changes)


def _identity_key(entity: Entity) -> str | None:
    """What survives a rename: the derived uuid, or an explicit key."""
    if entity.identity.uuid is not None:
        return f"uuid:{entity.identity.uuid}"
    if entity.identity.key is not None:
        return f"key:{entity.identity.key}"
    return None


def _impact(entity_id: str, entities: Mapping[str, Entity]) -> tuple[str, ...]:
    """What a change to this entity invalidates.

    Names the calculations, requirements, and verifications that depend on the
    changed entity, walking the graph rather than guessing.
    """
    from .constraints import Constraint

    impacted: set[str] = set()
    for other in entities.values():
        if other.id == entity_id:
            continue
        if entity_id in other.references():
            if other.kind in ("calculation", "verification", "requirement"):
                impacted.add(other.id)
            elif isinstance(other, Constraint):
                impacted.add(other.id)
                if other.source:
                    impacted.add(other.source)
    return tuple(sorted(impacted))


def diff(before: Mapping[str, Entity], after: Mapping[str, Entity]) -> Diff:
    """Classify the changes between two entity sets."""
    changes: list[Change] = []

    before_ids, after_ids = set(before), set(after)

    # Rename detection first, so a preserved identity is never reported as an
    # addition together with a removal.
    removed_keys = {
        _identity_key(before[i]): i for i in before_ids - after_ids if _identity_key(before[i])
    }
    added_keys = {
        _identity_key(after[i]): i for i in after_ids - before_ids if _identity_key(after[i])
    }
    renamed_before, renamed_after = set(), set()
    for key, old_id in sorted(removed_keys.items()):
        new_id = added_keys.get(key)
        if new_id is None:
            continue
        renamed_before.add(old_id)
        renamed_after.add(new_id)
        changes.append(
            Change(
                ChangeClass.RENAME,
                new_id,
                before=before[old_id].identity.display_name or old_id,
                after=after[new_id].identity.display_name or new_id,
                impact=_impact(new_id, after),
            )
        )

    for entity_id in sorted(after_ids - before_ids - renamed_after):
        entity = after[entity_id]
        changes.append(
            Change(
                _KIND_TO_ADDED.get(entity.kind, ChangeClass.ENTITY_ADDED),
                entity_id,
                after=entity.kind,
                impact=_impact(entity_id, after),
            )
        )

    for entity_id in sorted(before_ids - after_ids - renamed_before):
        entity = before[entity_id]
        changes.append(
            Change(
                _KIND_TO_REMOVED.get(entity.kind, ChangeClass.ENTITY_REMOVED),
                entity_id,
                before=entity.kind,
                impact=_impact(entity_id, before),
            )
        )

    for entity_id in sorted(before_ids & after_ids):
        changes.extend(_compare(before[entity_id], after[entity_id], after))

    return Diff(tuple(changes))


def _compare(old: Entity, new: Entity, entities: Mapping[str, Entity]) -> list[Change]:
    changes: list[Change] = []

    # Parameters, one change per parameter, so a diff names what moved.
    for name in sorted(set(old.parameters) | set(new.parameters)):
        was, now = old.parameters.get(name), new.parameters.get(name)
        if was == now:
            continue
        changes.append(
            Change(
                ChangeClass.PARAMETER_CHANGED,
                f"{new.id}.{name}",
                before=str(was.quantity) if was is not None and getattr(was, "quantity", None) else None,
                after=str(now.quantity) if now is not None and getattr(now, "quantity", None) else None,
                impact=_impact(new.id, entities),
            )
        )

    old_dict, new_dict = old.as_dict(), new.as_dict()
    changed_fields = {
        key
        for key in set(old_dict) | set(new_dict)
        if old_dict.get(key) != new_dict.get(key)
    } - {"parameters", "provenance", "identity"}

    # A display-name change with identity intact is a rename, not a removal.
    if old.identity.display_name != new.identity.display_name and old.id == new.id:
        changes.append(
            Change(
                ChangeClass.RENAME,
                new.id,
                before=old.identity.display_name,
                after=new.identity.display_name,
                impact=_impact(new.id, entities),
            )
        )

    presentation_only = changed_fields and changed_fields <= PRESENTATION_FIELDS
    if presentation_only:
        changes.append(
            Change(ChangeClass.PRESENTATION_CHANGED, new.id, after=sorted(changed_fields))
        )
        return changes

    if "verification" in changed_fields:
        changes.append(
            Change(
                ChangeClass.VERIFICATION_STATUS_CHANGED,
                new.id,
                before=old_dict.get("verification", {}).get("status"),
                after=new_dict.get("verification", {}).get("status"),
                impact=_impact(new.id, entities),
            )
        )
        changed_fields.discard("verification")

    substantive = changed_fields - PRESENTATION_FIELDS
    if substantive:
        changes.append(
            Change(
                _KIND_TO_CHANGED.get(new.kind, ChangeClass.ENTITY_ADDED)
                if new.kind in _KIND_TO_CHANGED
                else ChangeClass.PARAMETER_CHANGED,
                new.id,
                before=sorted(substantive),
                after=sorted(substantive),
                impact=_impact(new.id, entities),
            )
        )

    return changes
