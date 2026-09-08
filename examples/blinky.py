"""The smallest program that drives something: an MCU pin, a resistor, an LED.

The board everybody builds first. What it shows is the shape of a Fang program —
declared surfaces, connections between them, and a constraint that states the
engineering intent rather than the answer.
"""

from fang.interfaces import Pin, PinMap, PowerIn
from fang.lang import Ohm, Part, Signal, System, V, mA, mW, nF, require
from fang.parts import LED, Capacitor, Resistor


class MCU(Part):
    """A microcontroller, reduced to the one output this board uses."""

    designator_prefix = "U"

    power = PowerIn(voltage=3.3 * V, current_demand=30 * mA)
    blink = Signal()

    VDD = Pin("VDD", role="power", number="1")
    VSS = Pin("VSS", role="ground", number="8")
    PA5 = Pin("PA5", role="data", number="5")

    pinmap = PinMap({"power.vcc": "VDD", "power.gnd": "VSS", "blink.line": "PA5"})


class Blinky(System):
    supply = PowerIn(voltage=3.3 * V, current_capability=200 * mA)

    mcu = MCU(package="SOIC-8")
    series = Resistor(resistance=330 * Ohm, power_rating=125 * mW, package="R_0603")
    indicator = LED(
        forward_voltage=2 * V, forward_current=10 * mA, package="LED_0603"
    )
    bypass = Capacitor(capacitance=100 * nF, voltage_rating=16 * V, package="C_0402")

    def architecture(self):
        self.supply >> self.mcu.power

        # The pin drives the anode through the series resistor; the cathode
        # returns to the rail's ground rather than to a second ground of its own.
        self.mcu.blink >> self.series.p1
        self.series.p2 >> self.indicator.p1
        self.indicator.p2 >> self.supply.gnd

        # Decoupling belongs to the pin it decouples, so a checker can find it.
        self.mcu.power.vcc >> self.bypass.p1
        self.mcu.power.gnd >> self.bypass.p2

    def constraints(self):
        # (3.3 V - 2.0 V) / 330 Ohm is about 4 mA: visible, and inside what a
        # GPIO will source. Both bounds are stated; neither is computed here.
        require(self.series.resistance >= 150 * Ohm)
        require(self.indicator.forward_current <= 20 * mA)
