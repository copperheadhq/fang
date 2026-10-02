"""Schematic drafting by copperhead, as a second lowering of a snapshot.

Spec: "One canonical model" (a drafted sheet is a lowering leaving a snapshot,
never a store of its own) and "External Adapters Report Loss".

Fang's own schematic compiler places parts on a grid and joins them by label.
copperhead's drafting engine places and wires them: it reads a netlist intent
(`schematic.intent.json`: parts with the KiCad symbol each is drawn with, and
nets as lists of `REF.PIN`) and computes every coordinate itself. This module
writes that intent from a snapshot and runs `copperhead draft schematic` across
a process boundary, the way `schematic.KicadRenderer` runs `kicad-cli`.

The intent is a projection like the netlist it is read from, so it is a
function of the snapshot and of the options `compile_intent` is called with,
and nothing else. There is one lowering: `fang schematic --drafter copperhead`,
`examples/regenerate.py` and `examples/draw_figures.py` all call
`compile_intent`, and where they draw differently it is because they pass
different options, never because they lower differently. What copperhead cannot
draw is reported as a loss rather than dropped: a part with no symbol to draw
it with, a part with a pin its symbol has no place for, and a net that reaches
fewer than two drawn pins.
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


@dataclass(frozen=True)
class Symbol:
    """A KiCad library symbol a part is drawn with, and where its pins land."""

    #: The symbol, as `library:name`.
    library: str
    #: Each of the part's pin names to the symbol's pin number. None means the
    #: part numbers its pins as the symbol does, and its own numbers are used.
    pins: Mapping[str, str] | None = None
    #: What is printed under the part where its value is only the name of its
    #: type, which says what the part is modelled as rather than what it is.
    value: str | None = None


#: KiCad's diodes number the cathode 1 and the anode 2; a fang diode numbers
#: its anode 1, so a diode drawn by number would be drawn backwards.
_DIODE = {"A": "2", "K": "1"}

#: Designator prefix to the symbol a part is drawn with when neither the part
#: nor its type names one. A prefix is a convention shared across programs, so
#: only one that conventionally means a single kind of device is here: `M` is
#: left out, since KiCad draws a motor with it as well as a meter.
SYMBOL_OF_PREFIX: Mapping[str, Symbol] = {
    "C": Symbol("Device:C"),
    "D": Symbol("Device:D", _DIODE),
    "DS": Symbol("Device:LED", _DIODE),
    "F": Symbol("Device:Fuse"),
    "L": Symbol("Device:L"),
    "LED": Symbol("Device:LED", _DIODE),
    "R": Symbol("Device:R"),
    "RL": Symbol("Device:R"),
    "RS": Symbol("Device:R"),
    "RV": Symbol("Device:R_Potentiometer"),
    "SW": Symbol("Switch:SW_SPST"),
    "TP": Symbol("Connector:TestPoint"),
    # A cell names its terminals or numbers them; either way 1 is positive.
    "V": Symbol("Device:Battery_Cell"),
    "Y": Symbol("Device:Crystal"),
}

#: A part's type to the symbol it is drawn with, for a type one prefix does
#: not pick out: `U` covers every integrated part, and a zener is a `D`. The
#: types are the ones the examples' textbook figures model.
SYMBOL_OF_PART: Mapping[str, Symbol] = {
    # KiCad's generic op amp, not any one part: an ideal op amp is no vendor's.
    "OpAmp": Symbol(
        "Simulation_SPICE:OPAMP", {"IN+": "1", "IN-": "2", "OUT": "5"}, "OPAMP"
    ),
    # TI's own fully differential amplifier; KiCad has no generic one.
    "DifferentialOpAmp": Symbol(
        "Amplifier_Difference:THS4521IDGK",
        {"IN+": "8", "IN-": "1", "OUT+": "4", "OUT-": "5"},
        "THS4521",
    ),
    "SignalDiode": Symbol("Device:D", _DIODE, "1N4148"),
    "Zener": Symbol("Device:D_Zener", _DIODE),
    # A meter's pin 1 is the one current enters by, which KiCad marks + and
    # numbers 2.
    "Meter": Symbol("Device:Ammeter_DC", {"1": "2", "2": "1"}),
    "Lamp": Symbol("Device:Lamp"),
}

#: What a ground marker, a part whose every pin is a ground pin, is drawn
#: with. copperhead draws a power symbol at each pin of a ground net rather
#: than the part itself, so the marker never appears on the sheet as one.
GROUND_SYMBOL = Symbol("power:GND", value="GND")

#: The symbol a terminal is drawn with, for `terminal_names`.
TERMINAL = "Connector:TestPoint"


@dataclass(frozen=True)
class Intent:
    """copperhead's netlist intent for one snapshot, and what it leaves out."""

    document: Mapping
    losses: tuple[str, ...]

    def text(self) -> str:
        return json.dumps(self.document, indent=2, ensure_ascii=False) + "\n"


def _prefix(designator: str) -> str:
    return designator.rstrip("0123456789")


def symbol_of(
    component: Component,
    designator: str,
    *,
    libsource: str | None = None,
    marker: bool = False,
) -> Symbol | None:
    """The symbol a part is drawn with, or None where nothing names one.

    In order: the symbol the part names itself (`symbol = "library:name"`,
    which reaches the netlist as its libsource), numbered by the part's own
    pins; the one its type is drawn with; KiCad's ground symbol for a ground
    marker; the one its designator's prefix names.
    """
    if libsource:
        return Symbol(libsource)
    if component.part in SYMBOL_OF_PART:
        return SYMBOL_OF_PART[component.part]
    if marker:
        return GROUND_SYMBOL
    return SYMBOL_OF_PREFIX.get(_prefix(designator))


def short_value(value: str) -> str:
    """A value as a schematic prints it: `10k` for `10 kOhm`, `1uF` for `1 uF`."""
    for unit, short in ((" kOhm", "k"), (" MOhm", "M"), (" Ohm", "")):
        value = value.replace(unit, short)
    return value.replace(" ", "")


def compile_intent(
    snapshot,
    *,
    traits=None,
    netlist: Netlist | None = None,
    group: str = "fang",
    ground: str | None = None,
    terminal_names: bool = False,
    short_values: bool = False,
    date: str = "",
) -> Intent:
    """Lower a snapshot to copperhead's netlist intent.

    Every part goes into the one group named `group`. A part whose every pin
    is a ground pin marks a node rather than adding a device to it: it is
    drawn with KiCad's ground symbol unless it names its own, and its net is
    declared a ground net.

    The rest of the options say how the sheet is labelled, and each is the
    same for every caller unless that caller passes it:

    `ground` is the name the ground net is drawn with; None keeps the name
    the netlist gives it. `terminal_names` labels each terminal (a part drawn
    as a test point) with the name its part has in the program, upper-cased,
    and names the net it is on after it, the first in order where several
    meet; a ground net named by `ground` keeps that name. `short_values`
    prints each value as a schematic does, `10k` rather than `10 kOhm`. `date`
    is the title block's: it is part of the intent so the same intent drafts
    the same bytes, and a snapshot carries no issue date, so none is invented
    unless the caller names one.
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
    terminals: dict[str, str] = {}
    endpoint: dict[tuple[str, str], str] = {}
    parts = []
    for item in netlist.components:
        component = components[item.entity_id]
        owned = sorted(pins.get(item.entity_id, []), key=lambda pin: pin.vendor_name)
        marker = bool(owned) and all(pin.role == "ground" for pin in owned)
        symbol = symbol_of(
            component, item.designator, libsource=item.libsource, marker=marker
        )
        if symbol is None:
            losses.append(
                f"{item.designator} is not drawn: no KiCad symbol is named for it, "
                f'its type {component.part or "(none)"} is drawn with none, and a '
                f'"{_prefix(item.designator)}" prefix names none; '
                'give its part a symbol = "library:name"'
            )
            continue
        if symbol.pins is not None:
            unplaced = [pin.vendor_name for pin in owned if pin.vendor_name not in symbol.pins]
            if unplaced:
                losses.append(
                    f"{item.designator} is not drawn: {symbol.library} has no pin for its "
                    f"{', '.join(unplaced)}; give its part a symbol = \"library:name\" "
                    "whose pins its own numbers are"
                )
                continue
        for pin in owned:
            if symbol.pins is not None:
                number = symbol.pins[pin.vendor_name]
            else:
                number = pin.number or pin.vendor_name
            endpoint[(item.designator, pin.vendor_name)] = f"{item.designator}.{number}"
        if marker:
            markers.add(item.designator)

        value = item.value
        if symbol.value is not None and value == component.part:
            value = symbol.value
        if short_values:
            value = short_value(value)
        if terminal_names and symbol.library == TERMINAL:
            path = component.identity.path
            value = terminals[item.designator] = (
                path.leaf.name.upper() if path is not None else item.designator
            )
        parts.append(
            {"ref": item.designator, "libId": symbol.library, "value": value, "group": group}
        )

    nets = []
    renamed: set[str] = set()
    for net in netlist.nets:
        endpoints = sorted(
            endpoint[(node.designator, node.pin)]
            for node in net.nodes
            if (node.designator, node.pin) in endpoint
        )
        if len(endpoints) < 2:
            losses.append(
                f"net {net.name} is not drawn: it reaches "
                f"{len(endpoints)} drawn pin(s), and copperhead draws a net between two or more"
            )
            continue
        grounded = any(node.designator in markers for node in net.nodes)
        named = sorted(
            terminals[node.designator] for node in net.nodes if node.designator in terminals
        )
        if grounded and ground is not None:
            name = ground
        elif named:
            name = named[0]
        else:
            name = net.name
        if name != net.name:
            renamed.add(name)
        entry: dict = {"name": name, "pins": endpoints}
        if grounded:
            entry["kind"] = "ground"
        nets.append(entry)

    # A name given here must not land on a second net: KiCad joins two nets
    # drawn under one name, and the drawing would no longer be the netlist.
    given = [net["name"] for net in nets]
    clashes = sorted(name for name in renamed if given.count(name) > 1)
    if clashes:
        raise ValueError(
            f"the intent would draw more than one net as {', '.join(clashes)}, "
            "and KiCad joins nets drawn under one name"
        )

    document = {
        "version": INTENT_VERSION,
        "parts": parts,
        "nets": nets,
        "hints": {"date": date},
    }
    return Intent(document=document, losses=tuple(losses))


class DrafterUnavailable(Exception):
    """copperhead is not installed. Reported, never worked around."""


class DraftRefused(Exception):
    """copperhead read the intent and would not draw it, or drew something
    whose connections are not the intent's; the message says which."""


def drawn_connections(netlist_text: str) -> set[frozenset[str]]:
    """Every net of two or more pins in a KiCad netlist, as `REF.PIN` strings.

    KiCad names a power symbol `#PWR...`; those are left out, and the ground
    net they sit on is still there through the pins it joins.
    """
    from .sexpr import Node, parse

    found: set[frozenset[str]] = set()

    def walk(node: Node) -> None:
        for item in node.items:
            if not isinstance(item, Node):
                continue
            if item.head != "net":
                walk(item)
                continue
            pins = set()
            for child in item.items:
                if isinstance(child, Node) and child.head == "node":
                    fields = {
                        f.head: f.items[1].value
                        for f in child.items
                        if isinstance(f, Node) and f.head in ("ref", "pin")
                    }
                    if not fields["ref"].startswith("#"):
                        pins.add(f"{fields['ref']}.{fields['pin']}")
            if len(pins) > 1:
                found.add(frozenset(pins))

    walk(parse(netlist_text))
    return found


def intended_connections(intent: Intent) -> set[frozenset[str]]:
    """The nets an intent asks for, each as the set of its `REF.PIN` strings.

    A part drawn with a power symbol is left out, as `drawn_connections` leaves
    it out of the sheet: copperhead draws a power symbol of its own at each pin
    of the net instead, and KiCad names those `#PWR...`. What stays is every
    pin the net joins, so a drawing that loses one still fails the comparison.
    """
    power = {
        part["ref"] for part in intent.document["parts"] if part["libId"].startswith("power:")
    }
    nets = (
        frozenset(pin for pin in net["pins"] if pin.split(".", 1)[0] not in power)
        for net in intent.document["nets"]
    )
    return {net for net in nets if len(net) > 1}


@dataclass
class CopperheadDrafter:
    """copperhead, reached across a process boundary.

    The draft is made in a workspace of its own — a copperhead repository with
    nothing in it but its configuration and the intent — so the tool never sees
    the project. copperhead vendors the KiCad symbols it draws with into that
    workspace; the sheet it writes embeds them, so the file stands alone.
    """

    executable: str = "copperhead"
    #: Reads each draft's connections back, so a sheet is returned only if
    #: KiCad finds in it exactly the nets the intent asked for.
    reader: str = "kicad-cli"

    def available(self) -> bool:
        return shutil.which(self.executable) is not None and shutil.which(self.reader) is not None

    def _command(self) -> str:
        # The path `which` found, not the bare name: on Windows npm installs
        # copperhead as a .cmd shim, which only its full path starts.
        return shutil.which(self.executable) or self.executable

    def _run(self, arguments: list[str], **options) -> subprocess.CompletedProcess:
        """A run across the boundary, with its failures as refusals, not tracebacks."""
        try:
            return subprocess.run(
                arguments, capture_output=True, text=True, encoding="utf-8",
                errors="replace", **options,
            )
        except subprocess.TimeoutExpired as exc:
            raise DraftRefused(f"{arguments[0]} did not finish within {exc.timeout} s") from exc
        except OSError as exc:
            raise DraftRefused(f"{arguments[0]} could not be started: {exc}") from exc

    def version(self) -> str:
        if shutil.which(self.executable) is None:
            raise DrafterUnavailable(f"{self.executable} is not installed")
        completed = self._run([self._command(), "--version"], timeout=60)
        return (completed.stdout or completed.stderr).strip()

    def draft(self, intent: Intent, *, workspace, name: str = "schematic") -> str:
        """Draft the intent, and return the sheet only if its connections are
        the intent's: a drawing that joins two nets, or lands a pin on another
        net's wire, is refused rather than returned."""
        missing = [tool for tool in (self.executable, self.reader) if shutil.which(tool) is None]
        if missing:
            raise DrafterUnavailable(
                f"{' and '.join(missing)} {'is' if len(missing) == 1 else 'are'} not "
                "installed; the intent compiled but no sheet was drafted from it, "
                "and none is returned unread"
            )
        # Absolute, because copperhead is run from inside it and named it too.
        workspace = Path(workspace).resolve()
        (workspace / ".copperhead").mkdir(parents=True, exist_ok=True)
        (workspace / ".copperhead" / "config.json").write_text(
            json.dumps({"schematic": f"{name}.kicad_sch", "docs": "docs"}) + "\n",
            encoding="utf-8",
        )
        (workspace / "schematic.intent.json").write_text(intent.text(), encoding="utf-8")
        completed = self._run(
            [self._command(), "--repo", str(workspace), "--plain", "draft", "schematic"],
            cwd=workspace,
            timeout=300,
        )
        drafted = workspace / f"{name}.kicad_sch"
        if completed.returncode != 0 or not drafted.is_file():
            raise DraftRefused(
                f"{self.executable} did not draft the schematic: "
                f"{(completed.stderr or completed.stdout).strip()}"
            )

        back = workspace / "read-back.net"
        read = self._run(
            [shutil.which(self.reader) or self.reader, "sch", "export", "netlist",
             "-o", str(back), str(drafted)],
            cwd=workspace,
            timeout=120,
        )
        if read.returncode != 0 or not back.is_file():
            raise DraftRefused(
                f"{self.reader} could not read the drafted sheet back: "
                f"{(read.stderr or read.stdout).strip()}"
            )
        found = drawn_connections(back.read_text(encoding="utf-8"))
        wanted = intended_connections(intent)
        if found != wanted:
            extra = sorted(", ".join(sorted(net)) for net in found - wanted)
            lacking = sorted(", ".join(sorted(net)) for net in wanted - found)
            detail = "; ".join(
                part for part in (
                    f"it draws {' | '.join(extra)}" if extra else "",
                    f"where the intent has {' | '.join(lacking)}" if lacking else "",
                ) if part
            )
            raise DraftRefused(
                f"{self.executable} drafted a sheet whose connections are not the "
                f"intent's: {detail}"
            )
        return drafted.read_text(encoding="utf-8")
