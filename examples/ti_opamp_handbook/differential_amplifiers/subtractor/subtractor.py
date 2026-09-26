"""The subtractor, SBOA092B page 74.

    E_O = E2 - E1

The differential input amplifier of page 67 with every resistor 10 kOhm: E1
through R_I into the inverting input with R_O back from the output, E2
through R_I and R_O as a divider onto the non-inverting input. With R_O equal
to R_I the difference gain is 1, and what comes out is the subtraction itself.

The figure gives every value, so nothing was chosen. The bench drives a
difference, and then the same voltage on both inputs.
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
    over,
    ratio,
)


class Subtractor(System):
    """E1 into the - input, E2 divided onto the + input, all resistors 10 kOhm."""

    figure = Cites(
        "E_O = E2 - E1. Direct subtraction of two inputs",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 74, Subtractor",
    )

    a_d = Parameter("1", default=1 * ratio, description="E_O / (E2 - E1)")

    e1 = Terminal()
    e2 = Terminal()
    common = Terminal()
    e_out = Terminal()
    r_in_top = Resistor(resistance=10 * kOhm)
    r_out_top = Resistor(resistance=10 * kOhm)
    r_in_bottom = Resistor(resistance=10 * kOhm)
    r_out_bottom = Resistor(resistance=10 * kOhm)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        # The top leg: E1 into the summing point, R_O back from E_O.
        self.e1.probe >> self.r_in_top.p1
        self.r_in_top.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r_out_top.p1
        self.r_out_top.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe

        # The bottom leg: E2 divided by R_I over R_O onto the + input.
        self.e2.probe >> self.r_in_bottom.p1
        self.r_in_bottom.p2 >> self.amp.non_inverting.signal
        self.amp.non_inverting.signal >> self.r_out_bottom.p1
        self.r_out_bottom.p2 >> self.ground.node

        # The grounded terminal between E1 and E2.
        self.common.probe >> self.ground.node

    def constraints(self):
        # The two legs' ratios match, which is what makes it a subtractor, and
        # the matched ratio is the gain.
        require(
            equals(
                over(self.r_out_top.resistance, self.r_in_top.resistance),
                over(self.r_out_bottom.resistance, self.r_in_bottom.resistance),
            )
        )
        require(equals(self.a_d, over(self.r_out_top.resistance, self.r_in_top.resistance)))


BENCH = Bench(
    page=74,
    title="Subtractor",
    runs=[
        Run(
            "difference",
            OperatingPoint(),
            drive={"e1": "DC 1.5", "e2": "DC 4"},
            measure={
                "e_o": "v({e_out.1})",
                "gain": "v({e_out.1}) / (v({e2.1}) - v({e1.1}))",
            },
            claims=[
                Claim("e_o", 2.5, within=0.001, unit="V", note="4 V - 1.5 V"),
                Claim("gain", "a_d", within=0.001),
            ],
        ),
        Run(
            "common_mode",
            OperatingPoint(),
            drive={"e1": "DC 2", "e2": "DC 2"},
            measure={"e_o": "v({e_out.1})"},
            claims=[Claim("e_o", 0, within=1e-4, absolute=True, unit="V",
                          note="2 V on both inputs: nothing to subtract")],
        ),
    ],
)
