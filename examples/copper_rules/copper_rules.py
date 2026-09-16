"""A 2 A rail that states how wide its copper has to be.

The circuit is as small as a power path gets: a terminal block, a header and a
bulk capacitor. What it is here to show is the layer underneath. The program
declares its board and its stackup, states two rules about the copper on its
supply rail, and those rules reach a router as a generated `.kicad_dru` and come
back decided against a board that was actually laid out.

Two boards sit beside it. `narrow.kicad_pcb` routes the rail at 0.3 mm and
`wide.kicad_pcb` at 0.8 mm; the same rule fails against one and passes against
the other, and neither board is ever a place the width is *recorded*.
"""

from fang.interfaces import Pin, PinMap, PowerIn, PowerOut
from fang.lang import (
    A,
    Part,
    System,
    V,
    declare_board,
    layer,
    mm,
    ozcu,
    require,
    uF,
)
from fang.parts import Capacitor


class InputTerminal(Part):
    """Where the 5 V supply lands."""

    designator_prefix = "J"

    dc = PowerOut(voltage=5 * V, current_capability=2 * A)

    VIN = Pin("VIN", role="power", number="1")
    GND = Pin("GND", role="ground", number="2")

    pinmap = PinMap({"dc.vcc": "VIN", "dc.gnd": "GND"})


class LoadHeader(Part):
    """Where the rail leaves for whatever draws the two amps."""

    designator_prefix = "J"

    dc = PowerIn(voltage=5 * V, current_demand=2 * A)

    VCC = Pin("5V", role="power", number="1")
    GND = Pin("GND", role="ground", number="2")

    pinmap = PinMap({"dc.vcc": "5V", "dc.gnd": "GND"})


class PowerPath(System):
    """Five volts in, five volts out and a rule about the copper between."""

    supply = PowerIn(voltage=5 * V, current_capability=2 * A)

    source = InputTerminal(package="TerminalBlock_1x02_P5.08mm")
    load = LoadHeader(package="PinHeader_1x02_P2.54mm")
    bulk = Capacitor(capacitance=22 * uF, voltage_rating=16 * V, package="C_1206_3216Metric")

    def architecture(self):
        self.supply >> self.source.dc

        self.source.dc.vcc >> self.load.dc.vcc
        self.source.dc.gnd >> self.load.dc.gnd

        self.load.dc.vcc >> self.bulk.p1
        self.load.dc.gnd >> self.bulk.p2

    def constraints(self):
        # An ordinary electrical rule, for contrast: it is checked by the
        # structural constraint class and never reaches a router.
        require(self.bulk.voltage_rating >= 10 * V)

        # Two amps on one-ounce outer copper needs roughly half a millimetre for
        # a ten-degree rise. The rule is about the rail, and it is decided by
        # whatever copper realizes the rail, which is nothing at all until a
        # board exists, and undecided is the honest answer until then.
        require(
            self.supply.physical.trace_width >= 0.5 * mm,
            constraint_class="routing",
            constraint_kind="min_trace_width",
        )

        # The fabricator's floor for one-ounce copper, stated once here rather
        # than typed into the layout tool where nothing could check it.
        require(
            self.supply.physical.clearance >= 0.2 * mm,
            constraint_class="routing",
            constraint_kind="min_clearance",
        )

    def board(self):
        # Declared, not measured: no outline is computed and nothing is placed.
        declare_board(
            outline=[(0, 0), (40, 0), (40, 30), (0, 30)],
            thickness=1.6 * mm,
            layers=[
                layer("F.Cu", copper_weight=1 * ozcu),
                layer("core", function="dielectric", thickness=1.5 * mm),
                layer("B.Cu", copper_weight=1 * ozcu),
            ],
        )
