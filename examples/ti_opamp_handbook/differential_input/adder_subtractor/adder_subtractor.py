"""The adder-subtractor, or floating input combiner, SBOA092B page 68.

    E_O = -E1 - E2 + E3 + E4

E1 and E2 each reach the inverting input through a 10 kOhm R, with a third R
from the output back to it. E3 and E4 each reach the non-inverting input
through a 10 kOhm R_I, and a third R_I runs from that input to ground.

The printed result is not the obvious one, because the two sides are not
alike: the - side has two inputs and a feedback resistor, the + side two
inputs and a resistor to ground. It holds because the numbers happen to meet.
The + input sits at the average of E3, E4 and ground, (E3 + E4)/3, and the
noise gain of the - side is 1 + R/(R || R) = 3, so each + input is worth
exactly 1 at the output. With R and R_I each three equal resistors, the ratio
between R and R_I does not matter, which is what the page means by "R and R_I
not necessarily equal". The program writes each input's weight from the
resistors, so a fourth input on either side, which would break the 3 x 1/3,
would fail the check.

The figure gives every value, so nothing was chosen. The bench drives each
input alone, then all four at once with distinct voltages.
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
    parallel,
    product,
    ratio,
    total,
)


class AdderSubtractor(System):
    """E1, E2 into the - input; E3, E4 into the + input over a third R_I to ground."""

    figure = Cites(
        "E_O = -E1 - E2 + E3 + E4. R and R_I not necessarily equal",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 68, Adder-Subtractor or Floating Input Combiner",
    )

    a_1 = Parameter("1", default=-1 * ratio, description="E_O / E1, the others at ground")
    a_2 = Parameter("1", default=-1 * ratio, description="E_O / E2, the others at ground")
    a_3 = Parameter("1", default=1 * ratio, description="E_O / E3, the others at ground")
    a_4 = Parameter("1", default=1 * ratio, description="E_O / E4, the others at ground")
    noise_gain = Parameter(
        "1", default=3 * ratio, description="1 + R / (R || R): what the + input is worth"
    )

    e1 = Terminal()
    e2 = Terminal()
    e3 = Terminal()
    e4 = Terminal()
    common = Terminal()
    e_out = Terminal()

    r_1 = Resistor(resistance=10 * kOhm)
    r_2 = Resistor(resistance=10 * kOhm)
    r_feedback = Resistor(resistance=10 * kOhm)
    r_3 = Resistor(resistance=10 * kOhm)
    r_4 = Resistor(resistance=10 * kOhm)
    r_ground = Resistor(resistance=10 * kOhm)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        # The subtracting side: E1 and E2 into the summing point, R back.
        self.e1.probe >> self.r_1.p1
        self.e2.probe >> self.r_2.p1
        self.r_1.p2 >> self.amp.inverting.signal
        self.r_2.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r_feedback.p1
        self.r_feedback.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe

        # The adding side: E3 and E4 into the + input, a third R_I to ground.
        self.e3.probe >> self.r_3.p1
        self.e4.probe >> self.r_4.p1
        self.r_3.p2 >> self.amp.non_inverting.signal
        self.r_4.p2 >> self.amp.non_inverting.signal
        self.amp.non_inverting.signal >> self.r_ground.p1

        # The common terminal the figure draws at the bottom left, and E_O's.
        self.r_ground.p2 >> self.ground.node
        self.common.probe >> self.ground.node

    def constraints(self):
        r, r_i = self.r_feedback.resistance, self.r_ground.resistance

        # The - side: each input is an inverting amplifier of its own.
        require(equals(self.a_1, negative(over(r, self.r_1.resistance))))
        require(equals(self.a_2, negative(over(r, self.r_2.resistance))))

        # The noise gain the + input sees: R over the two input resistors in
        # parallel, plus one.
        require(
            equals(
                self.noise_gain,
                total(1 * ratio, over(r, parallel(self.r_1.resistance, self.r_2.resistance))),
            )
        )

        # The + side: each input divides against the other two resistors in
        # parallel, then the noise gain multiplies it back up.
        require(
            equals(
                self.a_3,
                over(
                    product(parallel(self.r_4.resistance, r_i), self.noise_gain),
                    total(self.r_3.resistance, parallel(self.r_4.resistance, r_i)),
                ),
            )
        )
        require(
            equals(
                self.a_4,
                over(
                    product(parallel(self.r_3.resistance, r_i), self.noise_gain),
                    total(self.r_4.resistance, parallel(self.r_3.resistance, r_i)),
                ),
            )
        )


def _alone(n: int) -> Run:
    drive = {f"e{k}": ("DC 1" if k == n else "DC 0") for k in range(1, 5)}
    return Run(
        f"e{n}_alone",
        OperatingPoint(),
        drive=drive,
        measure={f"gain_e{n}": f"v({{e_out.1}}) / v({{e{n}.1}})"},
        claims=[Claim(f"gain_e{n}", f"a_{n}", within=0.001)],
    )


BENCH = Bench(
    page=68,
    title="Adder-Subtractor or Floating Input Combiner",
    runs=[
        _alone(1),
        _alone(2),
        _alone(3),
        _alone(4),
        Run(
            "all_four",
            OperatingPoint(),
            drive={"e1": "DC 0.1", "e2": "DC 0.2", "e3": "DC 0.4", "e4": "DC 0.8"},
            measure={"e_o": "v({e_out.1})", "e_plus": "v({amp.IN+})"},
            claims=[
                Claim("e_o", 0.9, within=0.001, unit="V",
                      note="-0.1 - 0.2 + 0.4 + 0.8 = 0.9 V"),
                Claim("e_plus", 0.4, within=0.001, unit="V",
                      note="(E3 + E4)/3: the + input sits at the average of E3, E4 and ground"),
            ],
        ),
    ],
)
