"""Reducing two toolchains' outputs to the one thing they can be compared on.

A Fang build emits a KiCad netlist; an atopile build emits a `.kicad_pcb`. Their
designators, their net names, and their part identities are each toolchain's own
business — atopile picks a vendor part and Fang deliberately does not, and two
tools that both assign designators in their own deterministic order will not
assign the same ones. What a board *is*, and what both must therefore agree on,
is which instances become components and which pads are joined to which.

`Board` is that reduction: instance paths, and the partition of (instance, pad)
into nets. Everything else is dropped here rather than asserted on, so a
disagreement reported by this module is a disagreement about the design.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from fang.elaborate import elaborate
from fang.entities import Component, Pin
from fang.netlist import infer_nets
from fang.sexpr import Node, parse

#: A pad joined to nothing is not connectivity, and the two toolchains record it
#: differently: KiCad gives it net 0, and Fang gives it a net of its own.
MINIMUM_NET = 2


@dataclass(frozen=True)
class Board:
    """A board as the two toolchains can both state it."""

    #: Instance path (`top`, `mcu`) to the pads that instance carries.
    components: Mapping[str, frozenset[str]]
    #: Each net as the set of `(instance path, pad)` it joins.
    nets: frozenset[frozenset[tuple[str, str]]]

    def difference(self, other: "Board") -> list[str]:
        """What is not the same, in the words the reader needs. Empty is equal."""
        problems: list[str] = []

        missing = sorted(set(self.components) - set(other.components))
        extra = sorted(set(other.components) - set(self.components))
        if missing:
            problems.append(f"only in the first: {', '.join(missing)}")
        if extra:
            problems.append(f"only in the second: {', '.join(extra)}")

        for net in sorted(self.nets - other.nets, key=sorted):
            problems.append(f"net only in the first: {_render(net)}")
        for net in sorted(other.nets - self.nets, key=sorted):
            problems.append(f"net only in the second: {_render(net)}")
        return problems


def _render(net: frozenset[tuple[str, str]]) -> str:
    return "{" + ", ".join(f"{instance}.{pad}" for instance, pad in sorted(net)) + "}"


def _net_set(members: Mapping[str, set[tuple[str, str]]]) -> frozenset:
    return frozenset(
        frozenset(net) for net in members.values() if len(net) >= MINIMUM_NET
    )


# --------------------------------------------------------------------------
# The Fang side
# --------------------------------------------------------------------------


def from_fang(system, *, project_id: str = "PRJ-PARITY") -> Board:
    """Elaborate a Fang program and reduce it."""
    result = elaborate(system, project_id=project_id)
    if not result.ok:
        raise AssertionError([d.message for d in result.diagnostics])
    entities = result.snapshot.entities

    #: A component's instance path without the root, so `system.top` is `top`
    #: and matches what the other toolchain calls the same instance.
    paths = {
        entity.id: str(entity.identity.path).split(".", 1)[-1]
        for entity in entities.values()
        if isinstance(entity, Component)
    }
    pins = {
        pin.id: (paths[pin.owner], pin.number or pin.vendor_name)
        for pin in entities.values()
        if isinstance(pin, Pin) and pin.owner in paths
    }

    components: dict[str, set[str]] = {path: set() for path in paths.values()}
    for instance, pad in pins.values():
        components[instance].add(pad)

    nets = {
        index: {pins[member] for member in net if member in pins}
        for index, net in enumerate(infer_nets(entities))
    }
    return Board(
        components={path: frozenset(pads) for path, pads in components.items()},
        nets=_net_set(nets),
    )


# --------------------------------------------------------------------------
# The atopile side
# --------------------------------------------------------------------------


def from_kicad_pcb(path: Path) -> Board:
    """Read an atopile build's artifact and reduce it the same way.

    The instance path is read from the `atopile_address` property the build
    writes onto every footprint, which is the same name the Fang program gives
    the same instance. Nothing is matched by designator: the two toolchains
    number their parts in their own order, and neither is wrong.
    """
    board = parse(path.read_text())

    components: dict[str, frozenset[str]] = {}
    nets: dict[str, set[tuple[str, str]]] = {}

    for footprint in board.children("footprint"):
        instance = _property(footprint, "atopile_address")
        if instance is None:
            continue
        pads = set()
        for pad in footprint.children("pad"):
            name = pad.atoms()[0] if pad.atoms() else None
            if name is None:
                continue
            pads.add(name)
            net = pad.child("net")
            if net is None:
                continue
            code = net.atoms()[0]
            if code == "0":
                continue
            nets.setdefault(code, set()).add((instance, name))
        components[instance] = frozenset(pads)

    return Board(components=components, nets=_net_set(nets))


def _property(footprint: Node, name: str) -> str | None:
    for entry in footprint.children("property"):
        atoms = entry.atoms()
        if len(atoms) >= 2 and atoms[0] == name:
            return atoms[1]
    return None
