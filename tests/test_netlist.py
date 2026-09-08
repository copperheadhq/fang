"""Spec: Net Inference; Deterministic Designator Assignment; The Netlist Is A
Projection."""

import pytest

from fang.elaborate import elaborate
from fang.entities import Component, Connection, ConnectionKind, Pin as PinEntity
from fang.identity import authored
from fang.kicad import emit_netlist, write_netlist
from fang.lang import System, V, kOhm, uF
from fang.netlist import assign_designators, compile_netlist, infer_nets
from fang.parts import Capacitor, Diode, Resistor

PROJECT = "PRJ-NETLIST"


class Divider(System):
    top = Resistor(resistance=10 * kOhm, package="R_0603")
    bottom = Resistor(resistance=4.7 * kOhm, package="R_0603")
    cap = Capacitor(capacitance=100 * uF, voltage_rating=16 * V, package="C_0805")

    def architecture(self):
        self.top.p2 >> self.bottom.p1
        self.bottom.p1 >> self.cap.p1
        self.bottom.p2 >> self.cap.p2


@pytest.fixture
def divider():
    result = elaborate(Divider, project_id=PROJECT)
    assert result.ok, [d.message for d in result.diagnostics]
    return result


# -- net inference ---------------------------------------------------------


def test_connected_pins_form_one_net(divider):
    netlist = compile_netlist(divider.snapshot, traits=divider.traits)
    junction = netlist.net_of("R1", "1")
    assert junction is not None
    assert {(n.designator, n.pin) for n in junction.nodes} == {
        ("R1", "1"), ("R2", "2"), ("C1", "1")
    }


def test_unconnected_pins_form_separate_nets(divider):
    netlist = compile_netlist(divider.snapshot, traits=divider.traits)
    # R2 pin 1 is the top of the divider and is connected to nothing else.
    assert netlist.net_of("R2", "1") is None
    assert len(netlist.nets) == 2


def test_a_non_conductive_connection_does_not_merge_nets():
    from fang.graph import Snapshot

    pins = {
        "PIN-A": PinEntity(authored("PIN-A"), owner="CMP-1", vendor_name="1"),
        "PIN-B": PinEntity(authored("PIN-B"), owner="CMP-2", vendor_name="1"),
    }
    pins["CN-1"] = Connection(
        authored("CN-1"),
        connection_kind=ConnectionKind.DEPENDENCY,
        source="PIN-A",
        target="PIN-B",
    )
    classes = infer_nets(pins)
    assert len(classes) == 2


def test_net_inference_is_reproducible():
    first = elaborate(Divider, project_id=PROJECT)
    second = elaborate(Divider, project_id=PROJECT)
    a = compile_netlist(first.snapshot, traits=first.traits)
    b = compile_netlist(second.snapshot, traits=second.traits)
    assert a.as_dict() == b.as_dict()


def test_a_net_name_is_a_function_of_its_membership(divider):
    netlist = compile_netlist(divider.snapshot, traits=divider.traits)
    for net in netlist.nets:
        first = min((n.designator, n.pin) for n in net.nodes)
        assert net.name == f"Net-({first[0]}-Pad{first[1]})"


# -- designators -----------------------------------------------------------


def test_numbering_is_per_prefix(divider):
    netlist = compile_netlist(divider.snapshot, traits=divider.traits)
    assert sorted(c.designator for c in netlist.components) == ["C1", "R1", "R2"]


def test_the_same_design_yields_the_same_designators():
    first = elaborate(Divider, project_id=PROJECT)
    second = elaborate(Divider, project_id=PROJECT)
    assert assign_designators(first.snapshot.entities) == assign_designators(
        second.snapshot.entities
    )


def test_an_authored_designator_is_preserved():
    entities = {
        "CMP-1": Component(authored("CMP-1"), designator="R42", extensions={"designator_prefix": "R"}),
        "CMP-2": Component(authored("CMP-2"), extensions={"designator_prefix": "R"}),
    }
    assigned = assign_designators(entities)
    assert assigned["CMP-1"] == "R42"
    assert assigned["CMP-2"].startswith("R")
    assert assigned["CMP-2"] != "R42"


def test_designators_are_ordered_by_canonical_path():
    """Ordering by path, not by identifier, keeps designators stable and readable."""
    result = elaborate(Divider, project_id=PROJECT)
    assigned = assign_designators(result.snapshot.entities)
    by_path = sorted(
        (
            (str(e.identity.path), assigned[e.id])
            for e in result.snapshot.entities.values()
            if isinstance(e, Component)
        )
    )
    resistors = [designator for path, designator in by_path if designator.startswith("R")]
    assert resistors == ["R1", "R2"]


# -- the projection --------------------------------------------------------


def test_a_netlist_names_its_parent_snapshot(divider):
    netlist = compile_netlist(divider.snapshot, traits=divider.traits)
    assert netlist.snapshot == divider.snapshot.hash


def test_compiling_does_not_mutate_the_graph(divider):
    before = divider.snapshot.hash
    compile_netlist(divider.snapshot, traits=divider.traits)
    assert divider.snapshot.hash == before


def test_a_netlist_contains_nothing_absent_from_the_snapshot(divider):
    netlist = compile_netlist(divider.snapshot, traits=divider.traits)
    for component in netlist.components:
        assert component.entity_id in divider.snapshot.entities
    for net in netlist.nets:
        for node in net.nodes:
            assert node.pin_id in divider.snapshot.entities


def test_component_values_come_from_declared_parameters(divider):
    netlist = compile_netlist(divider.snapshot, traits=divider.traits)
    values = {c.designator: c.value for c in netlist.components}
    assert values["R1"] == "4.7 kOhm"
    assert values["R2"] == "10 kOhm"
    assert values["C1"] == "100 uF"


def test_a_part_with_no_known_value_is_not_given_an_invented_one():
    class Vague(System):
        r = Resistor()

    result = elaborate(Vague, project_id=PROJECT)
    netlist = compile_netlist(result.snapshot, traits=result.traits)
    assert netlist.components[0].value == "Resistor"


def test_footprints_come_from_the_footprint_trait(divider):
    netlist = compile_netlist(divider.snapshot, traits=divider.traits)
    footprints = {c.designator: c.footprint for c in netlist.components}
    assert footprints["R1"] == "Package:R_0603"
    assert footprints["C1"] == "Package:C_0805"
