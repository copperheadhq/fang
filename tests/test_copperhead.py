"""Spec: One canonical model (a drafted sheet is a lowering) and External
Adapters Report Loss."""

import json

import pytest

from fang.copperhead import (
    CopperheadDrafter,
    DraftRefused,
    DrafterUnavailable,
    Intent,
    compile_intent,
    drawn_connections,
    intended_connections,
    short_value,
)
from fang.elaborate import elaborate
from fang.interfaces import Pin, PinMap
from fang.lang import Electrical, Parameter, Part, System, V, kOhm, uF
from fang.netlist import compile_netlist
from fang.parts import Capacitor, Diode, Resistor, TestPoint, TwoPin

PROJECT = "PRJ-COPPERHEAD"


class Source(TwoPin):
    designator_prefix = "V"
    voltage = Parameter("V")


class Marker(Part):
    designator_prefix = "GND"

    node = Electrical()
    PIN1 = Pin("1", role="ground", number="1")
    pinmap = PinMap({"node.line": "1"})


class Sensor(Part):
    """A part no prefix names a symbol for, and that names none itself."""

    designator_prefix = "U"

    supply = Electrical()
    out = Electrical()
    VDD = Pin("VDD", role="power", number="1")
    OUT = Pin("OUT", role="analog", number="2")
    pinmap = PinMap({"supply.line": "VDD", "out.line": "OUT"})


class Drawn(Sensor):
    """The same part, naming the symbol it is drawn with."""

    symbol = "Sensor:Generic"


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
        self.bottom.p2 >> self.reference.node
        self.sensor.supply >> self.top.p1
        self.sensor.out >> self.bottom.p1


class Named(System):
    top = Resistor(resistance=10 * kOhm, package="R_0603")
    sensor = Drawn(package="SOT-23")

    def architecture(self):
        self.sensor.supply >> self.top.p1
        self.sensor.out >> self.top.p2


@pytest.fixture
def built():
    result = elaborate(Divider, project_id=PROJECT)
    assert result.ok, [d.message for d in result.diagnostics]
    return result


@pytest.fixture
def intent(built):
    return compile_intent(built.snapshot, traits=built.traits, group="divider")


def _refs(intent):
    return [part["ref"] for part in intent.document["parts"]]


def test_the_intent_is_byte_identical_for_unchanged_input(built):
    first = compile_intent(built.snapshot, traits=built.traits)
    second = compile_intent(built.snapshot, traits=built.traits)
    assert first.text() == second.text()
    assert json.loads(first.text()) == first.document


def test_a_part_is_drawn_with_the_symbol_its_prefix_names(intent):
    library = {part["ref"]: part["libId"] for part in intent.document["parts"]}
    assert library["R1"] == "Device:R"
    assert library["C1"] == "Device:C"
    assert library["V1"] == "Device:Battery_Cell"


def test_a_ground_marker_is_drawn_with_kicads_ground_symbol_on_a_ground_net(intent):
    """The marker is a part of the netlist, so it is in the intent, drawn with
    the symbol KiCad draws ground with; copperhead draws that symbol at each
    pin of the net rather than the part itself."""
    marker = {part["ref"]: part for part in intent.document["parts"]}["GND1"]
    assert marker["libId"] == "power:GND"
    assert marker["value"] == "GND"
    grounds = [net for net in intent.document["nets"] if net.get("kind") == "ground"]
    assert len(grounds) == 1
    assert "GND1.1" in grounds[0]["pins"]


def test_a_power_symbol_is_left_out_of_the_connections_a_draft_must_have(intent):
    """KiCad names the power symbols copperhead draws `#PWR...` and the read
    back leaves them out, so the intent's own power part is left out too."""
    wanted = intended_connections(intent)
    assert not any(pin.startswith("GND1.") for net in wanted for pin in net)
    assert frozenset({"C1.2", "R1.2", "V1.2"}) in wanted


def test_a_net_from_a_ground_marker_to_one_pin_is_drawn():
    """A resistor to ground is a net of two pins, one of them the marker's:
    copperhead draws it as a ground symbol on the resistor, not a loss."""

    class Pulldown(System):
        load = Resistor(resistance=10 * kOhm, package="R_0603")
        cap = Capacitor(capacitance=100 * uF, package="C_0805")
        reference = Marker(package="GND")

        def architecture(self):
            self.load.p1 >> self.cap.p1
            self.load.p2 >> self.reference.node

    result = elaborate(Pulldown, project_id=PROJECT)
    assert result.ok, [d.message for d in result.diagnostics]
    intent = compile_intent(result.snapshot, traits=result.traits)
    assert intent.losses == ()
    grounds = [net for net in intent.document["nets"] if net.get("kind") == "ground"]
    assert [net["pins"] for net in grounds] == [["GND1.1", "R1.2"]]


def test_an_endpoint_is_named_by_pin_number(intent):
    """copperhead finds a pin on the symbol by its number."""
    pins = {pin for net in intent.document["nets"] for pin in net["pins"]}
    assert "R1.1" in pins and "R1.2" in pins


def test_a_part_with_no_symbol_is_reported_rather_than_dropped(intent):
    assert "U1" not in _refs(intent)
    assert any(loss.startswith("U1 is not drawn") for loss in intent.losses)


def test_a_part_names_its_own_symbol():
    result = elaborate(Named, project_id=PROJECT)
    assert result.ok, [d.message for d in result.diagnostics]
    netlist = compile_netlist(result.snapshot, traits=result.traits)
    assert {c.designator: c.libsource for c in netlist.components}["U1"] == "Sensor:Generic"
    intent = compile_intent(result.snapshot, traits=result.traits)
    assert {p["ref"]: p["libId"] for p in intent.document["parts"]}["U1"] == "Sensor:Generic"
    assert intent.losses == ()


def test_a_net_that_reaches_one_drawn_pin_is_reported():
    """The sensor is not drawn, so each net it shares with the resistor is
    left with one pin; copperhead draws a net between two or more."""

    class Dangling(System):
        top = Resistor(resistance=10 * kOhm, package="R_0603")
        sensor = Sensor(package="SOT-23")

        def architecture(self):
            self.sensor.supply >> self.top.p1
            self.sensor.out >> self.top.p2

    result = elaborate(Dangling, project_id=PROJECT)
    assert result.ok, [d.message for d in result.diagnostics]
    intent = compile_intent(result.snapshot, traits=result.traits)
    assert intent.document["nets"] == []
    reported = [loss for loss in intent.losses if loss.startswith("net ")]
    assert len(reported) == 2
    assert all("reaches 1 drawn pin" in loss for loss in reported)


def test_the_title_block_date_is_not_invented(intent):
    assert intent.document["hints"]["date"] == ""


def test_the_title_block_date_is_the_one_the_caller_names(built):
    intent = compile_intent(built.snapshot, traits=built.traits, date="2026-01-01")
    assert intent.document["hints"]["date"] == "2026-01-01"


# -- symbols chosen by type, and where the pins land -------------------------


class OpAmp(Part):
    """An ideal op amp, numbered as the single-op-amp 8-pin pinout is."""

    designator_prefix = "U"

    inverting = Electrical()
    non_inverting = Electrical()
    output = Electrical()
    IN_MINUS = Pin("IN-", role="analog", number="2")
    IN_PLUS = Pin("IN+", role="analog", number="3")
    OUT = Pin("OUT", role="analog", number="6")
    pinmap = PinMap(
        {"inverting.line": "IN-", "non_inverting.line": "IN+", "output.line": "OUT"}
    )


class DrawnOpAmp(OpAmp):
    """The same op amp, naming the symbol whose pins its own numbers are."""

    symbol = "Amplifier_Operational:LM741"


def _follower(amplifier):
    class Follower(System):
        amp = amplifier(package="DIP-8")
        e_in = TestPoint(package="TP")
        e_out = TestPoint(package="TP")
        load = Resistor(resistance=10 * kOhm, package="R_0603")
        reference = Marker(package="GND")

        def architecture(self):
            self.e_in.probe >> self.amp.non_inverting
            self.amp.output >> self.amp.inverting
            self.amp.output >> self.e_out.probe
            self.amp.output >> self.load.p1
            self.load.p2 >> self.reference.node

    result = elaborate(Follower, project_id=PROJECT)
    assert result.ok, [d.message for d in result.diagnostics]
    return result


def _pins(intent):
    return sorted(pin for net in intent.document["nets"] for pin in net["pins"])


def test_an_op_amp_is_drawn_by_its_type_on_the_pins_its_symbol_numbers():
    """No prefix picks out an op amp, since `U` covers every integrated part;
    its type does, and KiCad's generic op amp numbers + 1, - 2 and out 5."""
    result = _follower(OpAmp)
    intent = compile_intent(result.snapshot, traits=result.traits)
    amp = {part["ref"]: part for part in intent.document["parts"]}["U1"]
    assert amp["libId"] == "Simulation_SPICE:OPAMP"
    assert amp["value"] == "OPAMP"
    assert {"U1.1", "U1.2", "U1.5"} <= set(_pins(intent))
    assert not {"U1.3", "U1.6"} & set(_pins(intent))
    assert intent.losses == ()


def test_a_part_naming_its_own_symbol_is_drawn_with_it_by_its_own_numbers():
    result = _follower(DrawnOpAmp)
    intent = compile_intent(result.snapshot, traits=result.traits)
    amp = {part["ref"]: part for part in intent.document["parts"]}["U1"]
    assert amp["libId"] == "Amplifier_Operational:LM741"
    assert amp["value"] == "DrawnOpAmp"
    assert {"U1.2", "U1.3", "U1.6"} <= set(_pins(intent))


def test_a_pin_its_symbol_has_no_place_for_is_reported_rather_than_moved():
    """An op amp type with a supply pin: drawn by number, V+ (7) would land on
    nothing, and drawn without it, the part would show unconnected a pin the
    design connects."""

    # Named OpAmp, the type the table draws; its base is the module's OpAmp.
    class OpAmp(globals()["OpAmp"]):
        supply = Electrical()
        VCC = Pin("V+", role="power", number="7")
        pinmap = PinMap(
            {
                "inverting.line": "IN-",
                "non_inverting.line": "IN+",
                "output.line": "OUT",
                "supply.line": "V+",
            }
        )

    result = _follower(OpAmp)
    intent = compile_intent(result.snapshot, traits=result.traits)
    assert "U1" not in _refs(intent)
    assert any(
        loss.startswith("U1 is not drawn") and "V+" in loss for loss in intent.losses
    )


def test_a_diode_is_drawn_with_its_cathode_on_kicads_pin_1():
    """A fang diode numbers its anode 1, and KiCad's diode its cathode 1: drawn
    by number, every diode would be drawn backwards."""

    class Clamp(System):
        diode = Diode(package="SOD-123")
        load = Resistor(resistance=10 * kOhm, package="R_0603")
        reference = Marker(package="GND")

        def architecture(self):
            self.diode.p1 >> self.load.p1
            self.diode.p2 >> self.reference.node
            self.load.p2 >> self.reference.node

    result = elaborate(Clamp, project_id=PROJECT)
    assert result.ok, [d.message for d in result.diagnostics]
    intent = compile_intent(result.snapshot, traits=result.traits)
    nets = {net["name"]: net for net in intent.document["nets"]}
    ground = next(net for net in nets.values() if net.get("kind") == "ground")
    assert "D1.1" in ground["pins"]
    assert any("D1.2" in net["pins"] and "R1.1" in net["pins"] for net in nets.values())


# -- labelling: options every caller passes or leaves alike -------------------


def test_the_ground_net_keeps_the_netlists_name_unless_one_is_given(built):
    netlist = compile_netlist(built.snapshot, traits=built.traits)
    plain = compile_intent(built.snapshot, traits=built.traits)
    named = compile_intent(built.snapshot, traits=built.traits, ground="GND")

    def ground(intent):
        return next(net for net in intent.document["nets"] if net.get("kind") == "ground")

    assert ground(plain)["name"] in {net.name for net in netlist.nets}
    assert ground(named)["name"] == "GND"
    assert ground(named)["pins"] == ground(plain)["pins"]


def test_a_terminal_is_labelled_and_names_its_net_when_asked():
    result = _follower(OpAmp)
    plain = compile_intent(result.snapshot, traits=result.traits)
    named = compile_intent(result.snapshot, traits=result.traits, terminal_names=True)
    values = {part["ref"]: part["value"] for part in named.document["parts"]}
    assert values["TP1"] == "E_IN" and values["TP2"] == "E_OUT"
    assert {part["ref"]: part["value"] for part in plain.document["parts"]}["TP1"] == "TestPoint"
    by_pin = {pin: net["name"] for net in named.document["nets"] for pin in net["pins"]}
    assert by_pin["U1.1"] == "E_IN"
    assert by_pin["U1.5"] == "E_OUT"
    assert [net["pins"] for net in named.document["nets"]] == [
        net["pins"] for net in plain.document["nets"]
    ]


def test_a_value_is_printed_short_when_asked(built):
    plain = compile_intent(built.snapshot, traits=built.traits)
    short = compile_intent(built.snapshot, traits=built.traits, short_values=True)
    assert {p["ref"]: p["value"] for p in plain.document["parts"]}["R1"] == "4.7 kOhm"
    assert {p["ref"]: p["value"] for p in short.document["parts"]}["R1"] == "4.7k"
    assert {p["ref"]: p["value"] for p in short.document["parts"]}["C1"] == "100uF"


def test_a_short_value_drops_the_ohm_and_the_spaces():
    assert short_value("4.7 kOhm") == "4.7k"
    assert short_value("1 MOhm") == "1M"
    assert short_value("330 Ohm") == "330"
    assert short_value("15.9 nF") == "15.9nF"
    assert short_value("OPAMP") == "OPAMP"


def test_a_name_given_to_two_nets_is_refused():
    """KiCad joins nets drawn under one name, so the drawing would not be the
    netlist; the intent is refused before copperhead is asked."""
    result = _follower(OpAmp)
    with pytest.raises(ValueError, match="E_OUT"):
        compile_intent(result.snapshot, traits=result.traits, ground="E_OUT", terminal_names=True)


def test_every_option_left_alone_is_the_same_intent_for_every_caller(built):
    """There is one lowering: the defaults are the defaults, not a caller's."""
    assert compile_intent(built.snapshot, traits=built.traits).text() == compile_intent(
        built.snapshot,
        traits=built.traits,
        group="fang",
        ground=None,
        terminal_names=False,
        short_values=False,
        date="",
    ).text()


# -- drafting ---------------------------------------------------------------


def test_the_drafter_names_the_executable_it_looked_for(intent, tmp_path):
    with pytest.raises(DrafterUnavailable, match="not-copperhead"):
        CopperheadDrafter(executable="not-copperhead").draft(intent, workspace=tmp_path)


#: A KiCad netlist as `kicad-cli sch export netlist` writes one: a power
#: symbol on the ground net, and a resistor pin landed on another net's wire.
READ_BACK = """(export (version "E")
  (nets
    (net (code "1") (name "GND")
      (node (ref "#PWR01") (pin "1"))
      (node (ref "R1") (pin "2"))
      (node (ref "V1") (pin "2")))
    (net (code "2") (name "out")
      (node (ref "R1") (pin "1"))
      (node (ref "R2") (pin "1"))
      (node (ref "R3") (pin "2")))))
"""


def test_a_draft_is_read_back_without_its_power_symbols():
    assert drawn_connections(READ_BACK) == {
        frozenset({"R1.2", "V1.2"}),
        frozenset({"R1.1", "R2.1", "R3.2"}),
    }


def test_a_draft_whose_connections_are_not_the_intent_is_refused(intent, tmp_path, monkeypatch):
    """copperhead exiting 0 is not enough: the sheet is read back, and one
    that lands a pin on another net's wire is refused, naming the net."""
    import subprocess

    import fang.copperhead as module

    monkeypatch.setattr(module.shutil, "which", lambda name: f"/opt/bin/{name}")

    def fake_run(self, arguments, **options):
        workspace = options["cwd"]
        if arguments[1:3] == ["sch", "export"]:
            wanted = sorted(intended_connections(intent), key=sorted)
            nets = "".join(
                f'(net (code "{i}") (name "n{i}")'
                + "".join(
                    f' (node (ref "{pin.split(".")[0]}") (pin "{pin.split(".")[1]}"))'
                    for pin in sorted(net) + (["X9.1"] if i == 0 else [])
                )
                + ")"
                for i, net in enumerate(wanted)
            )
            (workspace / "read-back.net").write_text(f"(export (nets {nets}))\n")
        else:
            (workspace / "divider.kicad_sch").write_text("(kicad_sch)\n")
        return subprocess.CompletedProcess(arguments, 0, "", "")

    monkeypatch.setattr(CopperheadDrafter, "_run", fake_run)
    with pytest.raises(DraftRefused, match="X9.1"):
        CopperheadDrafter().draft(intent, workspace=tmp_path, name="divider")


def test_a_draft_needs_the_reader_that_checks_it(intent, tmp_path):
    with pytest.raises(DrafterUnavailable, match="not-kicad-cli"):
        CopperheadDrafter(reader="not-kicad-cli").draft(intent, workspace=tmp_path)


@pytest.mark.skipif(
    not CopperheadDrafter().available(), reason="copperhead or kicad-cli is not installed here"
)
def test_a_draft_is_byte_identical_wherever_it_is_made(intent, tmp_path):
    first = CopperheadDrafter().draft(intent, workspace=tmp_path / "a", name="divider")
    second = CopperheadDrafter().draft(intent, workspace=tmp_path / "b", name="divider")
    assert first == second
    # A power part is drawn as copperhead's own symbol at each pin of its net.
    for part in intent.document["parts"]:
        if not part["libId"].startswith("power:"):
            assert f'"{part["ref"]}"' in first
