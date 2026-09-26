"""The non-inverting amplifier, SBOA092B page 53.

    E_O / E_I = (R_O + R_I) / R_I = 1 + R_O / R_I

E_I goes in at the + input. R_O and R_I divide the output down to the -
input, and the loop holds the - input at E_I, so the current E_I / R_I in R_I
is the current in R_O and the output stands E_I R_O / R_I above E_I. The
handbook derives it by letting the open-loop gain go to infinity.

The figure names the two resistors and gives them no values, so `values`
records the pair chosen here: 10 kOhm and 90 kOhm, a gain of +10. The bench
drives E_I with 1 V and reads E_O, then sweeps the frequency: the noise gain
is the signal gain here, 10, so a 10 MHz op amp closes near 1 MHz.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Parameter, System, kOhm, require
from fang.parts import Resistor
from fang.rationale import Chooses, Cites
from fang.simulation import ACSweep, OperatingPoint

from handbook import (
    Bench,
    Claim,
    Ground,
    OpAmp,
    Run,
    Terminal,
    equals,
    over,
    ratio,
    total,
)


class NoninvertingAmplifier(System):
    """E_I on the + input; R_O from the output to the - input, R_I from there to ground."""

    figure = Cites(
        "E_O / E_I = (R_O + R_I) / R_I = 1 + R_O / R_I",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 53, The Non-Inverting Amplifier",
    )

    values = Chooses(
        "What are R_I and R_O?",
        selected="10 kOhm and 90 kOhm, for a gain of +10",
        alternatives=[
            {
                "option": "10 kOhm and 100 kOhm, as in the inverting example",
                "reason": "gives 11, a gain nobody reads off at a glance",
            },
            {
                "option": "leave them unknown",
                "reason": "a gain nobody can compute is not a claim anything can check",
            },
        ],
        rationale=(
            "the figure names the resistors and gives no values",
            "a decade of gain keeps E_O far inside the swing for a 1 V drive",
        ),
    )

    a_v = Parameter("1", default=10 * ratio, description="E_O / E_I")

    e_in = Terminal()
    e_out = Terminal()
    e_in_return = Terminal()
    e_out_return = Terminal()
    r_in = Resistor(resistance=10 * kOhm)
    r_out = Resistor(resistance=90 * kOhm)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.amp.non_inverting.signal
        self.amp.inverting.signal >> self.r_out.p1
        self.r_out.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe
        self.amp.inverting.signal >> self.r_in.p1
        self.r_in.p2 >> self.ground.node
        self.e_in_return.probe >> self.ground.node
        self.e_out_return.probe >> self.ground.node

    def constraints(self):
        require(
            equals(self.a_v, total(1 * ratio, over(self.r_out.resistance, self.r_in.resistance)))
        )


BENCH = Bench(
    page=53,
    title="The Non-Inverting Amplifier",
    runs=[
        Run(
            "gain",
            OperatingPoint(),
            drive={"e_in": "DC 1"},
            measure={"gain": "v({e_out.1}) / v({e_in.1})"},
            claims=[Claim("gain", "a_v", within=0.001)],
        ),
        Run(
            "bandwidth",
            ACSweep(points=20, start="10", stop="10meg"),
            drive={"e_in": "DC 0 AC 1"},
            measure={
                "gain_1k": "find vm({e_out.1}) at=1k",
                "f_3db": "when vdb({e_out.1})=17 fall=1",
            },
            claims=[Claim("gain_1k", "a_v", within=0.001)],
            units={"f_3db": "Hz"},
            note=(
                "The -3 dB point is not a handbook claim: it is the op amp's, "
                "10 MHz over a noise gain of 10."
            ),
        ),
    ],
)
