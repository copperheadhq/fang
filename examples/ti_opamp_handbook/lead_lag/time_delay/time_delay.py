"""The time delay, SBOA092B page 86.

    "Unity gain phase or time shift"

An inverting stage built to approximate a pure delay. The input is a ladder,
R/6, 3.6 C to ground, 2R/3, 3.6 C to ground, R/6 into the summing point; the
feedback is R in parallel with a T of 0.8 C, 0.8 C with R/4 to ground from
their junction. At DC the capacitors are open: R/6 + 2R/3 + R/6 = R in, R
across, a gain of -1. The page's sketch shows a step coming out inverted,
starting after about RC and completing its rise over about 1.1 RC.

The figure gives R and C only as symbols. `values` records the pair chosen
here: R = 60 kOhm, so each fraction of it is a round number, and
C = 10 nF, so RC = 600 us.
"""

import sys
from decimal import Decimal
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Parameter, System, kOhm, nF, require, us
from fang.parts import Capacitor, Resistor
from fang.rationale import Chooses, Cites
from fang.simulation import OperatingPoint, Transient

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
    product,
    ratio,
    total,
)


class TimeDelay(System):
    """An RC ladder in, R across with a capacitor T beside it."""

    figure = Cites(
        "Unity gain phase or time shift; E_O follows the E_I step, delayed by RC, "
        "rising over 1.1 RC",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 86, Time Delay",
    )

    values = Chooses(
        "What are R and C?",
        selected="R = 60 kOhm and C = 10 nF, RC = 600 us",
        alternatives=[
            {
                "option": "R = 10 kOhm",
                "reason": "R/6 and 2R/3 would be 1.667 k and 6.667 k, values nobody stocks",
            },
            {
                "option": "leave them symbolic",
                "reason": "a delay nobody can compute is not a claim anything can check",
            },
        ],
        rationale=(
            "the figure gives every part as a multiple of R or C and no values",
            "60 kOhm makes R/6, 2R/3 and R/4 10k, 40k and 15k",
        ),
    )

    r = Parameter("Ohm", default=60 * kOhm, description="the page's R")
    c = Parameter("F", default=10 * nF, description="the page's C")
    rc = Parameter("s", default=600 * us, description="R C, the delay the sketch marks")
    rise = Parameter("s", default=660 * us, description="1.1 R C, the rise the sketch marks")
    a_v = Parameter("1", default=-1 * ratio, description="E_O / E_I at DC")

    e_in = Terminal()
    e_out = Terminal()
    r_in1 = Resistor(resistance=10 * kOhm)
    c_in1 = Capacitor(capacitance=36 * nF)
    r_in2 = Resistor(resistance=40 * kOhm)
    c_in2 = Capacitor(capacitance=36 * nF)
    r_in3 = Resistor(resistance=10 * kOhm)
    r_fb = Resistor(resistance=60 * kOhm)
    c_fb1 = Capacitor(capacitance=8 * nF)
    c_fb2 = Capacitor(capacitance=8 * nF)
    r_tee = Resistor(resistance=15 * kOhm)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        # The input ladder.
        self.e_in.probe >> self.r_in1.p1
        self.r_in1.p2 >> self.c_in1.p1
        self.r_in1.p2 >> self.r_in2.p1
        self.r_in2.p2 >> self.c_in2.p1
        self.r_in2.p2 >> self.r_in3.p1
        self.r_in3.p2 >> self.amp.inverting.signal
        self.c_in1.p2 >> self.ground.node
        self.c_in2.p2 >> self.ground.node
        # The feedback: R, and the capacitor T beside it.
        self.amp.inverting.signal >> self.r_fb.p1
        self.r_fb.p2 >> self.amp.output.signal
        self.amp.inverting.signal >> self.c_fb1.p1
        self.c_fb1.p2 >> self.c_fb2.p1
        self.c_fb2.p2 >> self.amp.output.signal
        self.c_fb1.p2 >> self.r_tee.p1
        self.r_tee.p2 >> self.ground.node
        self.amp.output.signal >> self.e_out.probe
        self.amp.non_inverting.signal >> self.ground.node

    def constraints(self):
        # Every part is the fraction of R or C the figure labels it with.
        require(equals(self.r_in1.resistance, over(self.r, 6 * ratio)))
        require(equals(self.r_in2.resistance, over(product(2 * ratio, self.r), 3 * ratio)))
        require(equals(self.r_in3.resistance, over(self.r, 6 * ratio)))
        require(equals(self.r_fb.resistance, self.r))
        require(equals(self.r_tee.resistance, over(self.r, 4 * ratio)))
        for part in (self.c_in1, self.c_in2):
            require(equals(part.capacitance, product(Decimal("3.6") * ratio, self.c)))
        for part in (self.c_fb1, self.c_fb2):
            require(equals(part.capacitance, product(Decimal("0.8") * ratio, self.c)))
        require(equals(self.rc, product(self.r, self.c)))
        require(equals(self.rise, product(Decimal("1.1") * ratio, self.rc)))
        # At DC: the ladder's three resistors in, R across.
        require(
            equals(
                self.a_v,
                negative(
                    over(
                        self.r_fb.resistance,
                        total(self.r_in1.resistance, self.r_in2.resistance, self.r_in3.resistance),
                    )
                ),
            )
        )


BENCH = Bench(
    page=86,
    title="Time Delay",
    runs=[
        Run(
            "dc_gain",
            OperatingPoint(),
            drive={"e_in": "DC 1"},
            measure={"gain": "v({e_out.1}) / v({e_in.1})"},
            claims=[Claim("gain", "a_v", within=0.001)],
        ),
        Run(
            "step",
            Transient(stop="5m", step="1u"),
            drive={"e_in": "PULSE(0 1 0 1n 1n 1 2)"},
            measure={
                "t10": "when v({e_out.1})=-0.1 fall=1",
                "t50": "when v({e_out.1})=-0.5 fall=1",
                "t90": "when v({e_out.1})=-0.9 fall=1",
                "rise": "t90 - t10",
                "final": "find v({e_out.1}) at=4.9m",
                "overshoot": "min v({e_out.1}) from=0 to=5m",
            },
            claims=[
                Claim(
                    "t50",
                    "rc",
                    within=0.05,
                    unit="s",
                    note=(
                        "the 50% point of the inverted step, against the RC the "
                        "sketch marks; the page draws the delay and prints no formula, "
                        "so the claim is held to 5%"
                    ),
                ),
                Claim(
                    "rise",
                    "rise",
                    within=0.05,
                    unit="s",
                    note="10% to 90%, against the sketch's 1.1 RC, held to 5% for the same reason",
                ),
                Claim("final", "a_v", within=0.001, unit="V", note="a 1 V step settles at -1 V"),
            ],
            units={"t10": "s", "t90": "s", "overshoot": "V"},
            note=(
                "A 1 V step at t = 0. The sketch has the output still until RC "
                "and then moving; the simulated edge is smoother than that, "
                "already 10% of the way at 0.46 RC, but its middle sits at RC "
                "and it takes 1.1 RC from 10% to 90%."
            ),
        ),
    ],
)
