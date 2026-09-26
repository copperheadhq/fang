"""The adder, SBOA092B page 64.

    E_O = -(E1 + E2 + E3),   Z_in = 10 kOhm for each input

Three 10 kOhm resistors bring E1, E2 and E3 to the summing point, and a fourth
10 kOhm runs from the output back to it. Each input is an inverting amplifier
of gain -1 on its own, and because the summing point sits at ground, each
source sees only its own resistor: that is the 10 kOhm the page gives as the
input impedance, and why the inputs do not load one another.

The figure gives every value, so nothing was chosen. The bench drives the
three inputs with distinct voltages at once, reads E_O against their sum, and
reads each input's impedance from the current its source delivers.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Parameter, System, kOhm, require
from fang.parts import Resistor
from fang.rationale import Cites
from fang.simulation import OperatingPoint

from handbook import (
    Bench,
    Claim,
    Ground,
    OpAmp,
    Run,
    Terminal,
    equals,
    negative,
    over,
    ratio,
)


class Adder(System):
    """E1, E2, E3 each through 10 kOhm into the summing point, 10 kOhm back."""

    figure = Cites(
        "E_O = -(E1 + E2 + E3). Z_in = 10 kOhm for each input",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 64, Adder",
    )

    a_v = Parameter("1", default=-1 * ratio, description="E_O / E_n, for each input")
    z_in = Parameter("Ohm", default=10 * kOhm, description="what each source sees")

    e1 = Terminal()
    e2 = Terminal()
    e3 = Terminal()
    common = Terminal()
    e_out = Terminal()

    r_1 = Resistor(resistance=10 * kOhm)
    r_2 = Resistor(resistance=10 * kOhm)
    r_3 = Resistor(resistance=10 * kOhm)
    r_feedback = Resistor(resistance=10 * kOhm)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e1.probe >> self.r_1.p1
        self.e2.probe >> self.r_2.p1
        self.e3.probe >> self.r_3.p1
        self.r_1.p2 >> self.amp.inverting.signal
        self.r_2.p2 >> self.amp.inverting.signal
        self.r_3.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r_feedback.p1
        self.r_feedback.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe
        self.amp.non_inverting.signal >> self.ground.node
        self.common.probe >> self.ground.node

    def constraints(self):
        r_o = self.r_feedback.resistance
        # Each input is an inverting amplifier of its own, all of the same gain.
        for r_n in (self.r_1, self.r_2, self.r_3):
            require(equals(self.a_v, negative(over(r_o, r_n.resistance))))
            # The summing point is a virtual ground, so a source sees its resistor.
            require(equals(self.z_in, r_n.resistance))


BENCH = Bench(
    page=64,
    title="Adder",
    runs=[
        Run(
            "sum",
            OperatingPoint(),
            drive={"e1": "DC 1", "e2": "DC 2", "e3": "DC -0.5"},
            measure={
                "e_o": "v({e_out.1})",
                "sum_gain": "v({e_out.1}) / (v({e1.1}) + v({e2.1}) + v({e3.1}))",
                "z_in_e1": "-v({e1.1}) / i(vdrive_e1)",
                "z_in_e2": "-v({e2.1}) / i(vdrive_e2)",
                "z_in_e3": "-v({e3.1}) / i(vdrive_e3)",
            },
            claims=[
                Claim("e_o", -2.5, within=0.001, unit="V",
                      note="-(1 + 2 - 0.5) = -2.5 V"),
                Claim("sum_gain", "a_v", within=0.001),
                Claim("z_in_e1", "z_in", within=0.001, unit="Ohm"),
                Claim("z_in_e2", "z_in", within=0.001, unit="Ohm"),
                Claim("z_in_e3", "z_in", within=0.001, unit="Ohm"),
            ],
            note=(
                "Each input's impedance is its drive voltage over the current its "
                "source delivers, which flows out of the source's + terminal and so "
                "reads negative in SPICE."
            ),
        ),
    ],
)
