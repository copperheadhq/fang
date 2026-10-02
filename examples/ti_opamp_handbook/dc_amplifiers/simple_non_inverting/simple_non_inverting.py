"""The simple non-inverting amplifier, SBOA092B page 71.

    E_O = (R_O + R_I) / R_I x E_I = 10 E_I

E_I goes straight to the + input, and R_O and R_I divide the output back to
the - input. The figure gives the values, 90 kOhm and 10 kOhm, so there is
nothing to choose: the gain is 100k / 10k = 10.

The page warns that the input common-mode limit must be observed, because
both inputs follow E_I. The macro-model has no common-mode limit, so the
bench shows the other limit it does have: the output swing, which a 1.35 V
input already reaches.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Parameter, System, kOhm, require
from fang.parts import Resistor
from fang.rationale import Cites
from fang.simulation import DCSweep, OperatingPoint

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


class SimpleNonInverting(System):
    """E_I on the + input, R_O and R_I dividing the output back to the - input."""

    figure = Cites(
        "E_O = (R_O + R_I) / R_I E_I = 10 E_I; input common mode voltage limit must be observed",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 71, Simple Non-Inverting",
    )

    a_v = Parameter("1", default=10 * ratio, description="E_O / E_I")

    e_in = Terminal()
    e_out = Terminal()
    r_in = Resistor(resistance=10 * kOhm)
    r_out = Resistor(resistance=90 * kOhm)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.amp.non_inverting.signal
        self.amp.inverting.signal >> self.r_in.p1
        self.r_in.p2 >> self.ground.node
        self.amp.inverting.signal >> self.r_out.p1
        self.r_out.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe

    def constraints(self):
        require(
            equals(
                self.a_v,
                over(total(self.r_out.resistance, self.r_in.resistance), self.r_in.resistance),
            )
        )


BENCH = Bench(
    page=71,
    title="Simple Non-Inverting",
    runs=[
        Run(
            "gain",
            OperatingPoint(),
            drive={"e_in": "DC 1"},
            measure={
                "gain": "v({e_out.1}) / v({e_in.1})",
                "e_minus": "v({amp.IN-})",
            },
            claims=[
                Claim("gain", "a_v", within=0.001),
                Claim(
                    "e_minus",
                    1,
                    within=0.001,
                    unit="V",
                    note="the - input follows E_I: both inputs sit at the input voltage, which is the common-mode limit the page warns of",
                ),
            ],
        ),
        Run(
            "swing",
            DCSweep(source="VDRIVE_e_in", start="-2", stop="2", step="0.01"),
            drive={"e_in": "DC 0"},
            measure={
                "e_out_top": "max v({e_out.1})",
                "e_out_bottom": "min v({e_out.1})",
                "gain_at_1v": "find v({e_out.1}) at=1",
            },
            claims=[
                Claim("gain_at_1v", "a_v", within=0.001, note="E_O at E_I = 1 V, so the gain"),
                Claim("e_out_top", 13.5, within=0.01, unit="V", note="the macro-model's swing, reached at E_I = 1.35 V; its clamp diode lets it pass by a few mV, hence 1%"),
                Claim("e_out_bottom", -13.5, within=0.01, unit="V"),
            ],
            note="A sweep of E_I from -2 V to 2 V. The output is linear at 10 E_I until it meets the +/-13.5 V swing.",
        ),
    ],
)
