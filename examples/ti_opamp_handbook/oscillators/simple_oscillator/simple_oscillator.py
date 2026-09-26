"""The simple oscillator, SBOA092B page 83.

    f = 1 / (2 pi R C)

Two T networks run in parallel from the output back to the - input: R, R in
series with 2C from their junction to ground, and C, C in series with R/2
from theirs. Together they are a twin-T notch, and the op amp runs open loop
through it. At d.c. the R-R path feeds the output straight back, which is
negative feedback and holds the circuit still. At 1 / (2 pi R C) a balanced
twin-T passes nothing. Trim the R/2 leg a little low and the transmission at
that frequency turns negative, so the inverting op amp sees its own output
come back in phase: regenerative feedback, and it oscillates there.

The figure gives R and C no values and R/2 no setting, so `values` and
`trim` record what was taken: 10 kOhm and 15.9 nF for 1 kHz, and the R/2 leg
as a 10 kOhm rheostat set to 0.49 of its travel, 4.9 kOhm. Nothing in the
loop limits the amplitude but the op amp's swing, so the output grows until
it clips at the rails and is reported as that.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from decimal import Decimal

from fang.lang import Parameter, System, kHz, kOhm, nF, require
from fang.parts import Capacitor, Resistor
from fang.rationale import Chooses, Cites
from fang.simulation import Transient

from handbook import (
    Bench,
    Claim,
    Ground,
    OpAmp,
    Potentiometer,
    Run,
    Terminal,
    at_most,
    corner,
    equals,
    product,
    ratio,
    within,
)


class SimpleOscillator(System):
    """An op amp run open loop through a twin-T, trimmed just past balance."""

    figure = Cites(
        "f = 1 / (2 pi R C). Double integrator circuit with regenerative "
        "feedback. Components R, C, and 2C should be very low tolerance. Trim "
        "R/2 until oscillation is barely sustained.",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 83, Simple Oscillator",
    )

    values = Chooses(
        "What are R and C?",
        selected="10 kOhm and 15.9 nF, so 1 / (2 pi R C) is 1.001 kHz; 2C is 31.8 nF",
        alternatives=[
            {
                "option": "leave them symbolic",
                "reason": "a frequency nobody can compute is not a claim a run can check",
            },
        ],
        rationale=(
            "the figure names R, C and 2C and gives no values",
            "1 kHz is a round frequency and 10 kOhm keeps the network well "
            "above the op amp's output resistance",
        ),
    )

    trim = Chooses(
        "Where is R/2 set?",
        selected="a 10 kOhm rheostat at 0.49 of its travel: 4.9 kOhm, 2% below R/2",
        alternatives=[
            {
                "option": "exactly R/2",
                "reason": "a balanced twin-T passes nothing at f, so nothing "
                "comes back to sustain an oscillation",
            },
            {
                "option": "R/2 set high",
                "reason": "the transmission at f is then positive, the feedback "
                "negative, and the circuit is still",
            },
            {
                "option": "0.499 of the travel, nearer barely sustained",
                "reason": "the growth is then so slow that a run long enough to "
                "see it settle is mostly waiting; 2% low moves f by 0.5%",
            },
        ],
        rationale=(
            "the page says to trim R/2 until the oscillation is barely "
            "sustained; below R/2 is the side that sustains it",
            "a 10 kOhm pot is R, so its mid-travel is R/2 and 0.49 is just below",
        ),
    )

    f_o = Parameter("Hz", default=1 * kHz, description="1 / (2 pi R C)")

    e_out = Terminal()
    r_first = Resistor(resistance=10 * kOhm)
    r_second = Resistor(resistance=10 * kOhm)
    c_shunt = Capacitor(capacitance=Decimal("31.8") * nF)
    c_first = Capacitor(capacitance=Decimal("15.9") * nF)
    c_second = Capacitor(capacitance=Decimal("15.9") * nF)
    r_half = Potentiometer(resistance=10 * kOhm, setting=Decimal("0.49") * ratio)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        # R, R from the output to the - input, 2C to ground between them.
        self.amp.output.signal >> self.r_first.p1
        self.r_first.p2 >> self.r_second.p1
        self.r_first.p2 >> self.c_shunt.p1
        self.r_second.p2 >> self.amp.inverting.signal

        # C, C beside them, R/2 to ground between them.
        self.amp.output.signal >> self.c_first.p1
        self.c_first.p2 >> self.c_second.p1
        self.c_first.p2 >> self.r_half.end_a
        self.c_second.p2 >> self.amp.inverting.signal

        # The R/2 rheostat: the wiper tied to the grounded end.
        self.r_half.wiper >> self.r_half.end_b
        self.r_half.end_b >> self.ground.node
        self.c_shunt.p2 >> self.ground.node
        self.amp.non_inverting.signal >> self.ground.node
        self.amp.output.signal >> self.e_out.probe

    def constraints(self):
        require(within(self.f_o, corner(self.r_first.resistance, self.c_first.capacitance), 0.002))
        require(equals(self.r_second.resistance, self.r_first.resistance))
        require(equals(self.c_second.capacitance, self.c_first.capacitance))
        require(equals(self.c_shunt.capacitance, product(2 * ratio, self.c_first.capacitance)))
        # The pot is R, so mid-travel is R/2, and it is set below that.
        require(equals(self.r_half.resistance, self.r_first.resistance))
        require(at_most(self.r_half.setting, Decimal("0.5") * ratio))


BENCH = Bench(
    page=83,
    title="Simple Oscillator",
    runs=[
        Run(
            "oscillation",
            Transient(stop="200m", step="2u"),
            cards=[".ic v({c_shunt.1})=1"],
            measure={
                "t_first": "when v({e_out.1})=0 rise=1 td=150m",
                "t_last": "when v({e_out.1})=0 rise=41 td=150m",
                "f_o": "40 / (t_last - t_first)",
                "e_high": "max v({e_out.1}) from=150m to=200m",
                "e_low": "min v({e_out.1}) from=150m to=200m",
                "early_high": "max v({e_out.1}) from=100m to=110m",
                "summing_peak": "max v({amp.IN-}) from=150m to=200m",
            },
            claims=[
                Claim(
                    "f_o", "f_o", within=0.01, unit="Hz",
                    note="1% for the trim: R/2 set 2% low moves the frequency "
                    "at which the twin-T turns negative up by about 0.5%",
                ),
                Claim(
                    "e_high", 13.5, within=0.01, unit="V",
                    note="nothing in the loop limits the amplitude; the output "
                    "clips at the op amp's swing",
                ),
                Claim("e_low", -13.5, within=0.01, unit="V"),
            ],
            units={"t_first": "s", "t_last": "s", "early_high": "V", "summing_peak": "V"},
            note="A 1 V kick on the 2C capacitor at the start, released at once, "
            "and 150 ms for the oscillation to grow into the rails; the "
            "frequency is timed over the forty rising zero crossings after.",
        ),
    ],
)
