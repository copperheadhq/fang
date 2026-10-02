"""The voltage summer, SBOA092B page 63.

    E_O = -R_O (E1/R1 + E2/R2 + E3/R3)

Each input drives a current E_n/R_n into the summing point, which the loop
holds at ground, and all of it leaves through R_O, so each input reaches the
output multiplied by -R_O/R_n. The page draws three inputs and a dotted line
above the third for "any number"; the program builds the three drawn.

The figure names the resistors and gives them no values, so `values` records
the set chosen here: R_O = 100 kOhm and R1, R2, R3 = 10, 20 and 50 kOhm, so
that the three weights, -10, -5 and -2, are all different and a swapped input
would show. The bench drives each input alone and reads its weight, then all
three at once and reads the weighted sum.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Parameter, System, kOhm, require
from fang.parts import Resistor
from fang.rationale import Chooses, Cites
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


class VoltageSummer(System):
    """E1, E2, E3 each through its own R_n into the summing point, R_O back."""

    figure = Cites(
        "E_O = -R_O (E1/R1 + E2/R2 + E3/R3 + ...). Thus, each input, E_n, is "
        "multiplied by a factor, -R_O/R_n, before summing",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 63, The Voltage Summer",
    )

    values = Chooses(
        "What are R1, R2, R3 and R_O?",
        selected="R1 10 kOhm, R2 20 kOhm, R3 50 kOhm, R_O 100 kOhm: weights -10, -5, -2",
        alternatives=[
            {
                "option": "all four equal",
                "reason": "that is the adder on the next page, and equal weights cannot "
                "show that each input gets its own",
            },
            {
                "option": "leave them unknown",
                "reason": "a weight nobody can compute is not a claim anything can check",
            },
        ],
        rationale=(
            "the figure names the resistors and gives no values",
            "three different weights, so an input wired to the wrong resistor fails",
            "standard values, and weights that keep E_O inside the swing for inputs "
            "under a volt",
        ),
    )

    a_1 = Parameter("1", default=-10 * ratio, description="-R_O / R1")
    a_2 = Parameter("1", default=-5 * ratio, description="-R_O / R2")
    a_3 = Parameter("1", default=-2 * ratio, description="-R_O / R3")

    e1 = Terminal()
    e2 = Terminal()
    e3 = Terminal()
    common = Terminal()
    e_out = Terminal()

    r_1 = Resistor(resistance=10 * kOhm)
    r_2 = Resistor(resistance=20 * kOhm)
    r_3 = Resistor(resistance=50 * kOhm)
    r_out = Resistor(resistance=100 * kOhm)
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
        r_o = self.r_out.resistance
        require(equals(self.a_1, negative(over(r_o, self.r_1.resistance))))
        require(equals(self.a_2, negative(over(r_o, self.r_2.resistance))))
        require(equals(self.a_3, negative(over(r_o, self.r_3.resistance))))


def _alone(n: int) -> Run:
    drive = {f"e{k}": ("DC 1" if k == n else "DC 0") for k in range(1, 4)}
    return Run(
        f"e{n}_alone",
        OperatingPoint(),
        drive=drive,
        measure={f"gain_e{n}": f"v({{e_out.1}}) / v({{e{n}.1}})"},
        claims=[Claim(f"gain_e{n}", f"a_{n}", within=0.001)],
    )


BENCH = Bench(
    page=63,
    title="The Voltage Summer",
    runs=[
        _alone(1),
        _alone(2),
        _alone(3),
        Run(
            "all_three",
            OperatingPoint(),
            drive={"e1": "DC 0.5", "e2": "DC 0.3", "e3": "DC -0.4"},
            measure={
                "e_o": "v({e_out.1})",
                "summing_point": "v({amp.IN-})",
                "i_o": "(v({amp.IN-}) - v({e_out.1})) / 100k",
                "i_in": "-(i(vdrive_e1) + i(vdrive_e2) + i(vdrive_e3))",
            },
            claims=[
                Claim("e_o", -5.7, within=0.001, unit="V",
                      note="-(10 x 0.5 + 5 x 0.3 + 2 x (-0.4)) = -5.7 V"),
                Claim("summing_point", 0, within=0.00001, absolute=True, unit="V",
                      note=(
                          "Pin (1), the summing point, at ground: the page's first "
                          "restraint. It sits at -E_O over the open-loop gain, 5.7 uV."
                      )),
                Claim("i_o", 57e-6, within=0.001, unit="A",
                      note="I_O = -E_O/R_O, the current through R_O"),
                Claim("i_in", 57e-6, within=0.001, unit="A",
                      note="I1 + I2 + I3: the page's second restraint, -I_O + I1 + I2 + I3 = 0"),
            ],
        ),
    ],
)
