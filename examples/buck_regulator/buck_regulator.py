"""A 12 V to 3.3 V buck converter, with the reasoning kept beside the circuit.

The circuit is ordinary. What is not ordinary is that the requirement, the part
decision, the datasheet numbers behind it, the two calculations, and the
verification that closes the requirement are all entities in the same graph as
the inductor — so `fang` can answer "why is this 4.7 uH?" without anyone having
written a design document.
"""

from fang.interfaces import AnalogIn, Pin, PinMap, PowerIn, PowerOut
from fang.lang import (
    A,
    Electrical,
    Parameter,
    Part,
    Signal,
    System,
    UnitLiteral,
    V,
    kHz,
    kOhm,
    mA,
    mOhm,
    mV,
    mW,
    nF,
    require,
    uF,
    uH,
)
from fang.parts import Capacitor, Diode, Fuse, Inductor, Resistor
from fang.rationale import Calculates, Chooses, Cites, Requires, Verifies

#: Dimensionless, for the divider ratio.
ratio = UnitLiteral("1")


class BuckController(Part):
    """A synchronous buck IC: it switches, and it compares against a reference.

    The output voltage is nowhere on this part. It is set by the divider on the
    board, which is why the divider carries the constraint that produces it.
    """

    designator_prefix = "U"

    vin = PowerIn(voltage=12 * V, current_demand=1500 * mA)
    sw = Electrical()
    boot = Electrical()
    feedback = AnalogIn(voltage=800 * mV)
    enable = Signal()

    input_voltage_max = Parameter("V")
    reference_voltage = Parameter("V", description="what feedback is compared against")
    switching_frequency = Parameter("Hz")
    output_current_max = Parameter("A")

    VIN = Pin("VIN", role="power", number="1")
    GND = Pin("GND", role="ground", number="2")
    SW = Pin("SW", role="unknown", number="3")
    BOOT = Pin("BOOT", role="unknown", number="4")
    FB = Pin("FB", role="analog", number="5")
    EN = Pin("EN", role="control", number="6")

    pinmap = PinMap(
        {
            "vin.vcc": "VIN",
            "vin.gnd": "GND",
            "sw.line": "SW",
            "boot.line": "BOOT",
            "feedback.signal": "FB",
            "enable.line": "EN",
        }
    )


class InputTerminal(Part):
    """Where the unregulated supply lands."""

    designator_prefix = "J"

    dc = PowerOut(voltage=12 * V, current_capability=2 * A)

    VIN = Pin("VIN", role="power", number="1")
    GND = Pin("GND", role="ground", number="2")

    pinmap = PinMap({"dc.vcc": "VIN", "dc.gnd": "GND"})


class RailHeader(Part):
    """Where the 3V3 rail leaves for the rest of the board."""

    designator_prefix = "J"

    dc = PowerIn(voltage=3.3 * V, current_demand=1500 * mA)

    VCC = Pin("3V3", role="power", number="1")
    GND = Pin("GND", role="ground", number="2")

    pinmap = PinMap({"dc.vcc": "3V3", "dc.gnd": "GND"})


class Rail3V3(System):
    """The rail, and the argument for it."""

    # -- what the board has to do -----------------------------------------
    rail_tolerance = Requires(
        "The 3V3 rail holds 3.3 V within 3% for 0 to 1.5 A over a 6 to 15 V input",
        priority="MUST",
        validation="analysis",
    )

    part_choice = Chooses(
        "Which converter makes the 3V3 rail?",
        selected="TPS62130",
        alternatives=[
            {"part": "LM2596", "reason": "asynchronous, and too tall for the enclosure"},
            {"part": "MP2315", "reason": "no power-good output, and the sequencing needs one"},
        ],
        requirements=("rail_tolerance",),
        evidence=("absolute_maximum",),
        rationale=(
            "17 V absolute maximum against a 15 V worst case input",
            "3 A capability against a 1.5 A load, so the part is not the limit",
        ),
    )

    absolute_maximum = Cites(
        "VIN absolute maximum is 17 V, recommended operating is 3 to 17 V",
        document="SRC-DS-TPS62130",
        locator="section 6.1, absolute maximum ratings",
    )
    ripple_current = Cites(
        "Recommended inductor ripple is 20 to 40% of the maximum output current",
        document="SRC-DS-TPS62130",
        locator="section 9.2.2.1, inductor selection",
    )

    # -- the two numbers that were computed, and from what ------------------
    inductor_value = Calculates(
        "L = v_out * (1 - v_out / v_in) / (f_sw * ripple_current)",
        inputs=("inductor", "controller"),
        result="4.7 uH at 1.25 MHz for 30% ripple at 1.5 A",
        requirements=("rail_tolerance",),
    )
    divider_ratio = Calculates(
        "v_out = v_ref * (1 + top / bottom)",
        inputs=("fb_top", "fb_bottom"),
        result="3.3 V from a 0.8 V reference at 3.125",
        requirements=("rail_tolerance",),
    )

    # -- the circuit --------------------------------------------------------
    supply = PowerIn(voltage=12 * V, current_capability=2 * A)
    rail = PowerOut(voltage=3.3 * V, current_capability=1500 * mA)

    # The rail's 3% tolerance, carried back through the divider and declared as
    # parameters so the comparison has a named thing on its left-hand side.
    divider_min = Parameter("", default=3.03 * ratio)
    divider_max = Parameter("", default=3.22 * ratio)

    dc_in = InputTerminal(package="TerminalBlock_1x02_P5.08mm")
    rail_out = RailHeader(package="PinHeader_1x02_P2.54mm")

    protection = Fuse(current_rating=2 * A, voltage_rating=60 * V, package="F_1206")
    reverse = Diode(
        reverse_voltage=100 * V,
        forward_voltage=550 * mV,
        forward_current=3 * A,
        package="SMA",
    )

    controller = BuckController(
        input_voltage_max=17 * V,
        reference_voltage=800 * mV,
        switching_frequency=1250 * kHz,
        output_current_max=3 * A,
        package="VQFN-16",
    )

    inductor = Inductor(
        inductance=4.7 * uH,
        current_rating=3 * A,
        dc_resistance=45 * mOhm,
        package="L_4x4mm",
    )

    input_bulk = Capacitor(capacitance=22 * uF, voltage_rating=50 * V, package="C_1210")
    output_bulk = Capacitor(capacitance=22 * uF, voltage_rating=16 * V, package="C_1206")
    boot_cap = Capacitor(capacitance=100 * nF, voltage_rating=16 * V, package="C_0402")

    fb_top = Resistor(resistance=200 * kOhm, power_rating=63 * mW, package="R_0402")
    fb_bottom = Resistor(resistance=64 * kOhm, power_rating=63 * mW, package="R_0402")

    # -- and what closes the requirement -------------------------------------
    load_regulation = Verifies(
        "rail_tolerance",
        method="analysis",
        evidence=("absolute_maximum", "ripple_current"),
        result="PASS",
    )

    def __init__(self, **overrides):
        super().__init__(**overrides)
        self.controller.select(
            "TI",
            "TPS62130RGTR",
            distributor_ids={"lcsc": "C77378"},
            datasheet="SRC-DS-TPS62130",
        )

    def architecture(self):
        # The system's declared edges, and the connectors that realize them.
        self.supply >> self.dc_in.dc
        self.rail_out.dc >> self.rail

        self.dc_in.dc.vcc >> self.protection.p1
        self.protection.p2 >> self.reverse.p1
        self.reverse.p2 >> self.controller.vin.vcc
        self.dc_in.dc.gnd >> self.controller.vin.gnd

        self.controller.vin.vcc >> self.input_bulk.p1
        self.controller.vin.gnd >> self.input_bulk.p2

        # The switching node: the one net on this board whose loop area matters
        # more than its schematic.
        self.controller.sw >> self.inductor.p1
        self.controller.sw >> self.boot_cap.p1
        self.boot_cap.p2 >> self.controller.boot

        self.inductor.p2 >> self.rail_out.dc.vcc
        self.rail_out.dc.vcc >> self.output_bulk.p1
        self.rail_out.dc.gnd >> self.output_bulk.p2

        # The divider that actually sets the output, tapped back to feedback.
        self.rail_out.dc.vcc >> self.fb_top.p1
        self.fb_top.p2 >> self.controller.feedback.signal
        self.fb_top.p2 >> self.fb_bottom.p1
        self.fb_bottom.p2 >> self.rail_out.dc.gnd

    def constraints(self):
        # The part has to clear the 15 V worst case, not the 12 V nominal.
        require(self.controller.input_voltage_max >= 16 * V)
        require(self.controller.output_current_max >= 1500 * mA)

        # 20 to 40% ripple at 1.25 MHz puts the inductor between these bounds.
        # Both come from the cited selection procedure, not from a preference.
        require(self.inductor.inductance >= 3.3 * uH)
        require(self.inductor.inductance <= 10 * uH)
        require(self.inductor.current_rating >= 2 * A)

        # (1 + top / bottom) = 4.125 gives 3.3 V from a 0.8 V reference, so the
        # ratio itself is what has to hold when either resistor is substituted.
        division = self.fb_top.resistance / self.fb_bottom.resistance
        require(self.divider_max >= division)
        require(self.divider_min <= division)

        # The input capacitor sees the input, and a hot-plugged supply rings.
        require(self.input_bulk.voltage_rating >= 25 * V)
        require(self.output_bulk.voltage_rating >= 10 * V)
