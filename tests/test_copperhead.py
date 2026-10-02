"""Spec: One canonical model (a drafted sheet is a lowering) and External
Adapters Report Loss."""

import json

import pytest

from fang.copperhead import (
    CopperheadDrafter,
    DraftRefused,
    DrafterUnavailable,
    compile_intent,
    drawn_connections,
    intended_connections,
)
from fang.elaborate import elaborate
from fang.interfaces import Pin, PinMap
from fang.lang import Electrical, Parameter, Part, System, V, kOhm, uF
from fang.netlist import compile_netlist
from fang.parts import Capacitor, Resistor, TwoPin

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


def test_a_ground_marker_is_a_ground_net_rather_than_a_part(intent):
    """copperhead draws the ground symbol on the net; a part drawn there too
    would be a second ground symbol with nothing behind it."""
    assert not any(ref.startswith("GND") for ref in _refs(intent))
    grounds = [net for net in intent.document["nets"] if net.get("kind") == "ground"]
    assert len(grounds) == 1
    assert not any(pin.startswith("GND") for pin in grounds[0]["pins"])


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
    for ref in _refs(intent):
        assert f'"{ref}"' in first
