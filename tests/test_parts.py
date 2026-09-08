"""Spec: The Part Model; The Standard Part Library."""

import pytest

from fang.elaborate import elaborate
from fang.entities import Component, Connection, Pin as PinEntity
from fang.lang import System, A, V, kOhm, mm, uF
from fang.parts import (
    LIBRARY,
    Capacitor,
    Connector,
    Crystal,
    Diode,
    Fuse,
    GenericPart,
    Inductor,
    LED,
    MountingHole,
    Regulator,
    Resistor,
    TestPoint,
    Transistor,
    TwoPin,
)
from fang.values import ValueStatus

PROJECT = "PRJ-PARTS"

REQUIRED_LIBRARY = {
    "Resistor", "Capacitor", "Inductor", "Diode", "LED", "Fuse", "Crystal",
    "Transistor", "Regulator", "Connector", "TestPoint", "MountingHole",
}


def test_the_library_covers_every_required_part():
    assert {part.__name__ for part in LIBRARY} >= REQUIRED_LIBRARY


def test_a_generic_part_has_no_vendor_identity():
    resistor = Resistor(resistance=10 * kOhm)
    assert resistor.manufacturer is None
    assert resistor.mpn is None
    assert not resistor.selected
    assert not [t for t in resistor.traits if t.protocol == "sourcing"]


def test_selecting_a_vendor_part_records_it_as_sourcing():
    resistor = Resistor(resistance=10 * kOhm)
    resistor.select("Yageo", "RC0603FR-0710KL", distributor_ids={"lcsc": "C25804"})

    sourcing = next(t for t in resistor.traits if t.protocol == "sourcing")
    assert sourcing.manufacturer == "Yageo"
    assert sourcing.mpn == "RC0603FR-0710KL"
    assert sourcing.distributor_ids == {"lcsc": "C25804"}
    # The logical identity is untouched: it is still a resistor of 10 kOhm.
    assert type(resistor) is Resistor
    assert str(resistor.value_of("resistance").quantity) == "10 kOhm"


def test_selecting_can_carry_datasheet_evidence():
    part = Regulator()
    part.select("TI", "TPS62130RGTR", datasheet="SRC-DS-TPS62130", evidence=("EVD-1",))
    trait = next(t for t in part.traits if t.protocol == "datasheet_evidence")
    assert trait.document == "SRC-DS-TPS62130"
    assert trait.evidence_ids == ("EVD-1",)


def test_designator_prefixes_are_declared_per_part_type():
    assert Resistor.designator_prefix == "R"
    assert Capacitor.designator_prefix == "C"
    assert Inductor.designator_prefix == "L"
    assert Regulator.designator_prefix == "U"
    assert Transistor.designator_prefix == "Q"
    assert Connector.designator_prefix == "J"
    assert TestPoint.designator_prefix == "TP"
    assert MountingHole.designator_prefix == "H"


def test_a_package_becomes_a_footprint_trait():
    resistor = Resistor(resistance=10 * kOhm, package="R_0603_1608Metric")
    footprint = next(t for t in resistor.traits if t.protocol == "footprint")
    assert footprint.name == "R_0603_1608Metric"


def test_each_library_part_declares_the_parameters_its_type_carries():
    assert set(Capacitor._parameters) >= {"capacitance", "voltage_rating"}
    assert set(Resistor._parameters) >= {"resistance", "power_rating"}
    assert set(Crystal._parameters) >= {"frequency", "load_capacitance"}
    assert set(Transistor._parameters) >= {"vds_max", "id_max", "rds_on"}
    assert set(Regulator._parameters) >= {"output_voltage", "output_current_max"}


def test_an_undeclared_rating_stays_unknown():
    capacitor = Capacitor(capacitance=100 * uF)
    assert capacitor.value_of("capacitance").status is ValueStatus.EXPLICIT
    assert capacitor.value_of("voltage_rating").status is ValueStatus.UNKNOWN


def test_a_two_pin_passive_lowers_to_its_two_pins():
    class Pair(System):
        a = Resistor(resistance=10 * kOhm)
        b = Resistor(resistance=10 * kOhm)

        def architecture(self):
            self.a.p2 >> self.b.p1

    result = elaborate(Pair, project_id=PROJECT)
    assert result.ok
    pins = {
        e.id: e.vendor_name
        for e in result.snapshot.entities.values()
        if isinstance(e, PinEntity)
    }
    lowered = [
        c
        for c in result.snapshot.entities.values()
        if isinstance(c, Connection) and c.derived_from_interface
    ]
    assert len(lowered) == 1
    assert (pins[lowered[0].source], pins[lowered[0].target]) == ("2", "1")


def test_a_diode_names_its_pins_anode_and_cathode():
    diode = Diode(forward_voltage=0.7 * V)
    assert sorted(p.name for p in diode.pins().values()) == ["A", "K"]


def test_a_part_with_no_electrical_function_still_participates():
    class Mechanical(System):
        hole = MountingHole(diameter=3 * mm)

    result = elaborate(Mechanical, project_id=PROJECT)
    assert result.ok
    components = [
        e for e in result.snapshot.entities.values() if isinstance(e, Component)
    ]
    assert len(components) == 1
    assert not [e for e in result.snapshot.entities.values() if isinstance(e, PinEntity)]


def test_the_designator_prefix_reaches_the_entity():
    class Board(System):
        r = Resistor(resistance=10 * kOhm)

    result = elaborate(Board, project_id=PROJECT)
    component = next(
        e for e in result.snapshot.entities.values() if isinstance(e, Component)
    )
    assert component.extensions["designator_prefix"] == "R"


def test_a_selected_part_carries_its_vendor_identity_to_the_entity():
    class Board(System):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.r.select("Yageo", "RC0603FR-0710KL")

        r = Resistor(resistance=10 * kOhm)

    result = elaborate(Board, project_id=PROJECT)
    component = next(
        e for e in result.snapshot.entities.values() if isinstance(e, Component)
    )
    assert component.extensions["mpn"] == "RC0603FR-0710KL"
