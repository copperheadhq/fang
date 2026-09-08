"""A voltage divider with a decoupling capacitor: the smallest real board."""

from fang.lang import Electrical, System, V, kOhm, require, uF
from fang.parts import Capacitor, Resistor


class Divider(System):
    """Two resistors dividing a rail, with a capacitor across the output."""

    supply = Electrical()
    output = Electrical()
    ground = Electrical()

    top = Resistor(resistance=10 * kOhm, package="R_0603_1608Metric")
    bottom = Resistor(resistance=4.7 * kOhm, package="R_0603_1608Metric")
    filter_cap = Capacitor(
        capacitance=100 * uF, voltage_rating=16 * V, package="C_0805_2012Metric"
    )

    def architecture(self):
        self.top.p2 >> self.bottom.p1
        self.bottom.p1 >> self.filter_cap.p1
        self.bottom.p2 >> self.filter_cap.p2

    def constraints(self):
        # A divider that draws more than a milliamp from a sensing rail is
        # usually a mistake; both legs stay well above that.
        require(self.top.resistance >= 1 * kOhm)
        require(self.bottom.resistance >= 1 * kOhm)
