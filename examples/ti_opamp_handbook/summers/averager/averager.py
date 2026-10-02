"""The averager, SBOA092B page 65.

    E_O = -(R_O/R_I)(E1 + E2 + E3) = -(E1 + E2 + E3)/3

The adder with each input resistor made three times R_O: three 30 kOhm R_I
into the summing point, 10 kOhm back. Each input is weighted -1/3, so the
output is the inverted average. The page's rule is R_O = R_I divided by the
number of inputs, and the program holds the parts to it with the count as a
parameter, which is also the divisor the bench measures.

The next page adds: ground unused inputs to preserve scale. The bench tries
both. In this inverting circuit a grounded input and an open one give the same
E_O, because the summing point is at ground either way and an open R_I carries
no current just as a grounded one does: the unused input counts as a zero in
the average and the divisor stays 3. What grounding changes is the noise
gain, 1 + R_O/(R_I/3) = 2 against 1 + R_O/(R_I/2) = 1.67, which moves the
output offset and bandwidth, not the scale.

The figure gives every value, so nothing was chosen.
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
    product,
    ratio,
)


class Averager(System):
    """E1, E2, E3 each through 30 kOhm into the summing point, 10 kOhm back."""

    figure = Cites(
        "E_O = -R_O/R_I (E1 + E2 + E3) = -(E1 + E2 + E3)/3. R_O = R_I divided by "
        "number of inputs. Output is inverted average of input signals. Ground "
        "unused inputs to preserve scale",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="pages 65 and 66, Averager",
    )

    inputs = Parameter("1", default=3 * ratio, description="how many inputs are averaged")

    e1 = Terminal()
    e2 = Terminal()
    e3 = Terminal()
    common = Terminal()
    e_out = Terminal()

    r_1 = Resistor(resistance=30 * kOhm)
    r_2 = Resistor(resistance=30 * kOhm)
    r_3 = Resistor(resistance=30 * kOhm)
    r_out = Resistor(resistance=10 * kOhm)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e1.probe >> self.r_1.p1
        self.e2.probe >> self.r_2.p1
        self.e3.probe >> self.r_3.p1
        self.r_1.p2 >> self.amp.inverting.signal
        self.r_2.p2 >> self.amp.inverting.signal
        self.r_3.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r_out.p1
        self.r_out.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe
        self.amp.non_inverting.signal >> self.ground.node
        self.common.probe >> self.ground.node

    def constraints(self):
        # R_O = R_I / n, written without the division so it is exact: n R_O = R_I.
        for r_i in (self.r_1, self.r_2, self.r_3):
            require(equals(product(self.inputs, self.r_out.resistance), r_i.resistance))


BENCH = Bench(
    page=65,
    title="Averager",
    runs=[
        Run(
            "average",
            OperatingPoint(),
            drive={"e1": "DC 1", "e2": "DC 2", "e3": "DC 4.5"},
            measure={
                "e_o": "v({e_out.1})",
                "divisor": "-(v({e1.1}) + v({e2.1}) + v({e3.1})) / v({e_out.1})",
            },
            claims=[
                Claim("e_o", -2.5, within=0.001, unit="V",
                      note="-(1 + 2 + 4.5)/3 = -2.5 V"),
                Claim("divisor", "inputs", within=0.001,
                      note="-(E1 + E2 + E3)/E_O: the number of inputs"),
            ],
        ),
        Run(
            "unused_input_grounded",
            OperatingPoint(),
            drive={"e1": "DC 1", "e2": "DC 2", "e3": "DC 0"},
            measure={"e_o": "v({e_out.1})"},
            claims=[
                Claim("e_o", -1.0, within=0.001, unit="V",
                      note=(
                          "E3 grounded: -(1 + 2 + 0)/3 = -1 V. The scale is kept, "
                          "and the grounded input counts as a zero in the average."
                      )),
            ],
        ),
        Run(
            "unused_input_open",
            OperatingPoint(),
            drive={"e1": "DC 1", "e2": "DC 2"},
            measure={"e_o": "v({e_out.1})", "e3_open": "v({e3.1})"},
            claims=[
                Claim("e_o", -1.0, within=0.001, unit="V",
                      note=(
                          "E3 left open gives the same -1 V: the open R_I sits at the "
                          "summing point's ground and carries nothing. The page's "
                          "advice does not change the scale of this circuit."
                      )),
            ],
            units={"e3_open": "V"},
        ),
    ],
)
