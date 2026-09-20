"""Spec: One canonical model (the schematic compiler is a lowering) and
A projection names the snapshot it came from."""

from decimal import Decimal

import pytest

from fang.elaborate import elaborate
from fang.interfaces import Pin, PinMap
from fang.lang import Electrical, Ohm, Parameter, Part, System, V, kOhm, uF
from fang.netlist import compile_netlist
from fang.parts import Capacitor, Resistor, TwoPin
from fang.schematic import (
    KicadRenderer,
    RendererUnavailable,
    SHEET_BAND,
    SHEET_MARGIN,
    SYMBOL_OF_PREFIX,
    TITLE_HEIGHT,
    TITLE_WIDTH,
    compile_schematic,
    place,
    terminals,
)
from fang.sexpr import Atom, Node, parse

PROJECT = "PRJ-SCHEMATIC"

#: The parts of the file that sit on the page, as opposed to the symbol
#: library above them, whose coordinates are a symbol's own.
ON_THE_PAGE = {"symbol", "wire", "global_label"}


def _paper(schematic: str) -> tuple[Decimal, Decimal]:
    paper = next(line for line in schematic.splitlines() if "(paper" in line)
    width, height = paper.strip().rstrip(")").split()[2:]
    return Decimal(width), Decimal(height)


def _drawn(schematic: str) -> list[tuple[Decimal, Decimal]]:
    """Every point the compiled sheet puts something at."""

    def points(node: Node):
        if node.head in ("at", "xy"):
            x, y = node.items[1:3]
            yield Decimal(str(x)), Decimal(str(y))
        for item in node.items:
            if isinstance(item, Node):
                yield from points(item)

    root = parse(schematic)
    return [
        point
        for item in root.items
        if isinstance(item, Node) and item.head in ON_THE_PAGE
        for point in points(item)
    ]


class Source(TwoPin):
    designator_prefix = "V"
    voltage = Parameter("V")


class Marker(Part):
    designator_prefix = "GND"

    node = Electrical()
    PIN1 = Pin("1", role="ground", number="1")
    pinmap = PinMap({"node.line": "1"})


class Sensor(Part):
    """A part with no drawn symbol: it is the generated box's subject."""

    designator_prefix = "U"

    supply = Electrical()
    out = Electrical()
    VDD = Pin("VDD", role="power", number="1")
    OUT = Pin("OUT", role="analog", number="2")
    pinmap = PinMap({"supply.line": "VDD", "out.line": "OUT"})


class Divider(System):
    top = Resistor(resistance=10 * kOhm, package="R_0603")
    bottom = Resistor(resistance=4.7 * kOhm, package="R_0603")
    cap = Capacitor(capacitance=100 * uF, package="C_0805")
    cell = Source(voltage=5 * V, package="Battery")
    reference = Marker(package="GND")
    sensor = Sensor(package="SOT-23")

    def architecture(self):
        self.top.p2 >> self.bottom.p1
        self.bottom.p1 >> self.cap.p1
        self.bottom.p2 >> self.cap.p2
        self.cell.p1 >> self.top.p1
        self.cell.p2 >> self.reference.node
        self.sensor.supply >> self.top.p1
        self.sensor.out >> self.bottom.p1


@pytest.fixture
def built():
    result = elaborate(Divider, project_id=PROJECT)
    assert result.ok, [d.message for d in result.diagnostics]
    return result


@pytest.fixture
def schematic(built):
    return compile_schematic(built.snapshot, traits=built.traits, title="divider")


# -- the file ---------------------------------------------------------------


def test_the_schematic_names_the_snapshot_it_came_from(built, schematic):
    assert built.snapshot.hash in schematic
    assert built.snapshot.project_id in schematic


def test_the_schematic_is_well_formed_s_expressions(schematic):
    root = parse(schematic)
    assert root.head == "kicad_sch"
    heads = {item.head for item in root.items if isinstance(item, Node)}
    assert {"lib_symbols", "symbol", "wire", "global_label"} <= heads


def test_compilation_is_byte_identical_for_unchanged_input(built):
    first = compile_schematic(built.snapshot, traits=built.traits, title="divider")
    second = compile_schematic(built.snapshot, traits=built.traits, title="divider")
    assert first == second


def test_every_part_reaches_the_sheet(built, schematic):
    netlist = compile_netlist(built.snapshot, traits=built.traits)
    for component in netlist.components:
        assert f'"{component.designator}"' in schematic


def test_a_part_carries_its_value_onto_the_sheet(schematic):
    assert '"Value" "10 kOhm"' in schematic
    assert '"Value" "5 V"' in schematic


# -- geometry ---------------------------------------------------------------


def test_a_two_terminal_part_lies_on_its_side(built):
    """Its labels then read across the page rather than down it."""
    netlist = compile_netlist(built.snapshot, traits=built.traits)
    placed = {p.designator: p for p in place(built.snapshot, netlist)}
    assert placed["R1"].symbol.rotation == 90
    assert placed["GND1"].symbol.rotation == 0


def test_a_pin_is_placed_by_the_symbol_axis_flip(built):
    """A symbol's y axis points up and a sheet's points down."""
    netlist = compile_netlist(built.snapshot, traits=built.traits)
    placed = {p.designator: p for p in place(built.snapshot, netlist)}
    resistor = placed["R1"]
    one, two = terminals(resistor, netlist)
    # Rotated a quarter turn, pin 1 is to the left of the body and pin 2 right.
    assert one.connect[0] < resistor.x < two.connect[0]
    assert one.connect[1] == two.connect[1] == resistor.y
    # And each label sits one stub further out than the pin it names.
    assert one.anchor[0] < one.connect[0]
    assert two.anchor[0] > two.connect[0]


def test_a_label_reads_away_from_the_part_it_names(built):
    netlist = compile_netlist(built.snapshot, traits=built.traits)
    placed = {p.designator: p for p in place(built.snapshot, netlist)}
    one, two = terminals(placed["R1"], netlist)
    assert (one.angle, one.justify) == (180, "right")
    assert (two.angle, two.justify) == (0, "left")


def test_every_terminal_carries_the_net_it_is_on(built):
    netlist = compile_netlist(built.snapshot, traits=built.traits)
    for placement in place(built.snapshot, netlist):
        for terminal in terminals(placement, netlist):
            net = netlist.net_of(terminal.designator, terminal.pin.key)
            assert terminal.net == (None if net is None else net.name)


def test_the_sheet_is_cut_to_its_drawing(schematic):
    """A fixed page would be mostly empty page, and that is not the design."""
    assert 0 < _paper(schematic)[0] < 297
    assert 0 < _paper(schematic)[1] < 210


def test_the_sheet_leaves_the_frame_and_the_title_block_their_room(schematic):
    """The sheet furniture is drawn on this page too. Cut the page to hold it
    or KiCad draws the frame across the circuit."""
    width, height = _paper(schematic)
    edge = SHEET_MARGIN + SHEET_BAND
    block = (width - edge - TITLE_WIDTH, height - edge - TITLE_HEIGHT)
    drawn = _drawn(schematic)
    assert drawn
    for x, y in drawn:
        assert edge < x < width - edge and edge < y < height - edge
        assert not (x > block[0] and y > block[1])


# -- symbols ----------------------------------------------------------------


def test_a_part_with_no_drawn_symbol_gets_a_box_of_its_own_pins(built):
    netlist = compile_netlist(built.snapshot, traits=built.traits)
    placed = {p.designator: p for p in place(built.snapshot, netlist)}
    box = placed["U1"].symbol
    assert box.name == "Box_U1"
    assert {pin.key for pin in box.pins} == {"VDD", "OUT"}
    # Nothing is invented: the numbers are the graph's.
    assert {pin.number for pin in box.pins} == {"1", "2"}


def test_a_drawn_symbol_is_not_read_out_of_an_installed_kicad(schematic):
    """The library on this machine is not an input, so it cannot drift."""
    assert '"fang:Resistor"' in schematic
    assert "Device:R" not in schematic
    assert SYMBOL_OF_PREFIX["R"].graphics


# -- rendering --------------------------------------------------------------


def test_the_renderer_names_the_executable_it_looked_for():
    renderer = KicadRenderer(executable="not-a-cad")
    with pytest.raises(RendererUnavailable, match="not-a-cad"):
        renderer.to_svg("(kicad_sch)", workspace="/tmp")


@pytest.mark.skipif(
    not KicadRenderer().available(), reason="kicad-cli is not installed here"
)
def test_the_render_is_the_ordinary_kicad_sheet(schematic, tmp_path):
    """Background, frame and title block: the picture a reader of a schematic
    expects, drawn with fang's own sheet rather than the installed KiCad's."""
    svg = KicadRenderer().to_svg(schematic, workspace=tmp_path, name="divider")
    width, height = _paper(schematic)
    background = f'<rect x="0.000000" y="0.000000" width="{float(width):f}"'
    assert background in svg
    assert "Title: divider" in svg
    assert f"project {PROJECT}" in svg


@pytest.mark.skipif(
    not KicadRenderer().available(), reason="kicad-cli is not installed here"
)
def test_the_render_carries_nothing_of_the_machine_it_was_made_on(
    built, schematic, tmp_path
):
    """KiCad's own sheet prints its version in the corner of the title block,
    and the snapshot hash covers the path the program was read from. Neither
    belongs in a committed picture, so neither is drawn."""
    svg = KicadRenderer().to_svg(schematic, workspace=tmp_path, name="divider")
    assert "KiCad E.D.A." not in svg
    assert built.snapshot.hash not in svg


@pytest.mark.skipif(
    not KicadRenderer().available(), reason="kicad-cli is not installed here"
)
def test_the_render_carries_no_timestamp(schematic, tmp_path):
    """A picture that changed every run would not be a projection."""
    first = KicadRenderer().to_svg(schematic, workspace=tmp_path / "a", name="divider")
    second = KicadRenderer().to_svg(schematic, workspace=tmp_path / "b", name="divider")
    assert first == second
    assert "<title>divider.svg</title>" in first
