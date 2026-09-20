"""Schematic as a compiler target.

Spec: "One canonical model" — the schematic compiler is one of the lowerings
leaving a snapshot — and "A projection names the snapshot it came from".

The symbols are drawn here rather than copied out of an installed KiCad. A
projection that embedded a library's text would change when that library
changed and the snapshot did not, and a schematic is a projection like any
other: it depends on the snapshot and on nothing else. What it does not do is
route. Connectivity is carried by a global label on every pin, because a net is
a fact in the graph and a wire path is not.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import uuid
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Mapping, Sequence

from .entities import Component, Pin
from .netlist import Netlist, compile_netlist

#: The schematic file format this writes. KiCad reads a version it knows; it
#: refuses one it does not, which is the behaviour we want from a version field.
FORMAT_VERSION = "20250114"

#: The namespace derived identifiers in a schematic hang off. A UUID in this
#: file names a thing inside one projection, so it is derived from the snapshot
#: rather than drawn at random: the same snapshot gives the same file.
NAMESPACE = uuid.UUID("6f0b4b8e-6a4d-5c1e-9b2a-2f7c1d4e8a30")

#: Millimetres. A schematic is on a 1.27 mm grid, and everything below is a
#: multiple of it so KiCad's own editing snaps to the same points.
GRID = Decimal("1.27")
STUB = Decimal("5.08")
COLUMN = Decimal("83.82")
ROW = Decimal("25.4")
ORIGIN_X = Decimal("45.72")
ORIGIN_Y = Decimal("38.1")
COLUMNS = 3
MARGIN = Decimal("10.16")

#: The drawing sheet's own geometry, in millimetres, and the reason the sheet
#: is cut larger than the drawing: KiCad's frame is drawn this far in from the
#: page edge, the band of reference letters is that wide again inside it, and
#: the title block fills the frame's bottom-right corner. Reserve all three or
#: the frame is drawn over the circuit.
SHEET_MARGIN = Decimal("10")
SHEET_BAND = Decimal("2")
TITLE_WIDTH = Decimal("108")
TITLE_HEIGHT = Decimal("32")
BORDER = SHEET_MARGIN + SHEET_BAND + MARGIN

#: A stroke-font character is about this wide at the 1.27 mm text size, and a
#: label adds its pointed end on top. Estimating is enough: the number decides
#: how big the sheet is, not where anything sits on it.
CHARACTER = Decimal("1.016")
LABEL_TAIL = Decimal("3.81")


def _mm(value: Decimal | int | str) -> str:
    """A coordinate as KiCad writes them: no trailing zeros, no exponent."""
    decimal = Decimal(str(value)).normalize()
    if decimal == 0:
        return "0"
    text = format(decimal, "f")
    return text


def _uuid(*key: str) -> str:
    return str(uuid.uuid5(NAMESPACE, "|".join(key)))


# --------------------------------------------------------------------------
# Symbols
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SymbolPin:
    """One terminal. `x`, `y` is the connection point, in symbol coordinates.

    A symbol's y axis points up and a sheet's points down, which is the one
    conversion everything below has to get right.
    """

    number: str
    x: str
    y: str
    angle: int
    length: str
    electrical: str = "passive"
    name: str = "~"
    node: str = ""

    @property
    def key(self) -> str:
        """The name this terminal has in the netlist, which may not be its number."""
        return self.node or self.number

    def at(self, rotation: int) -> tuple[Decimal, Decimal]:
        """The connection point as a sheet offset from the symbol's origin.

        A symbol's y axis points up and a sheet's points down. That flip, and
        the instance's rotation, are the whole of the transform.
        """
        x, y = Decimal(self.x), Decimal(self.y)
        x, y = {
            0: (x, y),
            90: (-y, x),
            180: (-x, -y),
            270: (y, -x),
        }[rotation % 360]
        return x, -y

    def sheet_angle(self, rotation: int) -> int:
        """The direction the pin body runs, once the symbol is placed."""
        return (self.angle + rotation) % 360

    def stub(self, rotation: int) -> tuple[Decimal, Decimal]:
        """Where the label goes: one stub out from the connection point.

        The body runs from the connection point along the pin's angle, so the
        stub runs the other way, into free space.
        """
        x, y = self.at(rotation)
        away = {0: (-1, 0), 90: (0, 1), 180: (1, 0), 270: (0, -1)}[
            self.sheet_angle(rotation)
        ]
        return x + STUB * away[0], y + STUB * away[1]

    def label_angle(self, rotation: int) -> int:
        """The rotation that makes a label read away from the symbol."""
        return (self.sheet_angle(rotation) + 180) % 360

    def label_justify(self, rotation: int) -> str:
        """Which side of its anchor the label's text sits on.

        A label's rotation turns the arrow; the text still reads left to right,
        so the side it occupies has to be said as well or every label lands back
        on top of the part it names.
        """
        return "left" if self.label_angle(rotation) in (0, 90) else "right"


@dataclass(frozen=True)
class Symbol:
    """A drawn symbol: graphics, pins, and where its two texts sit."""

    name: str
    pins: tuple[SymbolPin, ...]
    graphics: tuple[str, ...] = ()
    #: How the symbol sits on the sheet. A two-terminal part lies on its side,
    #: so its labels read across the page instead of down it.
    rotation: int = 0
    #: Where the reference and the value sit, as a sheet offset in millimetres.
    #: Sheet rather than symbol coordinates, so rotating the part does not
    #: rotate its text with it.
    reference_offset: tuple[str, str] = ("0", "-5.08")
    value_offset: tuple[str, str] = ("0", "5.08")
    hide_pin_numbers: bool = True
    hide_pin_names: bool = True


def _rectangle(x1: str, y1: str, x2: str, y2: str) -> str:
    return (
        f"(rectangle (start {x1} {y1}) (end {x2} {y2})"
        f" (stroke (width 0.254) (type default)) (fill (type none)))"
    )


def _polyline(*points: tuple[str, str]) -> str:
    pts = " ".join(f"(xy {x} {y})" for x, y in points)
    return (
        f"(polyline (pts {pts})"
        f" (stroke (width 0.254) (type default)) (fill (type none)))"
    )


#: A resistor, a cell and a ground marker, drawn to the dimensions KiCad's own
#: library uses, so a schematic fang writes sits on the same grid as one drawn
#: by hand and a part dropped in beside it lines up.
RESISTOR = Symbol(
    name="Resistor",
    graphics=(_rectangle("-1.016", "-2.54", "1.016", "2.54"),),
    pins=(
        SymbolPin("1", "0", "3.81", 270, "1.27"),
        SymbolPin("2", "0", "-3.81", 90, "1.27"),
    ),
    rotation=90,
)

CELL = Symbol(
    name="Cell",
    graphics=(
        _rectangle("-2.286", "1.778", "2.286", "1.524"),
        _rectangle("-1.524", "1.016", "1.524", "0.508"),
        _polyline(("0", "1.778"), ("0", "2.54")),
        _polyline(("0", "0.762"), ("0", "0")),
        _polyline(("0.762", "3.048"), ("1.778", "3.048")),
        _polyline(("1.27", "3.556"), ("1.27", "2.54")),
    ),
    pins=(
        SymbolPin("1", "0", "5.08", 270, "2.54"),
        SymbolPin("2", "0", "-2.54", 90, "2.54"),
    ),
    rotation=90,
    reference_offset=("0", "-6.35"),
    value_offset=("0", "6.35"),
)

GROUND = Symbol(
    name="Ground",
    graphics=(
        _polyline(
            ("0", "0"),
            ("0", "-1.27"),
            ("1.27", "-1.27"),
            ("0", "-2.54"),
            ("-1.27", "-1.27"),
            ("0", "-1.27"),
        ),
    ),
    pins=(SymbolPin("1", "0", "0", 270, "0", "power_in"),),
    reference_offset=("11.43", "-1.27"),
    value_offset=("11.43", "1.27"),
)

#: Designator prefix to drawn symbol. A prefix with no entry is drawn as a box
#: with its own pins on it, which is what a schematic does for a part nobody
#: has a symbol for.
SYMBOL_OF_PREFIX: Mapping[str, Symbol] = {
    "R": RESISTOR,
    "V": CELL,
    "GND": GROUND,
}


def _box(designator: str, pins: Sequence[tuple[str, str]]) -> Symbol:
    """A rectangle with the part's own pins on it, half a side each.

    Nothing here is invented: the pin numbers and names are the ones the graph
    carries, and their order down the side is the order the graph gives them.
    """
    half = (len(pins) + 1) // 2
    left, right = pins[:half], pins[half:]
    height = Decimal(max(half, len(right), 1) + 1) * GRID * 2
    top = height / 2
    drawn = [
        _rectangle(_mm(-Decimal("10.16")), _mm(-top), _mm(Decimal("10.16")), _mm(top))
    ]
    made: list[SymbolPin] = []
    for index, (number, name) in enumerate(left):
        y = top - GRID * 2 * Decimal(index + 1)
        made.append(
            SymbolPin(number, _mm(Decimal("-12.7")), _mm(y), 0, "2.54", "passive", name, name)
        )
    for index, (number, name) in enumerate(right):
        y = top - GRID * 2 * Decimal(index + 1)
        made.append(
            SymbolPin(number, _mm(Decimal("12.7")), _mm(y), 180, "2.54", "passive", name, name)
        )
    return Symbol(
        name=f"Box_{designator}",
        graphics=tuple(drawn),
        pins=tuple(made),
        reference_offset=("0", _mm(-top - GRID * 2)),
        value_offset=("0", _mm(top + GRID * 2)),
        hide_pin_numbers=False,
        hide_pin_names=False,
    )


# --------------------------------------------------------------------------
# The lowering
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Placement:
    """One component on the sheet: which symbol, and where."""

    designator: str
    value: str
    symbol: Symbol
    x: Decimal
    y: Decimal
    entity_id: str


def _pins_of(snapshot, component_id: str) -> tuple[tuple[str, str], ...]:
    pins = [
        entity
        for entity in snapshot.entities.values()
        if isinstance(entity, Pin) and entity.owner == component_id
    ]
    ordered = sorted(pins, key=lambda p: (p.number or "", p.vendor_name))
    return tuple((pin.number or pin.vendor_name, pin.vendor_name) for pin in ordered)


def _symbol_for(snapshot, component: Component, designator: str) -> Symbol:
    prefix = "".join(c for c in designator if not c.isdigit())
    drawn = SYMBOL_OF_PREFIX.get(prefix)
    if drawn is not None:
        return drawn
    return _box(designator, _pins_of(snapshot, component.id))


def place(snapshot, netlist: Netlist) -> tuple[Placement, ...]:
    """Lay the parts out in designator order, left to right then down.

    The order is the netlist's, which is the graph's, so the sheet is a
    function of the design rather than of the order anything was written.
    """
    by_id = {
        entity.id: entity
        for entity in snapshot.entities.values()
        if isinstance(entity, Component)
    }
    placements = []
    for index, component in enumerate(netlist.components):
        symbol = _symbol_for(snapshot, by_id[component.entity_id], component.designator)
        placements.append(
            Placement(
                designator=component.designator,
                value=component.value,
                symbol=symbol,
                x=ORIGIN_X + COLUMN * Decimal(index % COLUMNS),
                y=ORIGIN_Y + ROW * Decimal(index // COLUMNS),
                entity_id=component.entity_id,
            )
        )
    return tuple(placements)


@dataclass(frozen=True)
class Terminal:
    """One pin of one placed symbol, with everywhere it reaches on the sheet."""

    designator: str
    pin: SymbolPin
    connect: tuple[Decimal, Decimal]
    anchor: tuple[Decimal, Decimal]
    angle: int
    justify: str
    net: str | None

    def extent(self) -> tuple[Decimal, Decimal, Decimal, Decimal]:
        """The box the wire and the label together occupy."""
        x, y = self.anchor
        width = Decimal(len(self.net or "")) * CHARACTER + LABEL_TAIL
        if self.angle == 0:
            box = (x, y - GRID, x + width, y + GRID)
        elif self.angle == 180:
            box = (x - width, y - GRID, x, y + GRID)
        elif self.angle == 90:
            box = (x - GRID, y - width, x + GRID, y)
        else:
            box = (x - GRID, y, x + GRID, y + width)
        return (
            min(box[0], self.connect[0]),
            min(box[1], self.connect[1]),
            max(box[2], self.connect[0]),
            max(box[3], self.connect[1]),
        )


def terminals(placement: Placement, netlist: Netlist) -> tuple[Terminal, ...]:
    """Every terminal of one placed symbol, in the symbol's own pin order."""
    symbol = placement.symbol
    made = []
    for pin in symbol.pins:
        net = netlist.net_of(placement.designator, pin.key)
        offset = pin.at(symbol.rotation)
        stub = pin.stub(symbol.rotation)
        made.append(
            Terminal(
                designator=placement.designator,
                pin=pin,
                connect=(placement.x + offset[0], placement.y + offset[1]),
                anchor=(placement.x + stub[0], placement.y + stub[1]),
                angle=pin.label_angle(symbol.rotation),
                justify=pin.label_justify(symbol.rotation),
                net=None if net is None else net.name,
            )
        )
    return tuple(made)


def _extent(placements, wired) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """The box the whole sheet occupies, texts included.

    The sheet is then cut to it. A picture of eleven parts on a fixed A4 page
    is mostly empty page, and the empty part is not the design.
    """
    boxes = []
    for placement in placements:
        symbol = placement.symbol
        for name, (dx, dy) in (
            (placement.designator, symbol.reference_offset),
            (placement.value, symbol.value_offset),
        ):
            half = Decimal(len(name)) * CHARACTER / 2
            x, y = placement.x + Decimal(dx), placement.y + Decimal(dy)
            boxes.append((x - half, y - GRID, x + half, y + GRID))
    boxes += [terminal.extent() for terminal in wired]
    if not boxes:
        return (Decimal(0), Decimal(0), Decimal(0), Decimal(0))
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def _lib_symbol(symbol: Symbol, indent: str) -> list[str]:
    lines = [f'{indent}(symbol "fang:{symbol.name}"']
    inner = indent + "\t"
    lines.append(f"{inner}(pin_numbers (hide {'yes' if symbol.hide_pin_numbers else 'no'}))")
    lines.append(f"{inner}(pin_names (offset 0) (hide {'yes' if symbol.hide_pin_names else 'no'}))")
    lines.append(f"{inner}(exclude_from_sim no)")
    lines.append(f"{inner}(in_bom yes)")
    lines.append(f"{inner}(on_board yes)")
    for name in ("Reference", "Value"):
        lines.append(
            f'{inner}(property "{name}" "{symbol.name}" (at 0 0 0) '
            f"(effects (font (size 1.27 1.27))))"
        )
    lines.append(f'{inner}(symbol "{symbol.name}_0_1"')
    for graphic in symbol.graphics:
        lines.append(f"{inner}\t{graphic}")
    lines.append(f"{inner})")
    lines.append(f'{inner}(symbol "{symbol.name}_1_1"')
    for pin in symbol.pins:
        lines.append(
            f"{inner}\t(pin {pin.electrical} line (at {pin.x} {pin.y} {pin.angle}) "
            f"(length {pin.length})"
        )
        lines.append(f'{inner}\t\t(name "{pin.name}" (effects (font (size 1.27 1.27))))')
        lines.append(f'{inner}\t\t(number "{pin.number}" (effects (font (size 1.27 1.27))))')
        lines.append(f"{inner}\t)")
    lines.append(f"{inner})")
    lines.append(f"{indent})")
    return lines


def compile_schematic(
    snapshot,
    *,
    traits=None,
    netlist: Netlist | None = None,
    title: str = "fang",
) -> str:
    """Lower a snapshot to a KiCad schematic.

    The file names the snapshot it was compiled from, in the title block,
    because a projection that cannot say what it came from is a second place
    facts live. The project is the comment the rendered sheet shows and the
    hash the one below it: the hash covers provenance, which records the path
    the program was read from, so it differs between checkouts and belongs in
    the file rather than drawn into the picture.
    """
    netlist = netlist or compile_netlist(snapshot, traits=traits)
    placements = place(snapshot, netlist)
    wired = [
        terminal
        for placement in placements
        for terminal in terminals(placement, netlist)
    ]

    # Cut the sheet to the drawing and to the sheet furniture that surrounds
    # it, then move the drawing onto it: the frame and the title block take
    # the border and the strip along the bottom, and the circuit gets the rest.
    left, top, right, bottom = _extent(placements, wired)
    shift_x = BORDER - left
    shift_y = BORDER - top
    width = max(right - left, TITLE_WIDTH) + BORDER * 2
    height = bottom - top + TITLE_HEIGHT + BORDER * 2
    root = _uuid("sheet", snapshot.project_id, title)

    lines = [
        "(kicad_sch",
        f"\t(version {FORMAT_VERSION})",
        '\t(generator "fang")',
        '\t(generator_version "9.0")',
        f'\t(uuid "{root}")',
        f'\t(paper "User" {_mm(width)} {_mm(height)})',
        "\t(title_block",
        f'\t\t(title "{title}")',
        f'\t\t(comment 1 "project {snapshot.project_id}")',
        f'\t\t(comment 2 "snapshot {snapshot.hash}")',
        "\t)",
        "\t(lib_symbols",
    ]

    drawn: dict[str, Symbol] = {}
    for placement in placements:
        drawn.setdefault(placement.symbol.name, placement.symbol)
    for name in sorted(drawn):
        lines += _lib_symbol(drawn[name], "\t\t")
    lines.append("\t)")

    for placement in placements:
        symbol = placement.symbol
        lines.append("\t(symbol")
        lines.append(f'\t\t(lib_id "fang:{symbol.name}")')
        lines.append(
            f"\t\t(at {_mm(placement.x + shift_x)} {_mm(placement.y + shift_y)} "
            f"{symbol.rotation})"
        )
        lines.append("\t\t(unit 1)")
        lines.append("\t\t(exclude_from_sim no)")
        lines.append("\t\t(in_bom yes)")
        lines.append("\t\t(on_board yes)")
        lines.append("\t\t(dnp no)")
        lines.append(f'\t\t(uuid "{_uuid("symbol", placement.entity_id)}")')
        for name, value, (dx, dy) in (
            ("Reference", placement.designator, symbol.reference_offset),
            ("Value", placement.value, symbol.value_offset),
        ):
            at_x = placement.x + shift_x + Decimal(dx)
            at_y = placement.y + shift_y + Decimal(dy)
            lines.append(
                f'\t\t(property "{name}" "{value}" '
                f"(at {_mm(at_x)} {_mm(at_y)} {(360 - symbol.rotation) % 360}) "
                f"(effects (font (size 1.27 1.27))))"
            )
        for pin in symbol.pins:
            lines.append(
                f'\t\t(pin "{pin.number}" '
                f'(uuid "{_uuid("pin", placement.entity_id, pin.number)}"))'
            )
        lines.append("\t\t(instances")
        lines.append(f'\t\t\t(project "{title}"')
        lines.append(
            f'\t\t\t\t(path "/{root}" (reference "{placement.designator}") (unit 1))'
        )
        lines.append("\t\t\t)")
        lines.append("\t\t)")
        lines.append("\t)")

    for terminal in wired:
        key = (terminal.designator, terminal.pin.number)
        lines.append(
            f"\t(wire (pts "
            f"(xy {_mm(terminal.connect[0] + shift_x)} {_mm(terminal.connect[1] + shift_y)}) "
            f"(xy {_mm(terminal.anchor[0] + shift_x)} {_mm(terminal.anchor[1] + shift_y)})) "
            f'(stroke (width 0) (type default)) (uuid "{_uuid("wire", *key)}"))'
        )

    for terminal in wired:
        if terminal.net is None:
            continue
        key = (terminal.designator, terminal.pin.number)
        lines.append(
            f'\t(global_label "{terminal.net}" (shape passive) '
            f"(at {_mm(terminal.anchor[0] + shift_x)} "
            f"{_mm(terminal.anchor[1] + shift_y)} {terminal.angle}) "
            f"(effects (font (size 1.27 1.27)) (justify {terminal.justify})) "
            f'(uuid "{_uuid("label", *key)}"))'
        )

    lines.append('\t(sheet_instances (path "/" (page "1")))')
    lines.append("\t(embedded_fonts no)")
    lines.append(")")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


class RendererUnavailable(Exception):
    """KiCad is not installed. Reported, never worked around."""


#: The drawing sheet the render is made with: the frame, the band of reference
#: letters, and the title block, laid out where KiCad's own default sheet lays
#: them. It is written here for the same reason the symbols are drawn here —
#: a render that read the installed KiCad's sheet would change when that KiCad
#: changed and the snapshot did not. KiCad's default prints its own version in
#: the corner of the block, which is exactly the kind of drift this avoids.
#: The geometry is the one `compile_schematic` reserves room for: `SHEET_MARGIN`
#: to the frame, `SHEET_BAND` more to the reference letters, and a title block
#: `TITLE_WIDTH` by `TITLE_HEIGHT` in the corner they make.
DRAWING_SHEET = """(kicad_wks
	(version 20220228)
	(generator "fang")
	(setup
		(textsize 1.5 1.5)
		(linewidth 0.15)
		(textlinewidth 0.15)
		(left_margin 10)
		(right_margin 10)
		(top_margin 10)
		(bottom_margin 10)
	)
	(rect (name "frame") (start 0 0 ltcorner) (end 0 0 rbcorner) (repeat 2) (incrx 2) (incry 2))
	(line (name "tick") (start 50 2 ltcorner) (end 50 0 ltcorner) (repeat 30) (incrx 50))
	(tbtext "1" (name "ref") (pos 25 1 ltcorner) (font (size 1.3 1.3)) (repeat 100) (incrx 50))
	(line (name "tick") (start 50 2 lbcorner) (end 50 0 lbcorner) (repeat 30) (incrx 50))
	(tbtext "1" (name "ref") (pos 25 1 lbcorner) (font (size 1.3 1.3)) (repeat 100) (incrx 50))
	(line (name "tick") (start 2 50 ltcorner) (end 0 50 ltcorner) (repeat 30) (incry 50))
	(tbtext "A" (name "ref") (pos 1 25 ltcorner) (font (size 1.3 1.3)) (repeat 100) (incry 50))
	(line (name "tick") (start 2 50 rtcorner) (end 0 50 rtcorner) (repeat 30) (incry 50))
	(tbtext "A" (name "ref") (pos 1 25 rtcorner) (font (size 1.3 1.3)) (repeat 100) (incry 50))
	(rect (name "block") (start 110 34) (end 2 2))
	(line (start 110 5.5) (end 2 5.5))
	(line (start 110 8.5) (end 2 8.5))
	(line (start 110 12.5) (end 2 12.5))
	(line (start 110 18.5) (end 2 18.5))
	(tbtext "Title: ${TITLE}" (pos 109 10.7) (font bold (size 2 2)) (maxlen 100))
	(tbtext "File: ${FILENAME}" (pos 109 14.3) (maxlen 100))
	(tbtext "Sheet: ${SHEETPATH}" (pos 109 17) (maxlen 100))
	(tbtext "Date: ${ISSUE_DATE}" (pos 87 6.9) (maxlen 60))
	(tbtext "Rev: ${REVISION}" (pos 24 6.9) (font bold) (maxlen 20))
	(tbtext "Size: ${PAPER}" (pos 109 6.9) (maxlen 40))
	(tbtext "Id: ${#}/${##}" (pos 24 4.1) (maxlen 20))
	(tbtext "fang" (pos 109 4.1) (maxlen 40))
	(tbtext "${COMMENT1}" (pos 109 20) (maxlen 100))
)
"""


#: The one line in KiCad's SVG that follows the clock rather than the design.
#: Everything else it writes is a function of the sheet.
_STAMPED = re.compile(r"^<title>SVG Image created as .*</title>$", re.MULTILINE)


@dataclass
class KicadRenderer:
    """KiCad, reached across a process boundary.

    The schematic is written into a workspace of its own, beside the drawing
    sheet it is rendered with, and `kicad-cli` is run against that copy, so
    the tool never sees the project and never reaches for a sheet of its own.
    What comes back is the ordinary KiCad picture — theme background, frame,
    reference letters, title block — with its timestamp line replaced: a
    projection that changed on every run would not be a projection of the
    snapshot.
    """

    executable: str = "kicad-cli"

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def version(self) -> str:
        if not self.available():
            raise RendererUnavailable(f"{self.executable} is not installed")
        completed = subprocess.run(
            [self.executable, "version"], capture_output=True, text=True, timeout=60
        )
        return (completed.stdout or completed.stderr).strip().splitlines()[0]

    def to_svg(self, schematic: str, *, workspace, name: str = "schematic") -> str:
        if not self.available():
            raise RendererUnavailable(
                f"{self.executable} is not installed; the schematic compiled but "
                "no render was made and no picture is fabricated"
            )
        workspace = Path(workspace)
        workspace.mkdir(parents=True, exist_ok=True)
        source = workspace / f"{name}.kicad_sch"
        source.write_text(schematic, encoding="utf-8")
        sheet = workspace / "fang.kicad_wks"
        sheet.write_text(DRAWING_SHEET, encoding="utf-8")
        completed = subprocess.run(
            [
                self.executable,
                "sch",
                "export",
                "svg",
                "--drawing-sheet",
                str(sheet),
                "-o",
                str(workspace),
                str(source),
            ],
            capture_output=True,
            text=True,
            cwd=workspace,
            timeout=120,
        )
        rendered = workspace / f"{name}.svg"
        if completed.returncode != 0 or not rendered.is_file():
            raise RendererUnavailable(
                f"{self.executable} did not render the schematic: "
                f"{(completed.stderr or completed.stdout).strip()}"
            )
        return _STAMPED.sub(
            f"<title>{name}.svg</title>", rendered.read_text(encoding="utf-8")
        )
