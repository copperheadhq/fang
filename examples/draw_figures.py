"""Draw the schematics of the textbook examples with copperhead's drafting engine.

    python examples/draw_figures.py [example ...]

Every example in a group named in `regenerate.FIGURES` (the op amp handbook's
and the JEE Advanced questions) has its schematic drawn here rather than by
fang. Copperhead is not a dependency of fang, so this is not part of
`examples/regenerate.py` and the test suite does not run it. It needs a
copperhead checkout (`COPPERHEAD_DIR`, default `~/copperhead`) with its
dependencies installed, `npx`, and `kicad-cli`.

For each example it writes `figure/` beside the example's `out/`:

    figure/schematic.intent.json   what copperhead was asked to draw
    figure/<name>.kicad_sch        the sheet it drew
    figure/schematic.svg           KiCad's render of the sheet, cut to the circuit

The intent is the circuit's own netlist, with each part given the KiCad
library symbol that draws it (`SYMBOLS` below). A sheet is written only if
KiCad reads back from it exactly the connections the circuit has: a drawing
that joined two nets, or dropped a pin, is refused rather than shipped.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parent
sys.path.insert(0, str(EXAMPLES))
sys.path.insert(0, str(EXAMPLES.parent))

from regenerate import FIGURES, PROJECT, _program, examples  # noqa: E402

from fang.cli import load_system  # noqa: E402
from fang.elaborate import elaborate  # noqa: E402
from fang.netlist import compile_netlist  # noqa: E402
from fang.sexpr import Node, parse  # noqa: E402

COPPERHEAD = Path(os.environ.get("COPPERHEAD_DIR", Path.home() / "copperhead"))

#: What draws each kind of part: a KiCad library symbol, and which of its pin
#: numbers each of the part's pins is. A kind is the designator prefix, or for
#: an op amp or a diode the part itself, since one prefix covers several.
SYMBOLS: dict[str, tuple[str, dict[str, str]]] = {
    "R": ("Device:R", {"1": "1", "2": "2"}),
    "RL": ("Device:R", {"1": "1", "2": "2"}),
    "RS": ("Device:R", {"1": "1", "2": "2"}),
    "C": ("Device:C", {"1": "1", "2": "2"}),
    "L": ("Device:L", {"1": "1", "2": "2"}),
    "RV": ("Device:R_Potentiometer", {"1": "1", "2": "2", "3": "3"}),
    # A cell names its terminals; a textbook battery numbers them, 1 positive.
    "V": ("Device:Battery_Cell", {"+": "1", "-": "2", "1": "1", "2": "2"}),
    "LP": ("Device:Lamp", {"1": "1", "2": "2"}),
    "M": ("Device:Ammeter_DC", {"1": "2", "2": "1"}),
    "SW": ("Switch:SW_SPST", {"1": "1", "2": "2"}),
    "TP": ("Connector:TestPoint", {"1": "1"}),
    "GND": ("power:GND", {"1": "1"}),
    # KiCad's generic op amp, not any one part: the handbook's are ideal.
    "OpAmp": ("Simulation_SPICE:OPAMP", {"IN+": "1", "IN-": "2", "OUT": "5"}),
    # TI's own fully differential amplifier; KiCad has no generic one.
    "DifferentialOpAmp": (
        "Amplifier_Difference:THS4521IDGK",
        {"IN+": "8", "IN-": "1", "OUT+": "4", "OUT-": "5"},
    ),
    "SignalDiode": ("Device:D", {"A": "2", "K": "1"}),
    "Zener": ("Device:D_Zener", {"A": "2", "K": "1"}),
}

#: The value printed under a part, where the graph's would say what the part
#: is modelled as rather than what it is.
VALUES = {
    "OpAmp": "OPAMP",
    "DifferentialOpAmp": "THS4521",
    "SignalDiode": "1N4148",
    "Zener": "Zener",
    "Ground": "GND",
    "GroundReference": "GND",
}


def _prefix(designator: str) -> str:
    return designator.rstrip("0123456789")


def _value(text: str) -> str:
    text = VALUES.get(text, text)
    for unit, short in ((" kOhm", "k"), (" MOhm", "M"), (" Ohm", "")):
        text = text.replace(unit, short)
    return text.replace(" ", "")


def intent(name: str) -> dict:
    """The circuit as copperhead's schematic intent."""
    result = elaborate(load_system(_program(name)), project_id=PROJECT)
    netlist = compile_netlist(result.snapshot, traits=result.traits)
    entities = result.snapshot.entities
    kind, called = {}, {}
    for c in netlist.components:
        prefix = _prefix(c.designator)
        kind[c.designator] = c.value if prefix in ("U", "D") else prefix
        called[c.designator] = entities[c.entity_id].identity.path.segments[-1].name.upper()

    parts = [
        {
            "ref": c.designator,
            "libId": SYMBOLS[kind[c.designator]][0],
            # A terminal is labelled with the name the program gives it.
            "value": called[c.designator] if kind[c.designator] == "TP" else _value(c.value),
            "group": "Circuit",
        }
        for c in netlist.components
    ]
    nets = []
    for net in netlist.nets:
        nodes = [(n.designator, n.pin) for n in net.nodes]
        ground = any(kind[d] == "GND" for d, _ in nodes)
        terminals = sorted(called[d] for d, _ in nodes if kind[d] == "TP")
        entry = {
            "name": "GND" if ground else (terminals[0] if terminals else net.name),
            "pins": [f"{d}.{SYMBOLS[kind[d]][1][p]}" for d, p in nodes],
        }
        if ground:
            entry["kind"] = "ground"
        nets.append(entry)
    # A fixed date, so the same circuit draws the same bytes on any day.
    return {"version": 1, "parts": parts, "nets": nets, "hints": {"date": "2026-01-01"}}


def _connections(netlist_text: str) -> set[frozenset[str]]:
    """Every net of two or more pins, as its pins. KiCad renames a power
    symbol to `#PWR…`, so those are left out; the ground net is still there."""
    found = set()

    def walk(node: Node):
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


def _wanted(drawn: dict) -> set[frozenset[str]]:
    power = {p["ref"] for p in drawn["parts"] if p["libId"].startswith("power:")}
    nets = (
        frozenset(pin for pin in net["pins"] if pin.split(".")[0] not in power)
        for net in drawn["nets"]
    )
    return {net for net in nets if len(net) > 1}


#: Room left around the drawing when the render is cut to it, in millimetres.
MARGIN = 2.54
#: How wide a character of KiCad's 1.27 mm stroke font is, near enough.
TEXT_WIDTH = 1.1


def _top_level(text: str) -> list[str]:
    """The sheet's top-level items, as text, each starting on its own line."""
    items, depth, start = [], 0, None
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
            if depth == 2:
                start = index
        elif char == ")":
            if depth == 2 and start is not None:
                items.append(text[start : index + 1])
            depth -= 1
    return items


def _render(sheet: Path, work: Path) -> str:
    """KiCad's render of the sheet with nothing but the circuit on it.

    The drawing sheet's frame and title block, the page colour, and the box
    copperhead draws around a group are left out: there is one group, so the
    box encloses everything and says nothing. The page is then cut down to the
    drawing, since KiCad renders the whole sheet it chose."""
    text = sheet.read_text()
    kept = [
        item for item in _top_level(text)
        if not item.startswith(("(rectangle", '(text "Circuit"'))
    ]
    bare = work / "bare" / sheet.name
    bare.parent.mkdir()
    bare.write_text("(kicad_sch\n\t" + "\n\t".join(kept) + "\n)\n")
    subprocess.run(
        ["kicad-cli", "sch", "export", "svg", "--exclude-drawing-sheet",
         "--no-background-color", "-o", str(work / "svg"), str(bare)],
        capture_output=True, check=True,
    )
    svg = (work / "svg" / f"{sheet.stem}.svg").read_text()

    # Every point placed on the page, outside the symbol library, bounds it,
    # and so does every piece of text, which runs on from the point it is
    # anchored at. Its length is estimated, generously, in both directions
    # along its axis: a little too much room costs less than a clipped label.
    points = []
    for item in kept:
        if item.startswith("(lib_symbols"):
            continue
        for x, y in re.findall(r"\((?:at|xy|start|end) (-?[\d.]+) (-?[\d.]+)", item):
            points.append((float(x), float(y)))
        for words, x, y, angle, rest in re.findall(
            r'\((?:label|global_label|hierarchical_label|property "[^"]*"|text) '
            r'"([^"]*)"[^()]*(?:\([^()]*\)[^()]*)*?\(at (-?[\d.]+) (-?[\d.]+) (\d+)\)'
            r"([^\n]*)",
            item,
        ):
            if "(hide yes)" in rest:
                continue
            reach = len(words) * TEXT_WIDTH + TEXT_WIDTH * 3
            x, y = float(x), float(y)
            if int(angle) % 180:
                points += [(x, y - reach), (x, y + reach)]
            else:
                points += [(x - reach, y), (x + reach, y)]
    left = min(x for x, _ in points) - MARGIN
    top = min(y for _, y in points) - MARGIN
    width = max(x for x, _ in points) + MARGIN - left
    height = max(y for _, y in points) + MARGIN - top
    return re.sub(
        r'width="[^"]*" height="[^"]*" viewBox="[^"]*"',
        f'width="{width:.4f}mm" height="{height:.4f}mm" '
        f'viewBox="{left:.4f} {top:.4f} {width:.4f} {height:.4f}"',
        svg,
        count=1,
    )


def draw(name: str) -> str:
    stem = Path(name).name
    figure = EXAMPLES / name / "figure"
    drawn = intent(name)
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        (work / "schematic.intent.json").write_text(json.dumps(drawn, indent=2) + "\n")
        drafted = subprocess.run(
            ["npx", "tsx", str(EXAMPLES / "draft_figure.mts"), str(COPPERHEAD), str(work), stem],
            cwd=COPPERHEAD, capture_output=True, text=True,
        )
        if drafted.returncode:
            return f"{name}: copperhead refused\n  " + drafted.stderr.strip().replace("\n", "\n  ")
        sheet = work / f"{stem}.kicad_sch"
        subprocess.run(
            ["kicad-cli", "sch", "export", "netlist", "-o", str(work / "back.net"), str(sheet)],
            capture_output=True, check=True,
        )
        back = _connections((work / "back.net").read_text())
        if back != _wanted(drawn):
            return f"{name}: the drawing does not have the circuit's connections; not written"
        render = _render(sheet, work)
        figure.mkdir(exist_ok=True)
        (figure / "schematic.intent.json").write_text(json.dumps(drawn, indent=2) + "\n")
        (figure / f"{stem}.kicad_sch").write_text(sheet.read_text())
        (figure / "schematic.svg").write_text(render)
    return f"{name}: drawn"


def main(argv: list[str]) -> int:
    names = [n for n in examples() if n.startswith(FIGURES)]
    if argv:
        names = [n for n in names if Path(n).name in argv or n in argv]
    failed = 0
    for name in names:
        line = draw(name)
        failed += not line.endswith(": drawn")
        print(line)
    print(f"{len(names) - failed} of {len(names)} drawn")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
