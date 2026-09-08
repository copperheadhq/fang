"""Values chosen by equation: a divider stated as the ratio it must satisfy.

The resistors carry real values, but the values are not the design — the
constraints are. Ohm's law is written down as a constraint rather than left in a
comment, so substituting a part re-checks the arithmetic instead of trusting it.

Inheritance is how a second divider reuses the first: `SenseDivider` keeps the
equations and replaces the two values. A block owns its interior — its parts, its
parameters, and the constraints over them — and the board connects to the pads at
its edge.
"""

from fang.interfaces import AnalogIn, Pin, PinMap, PowerIn, PowerOut
from fang.lang import (
    MOhm,
    Module,
    Parameter,
    Part,
    System,
    UnitLiteral,
    V,
    kOhm,
    mA,
    mW,
    require,
    tolerance,
    uA,
)
from fang.parts import Resistor

#: A dimensionless literal, so a ratio is a quantity like every other number.
#: A project adds its own units this way rather than editing the language.
ratio = UnitLiteral("1")


class FeedbackDivider(Module):
    """Two resistors and the four facts that make them the right two."""

    v_in = Parameter("V", description="the rail being divided")
    i_bleed = Parameter("A", description="the most the leg may draw from it")
    ratio_min = Parameter("", description="lower bound on tap / rail")
    ratio_max = Parameter("", description="upper bound on tap / rail")

    top = Resistor(
        resistance=tolerance(82 * kOhm, "1%"), power_rating=100 * mW, package="R_0402"
    )
    bottom = Resistor(
        resistance=tolerance(22 * kOhm, "1%"), power_rating=100 * mW, package="R_0402"
    )

    def architecture(self):
        # The interior: the tap is the node between the two legs.
        self.top.p2 >> self.bottom.p1

    def constraints(self):
        division = self.bottom.resistance / (
            self.top.resistance + self.bottom.resistance
        )
        # The reference is on the left of every comparison because a parameter
        # is what the expression is being judged against.
        require(self.ratio_max >= division)
        require(self.ratio_min <= division)

        # Ohm's law, as a constraint: v_in <= i_bleed * R_total is the same
        # statement as "the leg draws no more than i_bleed", and it survives a
        # change to either resistor.
        require(
            self.v_in <= self.i_bleed * (self.top.resistance + self.bottom.resistance)
        )

        # A leg stiff enough to ignore the tap's input current, and not so stiff
        # that board leakage competes with it.
        require(self.top.resistance <= 1 * MOhm)
        require(self.top.resistance >= 10 * kOhm)


class SenseDivider(FeedbackDivider):
    """The same equations, an eighth of the ratio: 24 V onto a 3.3 V ADC."""

    top = Resistor(
        resistance=tolerance(180 * kOhm, "1%"), power_rating=100 * mW, package="R_0402"
    )
    bottom = Resistor(
        resistance=tolerance(20 * kOhm, "1%"), power_rating=100 * mW, package="R_0402"
    )


class ADC(Part):
    """A two-channel converter. Its inputs are analog, and typed as analog."""

    designator_prefix = "U"

    power = PowerIn(voltage=3.3 * V, current_demand=2 * mA)
    channel_a = AnalogIn(voltage=3.3 * V, impedance=1 * MOhm)
    channel_b = AnalogIn(voltage=3.3 * V, impedance=1 * MOhm)

    VDD = Pin("VDD", role="power", number="1")
    GND = Pin("GND", role="ground", number="2")
    AIN0 = Pin("AIN0", role="analog", number="3")
    AIN1 = Pin("AIN1", role="analog", number="4")

    pinmap = PinMap(
        {
            "power.vcc": "VDD",
            "power.gnd": "GND",
            "channel_a.signal": "AIN0",
            "channel_b.signal": "AIN1",
        }
    )


class TerminalBlock(Part):
    """The board's edge: two measured rails, the logic supply, one return."""

    designator_prefix = "J"

    rail_a = PowerOut(voltage=12 * V, current_capability=2000 * mA)
    rail_b = PowerOut(voltage=24 * V, current_capability=2000 * mA)
    logic = PowerOut(voltage=3.3 * V, current_capability=100 * mA)

    V12 = Pin("12V", role="power", number="1")
    V24 = Pin("24V", role="power", number="2")
    V3V3 = Pin("3V3", role="power", number="3")
    GND = Pin("GND", role="ground", number="4")

    pinmap = PinMap(
        {
            "rail_a.vcc": "12V",
            "rail_a.gnd": "GND",
            "rail_b.vcc": "24V",
            "rail_b.gnd": "GND",
            "logic.vcc": "3V3",
            "logic.gnd": "GND",
        }
    )


class MeasuredRail(System):
    """A 12 V rail and a 24 V rail, both measured by the same converter."""

    terminals = TerminalBlock(package="TerminalBlock_1x04_P5.08mm")

    feedback = FeedbackDivider(
        v_in=12 * V,
        i_bleed=250 * uA,
        ratio_min=0.19 * ratio,
        ratio_max=0.23 * ratio,
    )
    sense = SenseDivider(
        v_in=24 * V,
        i_bleed=200 * uA,
        ratio_min=0.09 * ratio,
        ratio_max=0.11 * ratio,
    )
    adc = ADC(package="MSOP-10")

    def architecture(self):
        self.terminals.logic >> self.adc.power

        self.terminals.rail_a.vcc >> self.feedback.top.p1
        self.terminals.rail_a.gnd >> self.feedback.bottom.p2
        self.terminals.rail_b.vcc >> self.sense.top.p1
        self.terminals.rail_b.gnd >> self.sense.bottom.p2

        self.feedback.top.p2 >> self.adc.channel_a.signal
        self.sense.top.p2 >> self.adc.channel_b.signal
