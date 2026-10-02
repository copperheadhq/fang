"""Schematic drafting by copperhead, as a second lowering of a snapshot.

Spec: "One canonical model" — a drafted sheet is a lowering leaving a
snapshot, never a store of its own — and "External Adapters Report Loss".

Fang's own schematic compiler places parts on a grid and joins them by label.
copperhead's drafting engine places and wires them: it reads a netlist intent
(`schematic.intent.json` — parts with the KiCad symbol each is drawn with, and
nets as lists of `REF.PIN`) and computes every coordinate itself. This module
writes that intent from a snapshot and runs `copperhead draft schematic` across
a process boundary, the way `schematic.KicadRenderer` runs `kicad-cli`.

The intent is a projection like the netlist it is read from, so it is a
function of the snapshot and nothing else. What copperhead cannot draw is
reported as a loss rather than dropped: a part with no symbol to draw it with,
and a net that reaches fewer than two drawn pins.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .entities import Component, Pin
from .netlist import Netlist, compile_netlist

#: The intent format this writes; copperhead refuses a version it does not know.
INTENT_VERSION = 1

#: Designator prefix to the KiCad symbol copperhead draws a part with when the
#: part names none of its own. Only symbols whose pin numbers are the ones a
#: part with that prefix conventionally has: a symbol whose numbering differed
#: would move a net onto the wrong pin, and copperhead maps endpoints by number.
LIBRARY_OF_PREFIX: Mapping[str, str] = {
    "C": "Device:C",
    "D": "Device:D",
    "F": "Device:Fuse",
    "L": "Device:L",
    "LED": "Device:LED",
    "R": "Device:R",
    "TP": "Connector:TestPoint",
    "V": "Device:Battery_Cell",
    "Y": "Device:Crystal",
}


@dataclass(frozen=True)
class Intent:
    """copperhead's netlist intent for one snapshot, and what it leaves out."""

    document: Mapping
    losses: tuple[str, ...]

    def text(self) -> str:
        return json.dumps(self.document, indent=2, ensure_ascii=False) + "\n"


def _prefix(designator: str) -> str:
    return designator.rstrip("0123456789")


def compile_intent(
    snapshot,
    *,
    traits=None,
    netlist: Netlist | None = None,
    group: str = "fang",
) -> Intent:
    """Lower a snapshot to copperhead's netlist intent.

    A part whose every pin is a ground pin marks a node rather than adding a
    device to it, so it is not drawn as a part: its net is declared a ground
    net and copperhead draws the ground symbol there instead. Every other part
    goes into the one group named `group`.
    """
    netlist = netlist or compile_netlist(snapshot, traits=traits)
    pins: dict[str, list[Pin]] = {}
    for entity in snapshot.entities.values():
        if isinstance(entity, Pin):
            pins.setdefault(entity.owner, []).append(entity)
    components = {
        entity.id: entity
        for entity in snapshot.entities.values()
        if isinstance(entity, Component)
    }

    losses: list[str] = []
    markers: set[str] = set()
    drawn: set[str] = set()
    number: dict[tuple[str, str], str] = {}
    parts = []
    for component in netlist.components:
        owned = pins.get(component.entity_id, [])
        for pin in owned:
            number[(component.designator, pin.vendor_name)] = pin.number or pin.vendor_name
        if owned and all(pin.role == "ground" for pin in owned):
            markers.add(component.designator)
            continue
        entity = components.get(component.entity_id)
        library = component.libsource or LIBRARY_OF_PREFIX.get(_prefix(component.designator))
        if library is None:
            losses.append(
                f"{component.designator} is not drawn: no KiCad symbol is named for it, "
                f'and a "{_prefix(component.designator)}" prefix names none; '
                'give its part a symbol = "library:name"'
            )
            continue
        drawn.add(component.designator)
        parts.append(
            {
                "ref": component.designator,
                "libId": library,
                "value": component.value or (entity.name if entity else component.designator),
                "group": group,
            }
        )

    nets = []
    for net in netlist.nets:
        ground = any(node.designator in markers for node in net.nodes)
        endpoints = sorted(
            f"{node.designator}.{number.get((node.designator, node.pin), node.pin)}"
            for node in net.nodes
            if node.designator in drawn
        )
        if len(endpoints) < 2:
            losses.append(
                f"net {net.name} is not drawn: it reaches "
                f"{len(endpoints)} drawn pin(s), and copperhead draws a net between two or more"
            )
            continue
        entry: dict = {"name": net.name, "pins": endpoints}
        if ground:
            entry["kind"] = "ground"
        nets.append(entry)

    document = {
        "version": INTENT_VERSION,
        "parts": parts,
        "nets": nets,
        # The title block's date is part of the intent so the same intent
        # drafts the same bytes; a snapshot carries no issue date, so none is
        # invented for it.
        "hints": {"date": ""},
    }
    return Intent(document=document, losses=tuple(losses))


class DrafterUnavailable(Exception):
    """copperhead is not installed. Reported, never worked around."""


class DraftRefused(Exception):
    """copperhead read the intent and would not draw it; its findings say why."""


@dataclass
class CopperheadDrafter:
    """copperhead, reached across a process boundary.

    The draft is made in a workspace of its own — a copperhead repository with
    nothing in it but its configuration and the intent — so the tool never sees
    the project. copperhead vendors the KiCad symbols it draws with into that
    workspace; the sheet it writes embeds them, so the file stands alone.
    """

    executable: str = "copperhead"

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def version(self) -> str:
        if not self.available():
            raise DrafterUnavailable(f"{self.executable} is not installed")
        completed = subprocess.run(
            [self.executable, "--version"], capture_output=True, text=True, timeout=60
        )
        return (completed.stdout or completed.stderr).strip()

    def draft(self, intent: Intent, *, workspace, name: str = "schematic") -> str:
        if not self.available():
            raise DrafterUnavailable(
                f"{self.executable} is not installed; the intent compiled but "
                "no sheet was drafted from it"
            )
        # Absolute, because copperhead is run from inside it and named it too.
        workspace = Path(workspace).resolve()
        (workspace / ".copperhead").mkdir(parents=True, exist_ok=True)
        (workspace / ".copperhead" / "config.json").write_text(
            json.dumps({"schematic": f"{name}.kicad_sch", "docs": "docs"}) + "\n",
            encoding="utf-8",
        )
        (workspace / "schematic.intent.json").write_text(intent.text(), encoding="utf-8")
        completed = subprocess.run(
            [self.executable, "--repo", str(workspace), "--plain", "draft", "schematic"],
            capture_output=True,
            text=True,
            cwd=workspace,
            timeout=300,
        )
        drafted = workspace / f"{name}.kicad_sch"
        if completed.returncode != 0 or not drafted.is_file():
            raise DraftRefused(
                f"{self.executable} did not draft the schematic: "
                f"{(completed.stderr or completed.stdout).strip()}"
            )
        return drafted.read_text(encoding="utf-8")
