"""The double-rolloff a.c. amplifier, SBOA092B page 77.

    "Similar to above."   C_1 R_1 = C_2 R_2

The non-inverting a.c. amplifier above it, rearranged. E_I reaches the +
input through C_2. R_0 (90 kOhm) runs from the output to the - input, C_1
(100 uF) from the - input down to a junction, and R_1 (10 kOhm) from that
junction to ground. R_2 (100 kOhm) returns the + input to the same junction
instead of to ground. In the midband C_1 is a short, the junction follows the
- input, which follows the + input, so almost no signal current flows in R_2:
it is bootstrapped, and the input network no longer rolls off on its own. The
two RC pairs then act together, and the response below the midband falls at
40 dB per decade instead of 20.

Solving the three nodes with an ideal op amp gives

    E_O / E_I = s T_2 (1 + R_1/R_2 + s (R_0 + R_1) C_1)
                / (s^2 T_1 T_2 + s T_2 (1 + R_1/R_2) + 1)

with T_1 = R_1 C_1 and T_2 = R_2 C_2. The page's rule, C_1 R_1 = C_2 R_2, is
not met by the values it draws: T_1 = 100u x 10k = 1 s, T_2 = 1u x 100k =
0.1 s. With T_1 ten times T_2 the denominator's Q is sqrt(T_1 T_2) /
(T_2 (1 + R_1/R_2)) = 2.9, and the response peaks 9.3 dB above the midband
near 0.52 Hz. The program keeps the drawn values (`reading`) and the bench
measures what they do. With equal time constants (C_2 = 10 uF, say) the Q is
0.91 and the peak under 1 dB.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Parameter, System, kOhm, require, s, uF
from fang.parts import Capacitor, Resistor
from fang.rationale import Calculates, Chooses, Cites
from fang.simulation import ACSweep, OperatingPoint

from handbook import (
    Bench,
    Claim,
    Ground,
    OpAmp,
    Run,
    Terminal,
    at_least,
    equals,
    over,
    product,
    ratio,
    total,
)


class DoubleRolloff(System):
    """C_2 onto the + input, R_2 bootstrapped to the C_1 R_1 junction."""

    figure = Cites(
        "Similar to above. C_1 R_1 = C_2 R_2",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 77, Double Rolloff",
    )

    reading = Chooses(
        "The drawn values give C_1 R_1 = 1 s and C_2 R_2 = 0.1 s; which does the program follow?",
        selected="the drawn values, and the rule is recorded as not met",
        alternatives=[
            {
                "option": "change C_2 to 10 uF so that the rule holds",
                "reason": "the figure is the source of truth for values; the rule is the page's intent, and the gap is reported",
            },
        ],
        rationale=(
            "the figure prints 1 uF, 100 kOhm, 100 uF and 10 kOhm",
            "the bench shows what the mismatch costs: a 9.3 dB peak",
        ),
    )

    topology = Chooses(
        "Where do C_1 and R_2 connect?",
        selected=(
            "C_1 from the - input to a junction, R_1 from the junction to "
            "ground, and R_2 from the + input to the junction"
        ),
        alternatives=[
            {
                "reading": "R_2 to ground, as in the circuit above",
                "reason": "the figure brings R_2's lower end across to the C_1 R_1 junction, not to the ground line",
            },
        ],
        rationale=("the dot at the C_1 R_1 junction has R_2's wire arriving from the left",),
    )

    response = Calculates(
        "E_O / E_I = s T_2 (1 + R_1/R_2 + s (R_0 + R_1) C_1) / (s^2 T_1 T_2 + s T_2 (1 + R_1/R_2) + 1)",
        inputs=("r_0", "r_1", "c_1", "r_2", "c_2"),
        result=(
            "10 in the midband; poles at f_0 = 1/(2 pi sqrt(T_1 T_2)) = 0.50 Hz "
            "with Q = 2.9, a peak of 29.2 (9.3 dB over 10) at 0.52 Hz; "
            "40 dB/decade below that down to the zero at 0.0175 Hz, 20 dB/decade below it"
        ),
    )

    a_v = Parameter("1", default=10 * ratio, description="E_O / E_I in the midband")
    t_1 = Parameter("s", default=1 * s, description="R_1 C_1")
    t_2 = Parameter("s", default=0.1 * s, description="R_2 C_2")

    e_in = Terminal()
    e_out = Terminal()
    c_2 = Capacitor(capacitance=1 * uF)
    r_2 = Resistor(resistance=100 * kOhm)
    c_1 = Capacitor(capacitance=100 * uF)
    r_1 = Resistor(resistance=10 * kOhm)
    r_0 = Resistor(resistance=90 * kOhm)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.c_2.p1
        self.c_2.p2 >> self.amp.non_inverting.signal
        self.amp.non_inverting.signal >> self.r_2.p1

        self.amp.inverting.signal >> self.c_1.p1
        self.amp.inverting.signal >> self.r_0.p1
        self.r_0.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe

        # The junction: C_1's lower end, R_2's return, and R_1 to ground.
        self.c_1.p2 >> self.r_1.p1
        self.r_2.p2 >> self.r_1.p1
        self.r_1.p2 >> self.ground.node

    def constraints(self):
        require(
            equals(
                self.a_v,
                over(total(self.r_0.resistance, self.r_1.resistance), self.r_1.resistance),
            )
        )
        require(equals(self.t_1, product(self.r_1.resistance, self.c_1.capacitance)))
        require(equals(self.t_2, product(self.r_2.resistance, self.c_2.capacitance)))
        # Not the printed C_1 R_1 = C_2 R_2: as drawn, T_1 is ten times T_2.
        require(at_least(self.t_1, product(self.t_2, 10 * ratio)))


BENCH = Bench(
    page=77,
    title="Double Rolloff",
    runs=[
        Run(
            "response",
            ACSweep(points=200, start="0.0001", stop="10meg"),
            drive={"e_in": "DC 0 AC 1"},
            measure={
                "gain_1k": "find vm({e_out.1}) at=1k",
                "peak": "max vm({e_out.1}) from=0.01 to=100",
                "g_005": "find vm({e_out.1}) at=0.05",
                "g_015": "find vm({e_out.1}) at=0.15",
                "slope_steep": "20 * log10(g_015 / g_005) / log10(3)",
                "g_0001": "find vm({e_out.1}) at=0.001",
                "g_001": "find vm({e_out.1}) at=0.01",
                "slope_low": "20 * log10(g_001 / g_0001)",
                "f_3db": "when vdb({e_out.1})=16.9897 cross=1",
            },
            claims=[
                Claim("gain_1k", "a_v", within=0.001),
                Claim(
                    "peak",
                    29.21,
                    within=0.005,
                    note=(
                        "9.3 dB above the midband, from the transfer function "
                        "with T_1 = 1 s and T_2 = 0.1 s; the page's rule "
                        "C_1 R_1 = C_2 R_2 would hold it under 1 dB"
                    ),
                ),
                Claim(
                    "slope_steep",
                    40,
                    within=1,
                    absolute=True,
                    note="dB per decade between 0.05 Hz and 0.15 Hz: the double rolloff",
                ),
                Claim(
                    "slope_low",
                    20,
                    within=1.5,
                    absolute=True,
                    note=(
                        "dB per decade from 1 mHz to 10 mHz, below the zero at "
                        "(1 + R_1/R_2) / (2 pi (R_0 + R_1) C_1) = 17.5 mHz, "
                        "where the response is back to a single rolloff"
                    ),
                ),
            ],
            units={"f_3db": "Hz"},
            note=(
                "The sweep has 200 points a decade so the peak, near 0.52 Hz, "
                "is read to better than 0.5%. The -3 dB point, where the gain "
                "first reaches 10 / sqrt 2 on the way up, is not a handbook claim."
            ),
        ),
        Run(
            "dc",
            OperatingPoint(),
            drive={"e_in": "DC 1"},
            measure={"e_out": "v({e_out.1})"},
            claims=[
                Claim(
                    "e_out",
                    0,
                    within=1e-6,
                    absolute=True,
                    unit="V",
                    note="C_2 blocks the 1 V; R_2 and R_1 hold the + input at ground",
                )
            ],
        ),
    ],
)
