"""The lag element, SBOA092B page 84.

    E_O = -(R_O / R_I) E_I / (1 + R_O C_O P) = -10 E_I / (10 + P)

An inverting amplifier with C_O across R_O: a DC gain of -R_O/R_I and one
pole where C_O's reactance equals R_O. The figure draws R_I = 1 MOhm,
R_O = 10 kOhm and C_O = 10 uF.

The printed right-hand side does not follow from the drawn values.
R_O C_O = 0.1 s, so the pole at 10 rad/s agrees, but -10/(10 + P) has a DC
gain of -1, and R_O/R_I = 10k/1M = 0.01. The drawn circuit is
-0.01/(1 + 0.1 P) = -0.1/(10 + P). The printed form is true for R_I = 10 kOhm
(or R_I and R_O both 1 MOhm with C_O = 0.1 uF); no single swap of the drawn
values gives it, since swapping R_I and R_O makes a gain of -100 and a pole
at 0.1 rad/s. `reading` records that the program keeps the drawn values and
claims what they do: a gain of -0.01 and a corner at 1.59 Hz.
"""

import sys
from decimal import Decimal
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Hz, MOhm, Parameter, System, kOhm, require, uF
from fang.parts import Capacitor, Resistor
from fang.rationale import Chooses, Cites
from fang.simulation import ACSweep, OperatingPoint

from handbook import (
    Bench,
    Claim,
    Ground,
    OpAmp,
    Run,
    Terminal,
    corner,
    equals,
    negative,
    over,
    ratio,
    within,
)


class LagElement(System):
    """E_I through R_I into the summing point, R_O and C_O side by side back from the output."""

    figure = Cites(
        "E_O = -(R_O / R_I) E_I / (1 + R_O C_O P) = -10 E_I / (10 + P); "
        "integrating type phase lag",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 84, Lag Element",
    )

    reading = Chooses(
        "The drawn values give -0.01/(1 + 0.1 P); the page prints -10/(10 + P), a DC gain of -1. Which is simulated?",
        selected=(
            "the drawn values, R_I 1 MOhm, R_O 10 kOhm, C_O 10 uF: a DC gain "
            "of -0.01 and a corner at 10 rad/s, 1.59 Hz"
        ),
        alternatives=[
            {
                "option": "R_I = 10 kOhm, which makes the printed -10/(10 + P) true",
                "reason": (
                    "it is the likeliest intent, but it changes a value the "
                    "figure prints; the program simulates what is drawn and "
                    "says where the formula parts from it"
                ),
            },
            {
                "option": "R_I and R_O swapped",
                "reason": (
                    "1 MOhm across 10 uF is a 10 s time constant and a gain "
                    "of -100: -100/(1 + 10 P), further from the printed form "
                    "than the drawing is"
                ),
            },
        ],
        rationale=(
            "R_O C_O = 0.1 s agrees with the printed pole at P = -10, so "
            "the lag is right and only the gain is off",
            "-10/(10 + P) needs R_O/R_I = 1; 10k/1M is 0.01",
        ),
    )

    a_v = Parameter("1", default=-0.01 * ratio, description="E_O / E_I at DC")
    f_c = Parameter(
        "Hz", default=Decimal("1.59155") * Hz, description="the lag's corner, 1/(2 pi R_O C_O)"
    )

    e_in = Terminal()
    e_out = Terminal()
    r_in = Resistor(resistance=1 * MOhm)
    r_out = Resistor(resistance=10 * kOhm)
    c_out = Capacitor(capacitance=10 * uF)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.r_in.p1
        self.r_in.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r_out.p1
        self.amp.inverting.signal >> self.c_out.p1
        self.r_out.p2 >> self.amp.output.signal
        self.c_out.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe
        self.amp.non_inverting.signal >> self.ground.node

    def constraints(self):
        # At DC the capacitor is open and this is the inverting amplifier.
        require(equals(self.a_v, negative(over(self.r_out.resistance, self.r_in.resistance))))
        # The pole: where C_O takes the feedback current from R_O.
        require(within(self.f_c, corner(self.r_out.resistance, self.c_out.capacitance), 0.0001))


BENCH = Bench(
    page=84,
    title="Lag Element",
    runs=[
        Run(
            "dc_gain",
            OperatingPoint(),
            drive={"e_in": "DC 1"},
            measure={"gain": "v({e_out.1}) / v({e_in.1})"},
            claims=[
                Claim(
                    "gain",
                    "a_v",
                    within=0.001,
                    note=(
                        "the page's -10/(10 + P) has a DC gain of -1; with the "
                        "drawn 1 MOhm in and 10 kOhm across it is -0.01"
                    ),
                )
            ],
        ),
        Run(
            "corner",
            ACSweep(points=200, start="10m", stop="1k"),
            drive={"e_in": "DC 0 AC 1"},
            measure={
                "gain_low": "find vm({e_out.1}) at=10m",
                "f_3db": "when vdb({e_out.1})=-43.0103 fall=1",
            },
            claims=[
                Claim("gain_low", 0.01, within=0.001, note="|a_v|, a decade and more below the corner"),
                Claim(
                    "f_3db",
                    "f_c",
                    within=0.005,
                    unit="Hz",
                    note="10 rad/s, the pole the page prints, which the drawn R_O C_O = 0.1 s does give",
                ),
            ],
            note="The -3 dB point is 3.0103 dB under the DC gain of -40 dB.",
        ),
    ],
)
