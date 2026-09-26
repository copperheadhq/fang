"""The inverting amplifier, SBOA092B page 54.

    E_O / E_I = -R_O / R_I

The handbook derives it by letting the open-loop gain go to infinity, so the
inverting input sits at ground and the current through R_I is the current
through R_O. The figure names the two resistors and gives them no values, so
`values` records the pair chosen here: 10 kOhm in and 100 kOhm across, a gain
of -10.

The bench drives E_I with 1 V and reads E_O, then sweeps the frequency to show
where the claim stops holding: a 10 MHz op amp closed for a noise gain of 11
has a bandwidth near 900 kHz, which the ideal algebra does not see.
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
    negative,
    over,
    ratio,
)


class InvertingAmplifier(System):
    """E_I through R_I into the summing point, R_O back from the output."""

    figure = Cites(
        "E_O / E_I = -R_O / R_I",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 54, The Inverting Amplifier",
    )

    values = Chooses(
        "What are R_I and R_O?",
        selected="10 kOhm and 100 kOhm, for a gain of -10",
        alternatives=[
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

    a_v = Parameter("1", default=-10 * ratio, description="E_O / E_I")

    e_in = Terminal()
    e_out = Terminal()
    r_in = Resistor(resistance=10 * kOhm)
    r_out = Resistor(resistance=100 * kOhm)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.r_in.p1
        self.r_in.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r_out.p1
        self.r_out.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe
        self.amp.non_inverting.signal >> self.ground.node

    def constraints(self):
        require(equals(self.a_v, negative(over(self.r_out.resistance, self.r_in.resistance))))


BENCH = Bench(
    page=54,
    title="The Inverting Amplifier",
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
            claims=[Claim("gain_1k", 10, within=0.001)],
            units={"f_3db": "Hz"},
            note=(
                "The magnitude, so 10 rather than -10. The -3 dB point is "
                "not a handbook claim: it is the op amp's, 10 MHz over a noise "
                "gain of 11."
            ),
        ),
    ],
)
