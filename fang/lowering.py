"""Lowering a typed interface connection to pin connections.

Spec: "Deterministic Interface Lowering to Pins", "Deterministic Pin
Assignment", "A Pin Choice Is A Recorded Decision", and "An Incomplete Lowering
Fails Explicitly".

The assignment is a pure function of the graph state and the part selection, so
the same design lowers identically every time. Where a choice existed it becomes
a decision entity; where none can be made the lowering fails whole.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Mapping, Sequence

from .diagnostics import (
    IFACE_MEMBERSHIP_DISAGREEMENT,
    IFACE_UNSATISFIABLE_SIGNAL,
    SourceLocation,
    error,
)
from .entities import Connection, ConnectionKind, Decision, Entity, Pin
from .interfaces import CATALOGUE, InterfacePort, InterfaceType
from .provenance import Provenance


@dataclass(frozen=True)
class PinChoice:
    """One side's pin for one signal, with the alternatives it was chosen over."""

    owner: str            # the module entity carrying the pin
    pin: str              # the vendor pin name
    alternatives: tuple[str, ...] = ()

    @property
    def was_a_choice(self) -> bool:
        return len(self.alternatives) > 0


@dataclass(frozen=True)
class SignalAssignment:
    """One signal, lowered to a pin on each side."""

    signal: str
    left: PinChoice
    right: PinChoice

    def as_dict(self) -> dict:
        return {
            "signal": self.signal,
            "left": {"owner": self.left.owner, "pin": self.left.pin},
            "right": {"owner": self.right.owner, "pin": self.right.pin},
        }


@dataclass(frozen=True)
class Lowering:
    """The complete result of lowering one interface connection.

    It is complete or it does not exist: a lowering that cannot satisfy a
    required signal raises rather than returning a partial mapping.
    """

    interface_connection: str        # the interface connection's entity id
    interface: str
    assignments: tuple[SignalAssignment, ...]
    path: str = ""                   # the connection's canonical semantic path

    def as_dict(self) -> dict:
        return {
            "interface_connection": self.interface_connection,
            "interface": self.interface,
            "assignments": [a.as_dict() for a in self.assignments],
        }


def interface_of(surface) -> InterfaceType:
    """The interface type behind a surface.

    An `InterfacePort` carries one directly; a stage-2 surface names a catalogue
    entry, so both lower through the same path.
    """
    if isinstance(surface, InterfacePort):
        return surface.interface
    return CATALOGUE.get(surface.surface_type)


def check_membership(left, right) -> None:
    """Two connected interfaces must share their required signal set."""
    left_required = set(interface_of(left).required_signals)
    right_required = set(interface_of(right).required_signals)

    # One wire to one wire is unambiguous however each side names its wire; only
    # a multi-wire connection needs the two sides to agree on membership.
    if len(left_required) == 1 and len(right_required) == 1:
        return

    if left_required != right_required:
        only_left = sorted(left_required - right_required)
        only_right = sorted(right_required - left_required)
        raise error(
            IFACE_MEMBERSHIP_DISAGREEMENT,
            f"{interface_of(left).name} and {interface_of(right).name} disagree on "
            f"membership: {only_left or 'nothing'} is required by one side and "
            f"{only_right or 'nothing'} by the other",
        )


def _choose(
    candidates: Sequence[str], taken: set[str], signal: str, side: str, owner: str
) -> tuple[str, tuple[str, ...]]:
    """Pick a pin in declared order, skipping any already used in this lowering.

    Declared order is the engineer's stated preference and is reproducible, so
    the assignment is both deterministic and the one that was asked for.
    """
    available = [pin for pin in candidates if pin not in taken]
    if not available:
        if candidates:
            raise error(
                IFACE_UNSATISFIABLE_SIGNAL,
                f"every candidate pin for {signal!r} on the {side} side ({owner}) "
                f"is already assigned: {', '.join(candidates)}",
            )
        raise error(
            IFACE_UNSATISFIABLE_SIGNAL,
            f"the required signal {signal!r} has no candidate pin on the {side} "
            f"side ({owner})",
        )
    chosen = available[0]
    alternatives = tuple(pin for pin in available[1:])
    return chosen, alternatives


def lower(
    left,
    right,
    *,
    connection_id: str,
    path: str = "",
) -> Lowering:
    """Lower one interface connection. Raises rather than partially mapping."""
    check_membership(left, right)
    interface = interface_of(left)

    left_owner = left.owner
    right_owner = right.owner
    left_map = _pin_map_of(left_owner)
    right_map = _pin_map_of(right_owner)

    taken_left: set[str] = set()
    taken_right: set[str] = set()
    assignments: list[SignalAssignment] = []

    # The interface's declared signal order, so the traversal is reproducible.
    for spec in interface.signals:
        left_candidates = (
            left_map.candidates(*left.pin_lookup(spec.name)) if left_map else ()
        )
        right_candidates = (
            right_map.candidates(*right.pin_lookup(spec.name)) if right_map else ()
        )

        if not spec.required and not (left_candidates and right_candidates):
            # An optional signal absent on either side is simply not lowered.
            continue

        left_pin, left_alternatives = _choose(
            left_candidates, taken_left, spec.name, "left", left_owner._entity_id
        )
        right_pin, right_alternatives = _choose(
            right_candidates, taken_right, spec.name, "right", right_owner._entity_id
        )
        taken_left.add(left_pin)
        taken_right.add(right_pin)

        assignments.append(
            SignalAssignment(
                spec.name,
                PinChoice(left_owner._entity_id, left_pin, left_alternatives),
                PinChoice(right_owner._entity_id, right_pin, right_alternatives),
            )
        )

    return Lowering(connection_id, interface.name, tuple(assignments), path)


def _pin_map_of(module):
    return getattr(module, "_pin_map", None)


def emit(
    lowering: Lowering,
    *,
    pin_ids: Mapping[tuple[str, str], str],
    derive_id,
    provenance: Provenance,
    source_location: SourceLocation | None = None,
) -> dict[str, Entity]:
    """Turn a lowering into first-class connectivity and decisions.

    Each pin connection carries provenance naming the interface connection it
    came from, so the lowering is re-derivable and auditable.
    """
    entities: dict[str, Entity] = {}

    for index, assignment in enumerate(lowering.assignments):
        left_pin_id = pin_ids[(assignment.left.owner, assignment.left.pin)]
        right_pin_id = pin_ids[(assignment.right.owner, assignment.right.pin)]

        # Derived from the connection's canonical path, not from its identifier:
        # an identifier is not a path segment and would not parse as one.
        base = lowering.path or lowering.interface_connection
        identity = derive_id("net", f"{base}.{assignment.signal}")
        connection = Connection(
            identity,
            connection_kind=CATALOGUE.get(lowering.interface).connection_kind,
            source=left_pin_id,
            target=right_pin_id,
            derived_from_interface=lowering.interface_connection,
            provenance=provenance,
            source_location=source_location,
        )
        entities[connection.id] = connection

        # A choice becomes a decision; a single candidate does not, because no
        # choice existed.
        for side, choice, pin_id in (
            ("left", assignment.left, left_pin_id),
            ("right", assignment.right, right_pin_id),
        ):
            if not choice.was_a_choice:
                continue
            decision_identity = derive_id(
                "decision", f"{base}.{assignment.signal}.{side}"
            )
            entities[decision_identity.id] = Decision(
                decision_identity,
                question=(
                    f"Which pin of {choice.owner} carries "
                    f"{lowering.interface}.{assignment.signal}?"
                ),
                choice=pin_id,
                rationale=(
                    "first candidate in the part's declared preference order that "
                    "was not already assigned within this lowering",
                ),
                alternatives_rejected=tuple(
                    {"pin": alternative, "reason": "a higher-preference candidate was available"}
                    for alternative in choice.alternatives
                ),
                provenance=provenance,
                source_location=source_location,
            )

    return entities
