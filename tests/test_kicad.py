"""Spec: The Netlist Is A Projection (emission)."""

import pytest

from fang.elaborate import elaborate
from fang.kicad import SExpr, emit_netlist, write_netlist
from fang.lang import System, V, kOhm, uF
from fang.netlist import compile_netlist
from fang.parts import Capacitor, Resistor

PROJECT = "PRJ-KICAD"


class Divider(System):
    top = Resistor(resistance=10 * kOhm, package="R_0603")
    bottom = Resistor(resistance=4.7 * kOhm, package="R_0603")
    cap = Capacitor(capacitance=100 * uF, package="C_0805")

    def architecture(self):
        self.top.p2 >> self.bottom.p1
        self.bottom.p1 >> self.cap.p1
        self.bottom.p2 >> self.cap.p2


@pytest.fixture
def netlist():
    result = elaborate(Divider, project_id=PROJECT)
    assert result.ok
    return compile_netlist(result.snapshot, traits=result.traits)


def test_the_s_expression_writer_quotes_and_nests():
    node = SExpr("comp", SExpr("ref", "R1"), SExpr("value", 'a "quoted" value'))
    rendered = node.render()
    assert '(ref "R1")' in rendered
    assert '\\"quoted\\"' in rendered
    assert rendered.startswith("(comp\n")


def test_emission_is_byte_identical_for_unchanged_input(netlist):
    assert emit_netlist(netlist) == emit_netlist(netlist)


def test_the_emitted_file_names_the_snapshot_it_came_from(netlist):
    rendered = emit_netlist(netlist)
    assert f'(snapshot "{netlist.snapshot}")' in rendered
    assert f'(project "{netlist.project_id}")' in rendered


def test_every_component_is_emitted_with_ref_value_and_footprint(netlist):
    rendered = emit_netlist(netlist)
    for component in netlist.components:
        assert f'(ref "{component.designator}")' in rendered
        assert f'(value "{component.value}")' in rendered
        if component.footprint:
            assert f'(footprint "{component.footprint}")' in rendered


def test_every_net_is_emitted_with_its_nodes(netlist):
    rendered = emit_netlist(netlist)
    for net in netlist.nets:
        assert f'(net "code" "{net.code}" "name" "{net.name}")' in rendered or (
            f'"name" "{net.name}"' in rendered
        )
        for node in net.nodes:
            assert f'(node "ref" "{node.designator}" "pin" "{node.pin}")' in rendered


def test_the_entity_id_travels_with_the_component(netlist):
    """It is what makes a round trip identity-preserving rather than name-matching."""
    rendered = emit_netlist(netlist)
    for component in netlist.components:
        assert component.entity_id in rendered


def test_writing_produces_exactly_the_bytes_returned(tmp_path, netlist):
    path = tmp_path / "divider.net"
    data = write_netlist(netlist, path)
    assert path.read_bytes() == data
    assert data.endswith(b"\n")


def test_a_manufacturer_and_mpn_are_emitted_as_fields():
    class Sourced(System):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.r.select("Yageo", "RC0603FR-0710KL")

        r = Resistor(resistance=10 * kOhm, package="R_0603")
        r2 = Resistor(resistance=10 * kOhm, package="R_0603")

        def architecture(self):
            self.r.p1 >> self.r2.p1

    result = elaborate(Sourced, project_id=PROJECT)
    compiled = compile_netlist(result.snapshot, traits=result.traits)
    rendered = emit_netlist(compiled)
    assert "Yageo" in rendered
    assert "RC0603FR-0710KL" in rendered


def test_the_end_to_end_path_from_a_program_to_a_file(tmp_path):
    """A Fang program becomes a netlist a person can open."""
    result = elaborate(Divider, project_id=PROJECT)
    compiled = compile_netlist(result.snapshot, traits=result.traits)
    data = write_netlist(compiled, tmp_path / "divider.net", source="divider.py")

    text = data.decode()
    assert text.startswith('(export "version" "E"')
    assert '(source "divider.py")' in text
    assert text.count("(comp\n") == 3   # "(components" must not match
    assert text.count("(net ") == len(compiled.nets)
