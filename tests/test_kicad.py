"""Spec: The Netlist Is A Projection (emission); The KiCad Netlist Adapter Uses
KiCad's Own Form."""

from pathlib import Path

import pytest

from fang.elaborate import elaborate
from fang.entities import Component, Net, Pin
from fang.kicad import SExpr, emit_netlist, read_netlist, write_netlist
from fang.lang import System, V, kOhm, uF
from fang.netlist import compile_netlist
from fang.parts import Capacitor, Resistor
from fang.sexpr import Atom, Node, parse

PROJECT = "PRJ-KICAD"

#: A netlist KiCad itself exported; examples/imported/README.md says from what.
KICAD_EXPORT = Path(__file__).resolve().parent.parent / "examples" / "imported" / "reference.net"


class Divider(System):
    top = Resistor(resistance=10 * kOhm, package="R_0603")
    bottom = Resistor(resistance=4.7 * kOhm, package="R_0603")
    cap = Capacitor(capacitance=100 * uF, package="C_0805")

    def architecture(self):
        self.top.p2 >> self.bottom.p1
        self.bottom.p1 >> self.cap.p1
        self.bottom.p2 >> self.cap.p2


class Sourced(System):
    """A part with a manufacturer and an MPN, so fields are emitted."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.r.select("Yageo", "RC0603FR-0710KL")

    r = Resistor(resistance=10 * kOhm, package="R_0603")
    r2 = Resistor(resistance=10 * kOhm, package="R_0603")

    def architecture(self):
        self.r.p1 >> self.r2.p1


@pytest.fixture
def netlist():
    result = elaborate(Divider, project_id=PROJECT)
    assert result.ok
    return compile_netlist(result.snapshot, traits=result.traits)


@pytest.fixture
def sourced():
    result = elaborate(Sourced, project_id=PROJECT)
    assert result.ok
    return compile_netlist(result.snapshot, traits=result.traits)


def elements(node: Node, head: str) -> list[Node]:
    """Every list with this head, at any depth."""
    found = [node] if node.head == head else []
    for item in node.rest:
        if isinstance(item, Node):
            found.extend(elements(item, head))
    return found


def child_heads(node: Node) -> set[str]:
    return {item.head for item in node.rest if isinstance(item, Node)}


def test_the_s_expression_writer_quotes_and_nests():
    node = SExpr("comp", SExpr("ref", "R1"), SExpr("value", 'a "quoted" value'))
    rendered = node.render()
    assert '(ref "R1")' in rendered
    assert '\\"quoted\\"' in rendered
    assert rendered.startswith("(comp\n")


def test_the_writer_keeps_child_order_when_an_atom_follows_a_list():
    field = parse(SExpr("field", SExpr("name", "MPN"), "RC0603FR-0710KL").render())
    assert isinstance(field.items[1], Node) and field.items[1].head == "name"
    assert isinstance(field.items[2], Atom) and field.items[2].value == "RC0603FR-0710KL"


def test_emission_is_byte_identical_for_unchanged_input(netlist):
    assert emit_netlist(netlist) == emit_netlist(netlist)


def test_the_emitted_file_names_the_snapshot_it_came_from(netlist):
    design = parse(emit_netlist(netlist)).child("design")
    assert design.value("snapshot") == netlist.snapshot
    assert design.value("project") == netlist.project_id


def test_every_component_is_emitted_with_ref_value_and_footprint(netlist):
    emitted = {
        comp.value("ref"): comp
        for comp in parse(emit_netlist(netlist)).child("components").children("comp")
    }
    assert set(emitted) == {component.designator for component in netlist.components}
    for component in netlist.components:
        comp = emitted[component.designator]
        assert comp.value("value") == component.value
        assert comp.value("footprint") == component.footprint


def test_every_net_is_emitted_with_its_nodes(netlist):
    emitted = {
        net.value("name"): net
        for net in parse(emit_netlist(netlist)).child("nets").children("net")
    }
    assert set(emitted) == {net.name for net in netlist.nets}
    for net in netlist.nets:
        written = emitted[net.name]
        assert written.value("code") == str(net.code)
        assert [(node.value("ref"), node.value("pin")) for node in written.children("node")] == [
            (node.designator, node.pin) for node in net.nodes
        ]


def test_the_entity_id_travels_with_the_component(netlist):
    """It is what makes a round trip identity-preserving rather than name-matching."""
    properties = [
        comp.child("property")
        for comp in parse(emit_netlist(netlist)).child("components").children("comp")
    ]
    assert all(prop.value("name") == "fang_id" for prop in properties)
    assert {prop.value("value") for prop in properties} == {
        component.entity_id for component in netlist.components
    }


def test_writing_produces_exactly_the_bytes_returned(tmp_path, netlist):
    path = tmp_path / "divider.net"
    data = write_netlist(netlist, path)
    assert path.read_bytes() == data
    assert data.endswith(b"\n")


def test_a_manufacturer_and_mpn_are_emitted_as_fields(sourced):
    fields = {
        field.value("name"): field.atoms()
        for comp in parse(emit_netlist(sourced)).child("components").children("comp")
        if comp.child("fields")
        for field in comp.child("fields").children("field")
    }
    assert fields == {"Manufacturer": ["Yageo"], "MPN": ["RC0603FR-0710KL"]}


def test_an_emitted_netlist_nests_every_field_as_kicad_does(sourced):
    root = parse(emit_netlist(sourced))
    assert root.atoms() == []
    assert root.value("version") == "E"
    for head in ("design", "comp", "property", "net", "node"):
        found = elements(root, head)
        assert found, head
        for element in found:
            assert element.atoms() == [], f"{head} carries flat atoms: {element.atoms()}"
    for field in elements(root, "field"):
        assert field.value("name")          # the key is a list of its own
        assert len(field.atoms()) == 1      # and the value follows it


def test_an_emitted_netlist_reads_back_whole(sourced):
    result = read_netlist(emit_netlist(sourced), project_id=PROJECT, source="sourced.net")
    entities = result.entities.values()
    assert {e.designator for e in entities if isinstance(e, Component)} == {
        component.designator for component in sourced.components
    }
    assert {alias for e in entities if isinstance(e, Net) for alias in e.aliases} == {
        net.name for net in sourced.nets
    }
    assert len([e for e in entities if isinstance(e, Pin)]) == sum(
        len(net.nodes) for net in sourced.nets
    )


def test_every_element_fang_emits_has_the_shape_kicad_writes(sourced):
    """Each child Fang writes appears in the same element of a file KiCad wrote."""
    ours = parse(emit_netlist(sourced))
    kicads = parse(KICAD_EXPORT.read_text())
    # Fang's own additions: the snapshot and project a netlist is a projection of.
    fang_only = {"design": {"snapshot", "project"}}

    for head in ("export", "design", "comp", "fields", "field", "property", "net", "node"):
        emitted, written = elements(ours, head), elements(kicads, head)
        assert emitted and written, head
        ours_children = set().union(*(child_heads(element) for element in emitted))
        kicad_children = set().union(*(child_heads(element) for element in written))
        extra = ours_children - fang_only.get(head, set()) - kicad_children
        assert not extra, f"{head} carries {sorted(extra)}, which KiCad does not write"


def test_the_end_to_end_path_from_a_program_to_a_file(tmp_path):
    """A Fang program becomes a netlist a person can open."""
    result = elaborate(Divider, project_id=PROJECT)
    compiled = compile_netlist(result.snapshot, traits=result.traits)
    data = write_netlist(compiled, tmp_path / "divider.net", source="divider.py")

    root = parse(data.decode())
    assert root.head == "export"
    assert root.value("version") == "E"
    assert root.child("design").value("source") == "divider.py"
    assert len(root.child("components").children("comp")) == 3
    assert len(root.child("nets").children("net")) == len(compiled.nets)
