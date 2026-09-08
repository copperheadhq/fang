"""The standard part library.

Spec: "The Part Model" and "The Standard Part Library".

A generic part is a set of facts plus the traits it satisfies. It carries no
vendor identity until one is selected, because inventing a manufacturer for a
resistor nobody has chosen is exactly the "unearned certainty" the standard
exists to prevent.
"""

from __future__ import annotations

from typing import Mapping

from .interfaces import AnalogIn, AnalogOut, Pin, PinMap, PowerIn, PowerOut
from .lang import (
    Electrical,
    Ground,
    Mechanical,
    Parameter,
    Part,
    Power,
    Signal,
)
from .traits import DatasheetEvidence, Footprint, Sourcing


class GenericPart(Part):
    """A library part with no vendor identity yet.

    Everything it needs — package, footprint trait, and vendor selection — now
    lives on `Part`, because every part has those and not only the library's.
    """

    designator_prefix = "U"


class TwoPin(GenericPart):
    """The shape most of a board is made of: two surfaces, two pins."""

    p1 = Electrical()
    p2 = Electrical()
    PIN1 = Pin("1", role="unknown", number="1")
    PIN2 = Pin("2", role="unknown", number="2")
    pinmap = PinMap({"p1.line": "1", "p2.line": "2"})


# --------------------------------------------------------------------------
# Passives
# --------------------------------------------------------------------------


class Resistor(TwoPin):
    designator_prefix = "R"
    resistance = Parameter("Ohm")
    power_rating = Parameter("W")
    tolerance_pct = Parameter("percent")


class Capacitor(TwoPin):
    designator_prefix = "C"
    capacitance = Parameter("F")
    voltage_rating = Parameter("V")
    tolerance_pct = Parameter("percent")


class Inductor(TwoPin):
    designator_prefix = "L"
    inductance = Parameter("H")
    current_rating = Parameter("A")
    dc_resistance = Parameter("Ohm")


class Diode(TwoPin):
    designator_prefix = "D"
    forward_voltage = Parameter("V")
    reverse_voltage = Parameter("V")
    forward_current = Parameter("A")

    # Override the generic two-pin names rather than adding to them, so a diode
    # has an anode and a cathode and not also a pin 1 and a pin 2.
    PIN1 = Pin("A", role="unknown", number="1")
    PIN2 = Pin("K", role="unknown", number="2")
    pinmap = PinMap({"p1.line": "A", "p2.line": "K"})


class LED(Diode):
    designator_prefix = "DS"
    luminous_intensity = Parameter("cd")


class Fuse(TwoPin):
    designator_prefix = "F"
    current_rating = Parameter("A")
    voltage_rating = Parameter("V")


class Crystal(TwoPin):
    designator_prefix = "Y"
    frequency = Parameter("Hz")
    load_capacitance = Parameter("F")
    tolerance_ppm = Parameter("ppm")


# --------------------------------------------------------------------------
# Active parts
# --------------------------------------------------------------------------


class Transistor(GenericPart):
    """A three-terminal switching or amplifying part."""

    designator_prefix = "Q"
    gate = Signal()
    drain = Electrical()
    source = Electrical()

    vds_max = Parameter("V")
    vgs_threshold = Parameter("V")
    id_max = Parameter("A")
    rds_on = Parameter("Ohm")

    G = Pin("G", role="control", number="1")
    D = Pin("D", role="unknown", number="2")
    S = Pin("S", role="unknown", number="3")
    pinmap = PinMap({"gate.line": "G", "drain.line": "D", "source.line": "S"})


class Regulator(GenericPart):
    """A voltage regulator: power in, power out, and the rail it makes."""

    designator_prefix = "U"
    vin = PowerIn()
    vout = PowerOut()

    input_voltage_max = Parameter("V")
    output_voltage = Parameter("V")
    output_current_max = Parameter("A")
    quiescent_current = Parameter("A")
    dropout_voltage = Parameter("V")

    VIN = Pin("VIN", role="power", number="1")
    GND = Pin("GND", role="ground", number="2")
    VOUT = Pin("VOUT", role="power", number="3")
    pinmap = PinMap(
        {
            "vin.vcc": "VIN",
            "vin.gnd": "GND",
            "vout.vcc": "VOUT",
            "vout.gnd": "GND",
        }
    )


class Connector(GenericPart):
    """An external connection surface. Its pin count is declared per instance."""

    designator_prefix = "J"
    shell = Mechanical()
    current_rating = Parameter("A")
    voltage_rating = Parameter("V")


class TestPoint(GenericPart):
    designator_prefix = "TP"
    probe = Electrical()
    TP = Pin("1", role="unknown", number="1")
    pinmap = PinMap({"probe.line": "1"})


class MountingHole(GenericPart):
    """A part with no electrical function that still belongs to the design."""

    designator_prefix = "H"
    mount = Mechanical()
    diameter = Parameter("mm")


# --------------------------------------------------------------------------
# Common compositions
# --------------------------------------------------------------------------


class DecouplingCapacitor(Capacitor):
    """A capacitor whose job is stated, so a checker can find it."""

    designator_prefix = "C"


#: Every part the library ships, for enumeration and for tests that assert the
#: library's membership rather than trusting the module's contents.
LIBRARY = (
    Resistor,
    Capacitor,
    Inductor,
    Diode,
    LED,
    Fuse,
    Crystal,
    Transistor,
    Regulator,
    Connector,
    TestPoint,
    MountingHole,
)
