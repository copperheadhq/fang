"""The differential input amplifier, SBOA092B page 67.

    E_O = (R3/R1) ((R1 + R_O)/(R2 + R3)) E2 - (R_O/R1) E1

and, for R2 = R1 and R3 = R_O,

    E_O = (R_O/R1) (E2 - E1)

E1 reaches the inverting input through R1, with R_O back from the output. E2
reaches the non-inverting input through the divider R2 over R3. The figure
names the four resistors and gives them no values, so `values` records the
set chosen here: the matched pair the page reduces to, 10 kOhm and 100 kOhm,
for a differential gain of 10.

The program holds the general formula, not the reduced one: `a_e1` and `a_e2`
are what each input alone is worth at the output, written from the four
resistors, and the matched values are what make them equal and opposite. The
bench drives each input alone, then a difference, then the same voltage on
both, where a matched pair gives nothing out.
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
    product,
    ratio,
    total,
)


class DifferentialInputAmplifier(System):
    """E1 through R1 to the - input, E2 through R2 over R3 to the + input."""

    figure = Cites(
        "E_O = (R3/R1)((R1 + R_O)/(R2 + R3)) E2 - (R_O/R1) E1; "
        "for R2 = R1 and R3 = R_O, E_O = (R_O/R1)(E2 - E1)",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 67, The Differential Input Amplifier",
    )

    values = Chooses(
        "What are R1, R_O, R2 and R3?",
        selected=(
            "R1 = R2 = 10 kOhm and R_O = R3 = 100 kOhm, a differential gain of 10"
        ),
        alternatives=[
            {
                "option": "four unrelated values, to exercise the general formula",
                "reason": (
                    "the page's point is the matched case, where the output is "
                    "the difference alone; unmatched values pass part of the "
                    "common-mode voltage"
                ),
            },
            {
                "option": "leave them unknown",
                "reason": "a gain nobody can compute is not a claim anything can check",
            },
        ],
        rationale=(
            "the figure names the resistors and gives no values",
            "R2 = R1 and R3 = R_O is the condition the page reduces the formula under",
        ),
    )

    a_e1 = Parameter("1", default=-10 * ratio, description="E_O / E1, with E2 at ground")
    a_e2 = Parameter("1", default=10 * ratio, description="E_O / E2, with E1 at ground")

    e1 = Terminal()
    e2 = Terminal()
    e_out = Terminal()
    r1 = Resistor(resistance=10 * kOhm)
    r_out = Resistor(resistance=100 * kOhm)
    r2 = Resistor(resistance=10 * kOhm)
    r3 = Resistor(resistance=100 * kOhm)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        # The top leg: E1 through R1 to the summing point, R_O back from E_O.
        self.e1.probe >> self.r1.p1
        self.r1.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r_out.p1
        self.r_out.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe

        # The bottom leg: E2 through the divider R2 over R3 to the + input.
        self.e2.probe >> self.r2.p1
        self.r2.p2 >> self.amp.non_inverting.signal
        self.amp.non_inverting.signal >> self.r3.p1
        self.r3.p2 >> self.ground.node

    def constraints(self):
        # The general formula, one input at a time.
        require(equals(self.a_e1, negative(over(self.r_out.resistance, self.r1.resistance))))
        require(
            equals(
                self.a_e2,
                product(
                    over(self.r3.resistance, self.r1.resistance),
                    over(
                        total(self.r1.resistance, self.r_out.resistance),
                        total(self.r2.resistance, self.r3.resistance),
                    ),
                ),
            )
        )
        # Equal and opposite, which is what makes the output the difference
        # alone and a common-mode voltage worth nothing.
        require(equals(self.a_e2, negative(self.a_e1)))


BENCH = Bench(
    page=67,
    title="The Differential Input Amplifier",
    runs=[
        Run(
            "e1_alone",
            OperatingPoint(),
            drive={"e1": "DC 1", "e2": "DC 0"},
            measure={"gain_e1": "v({e_out.1}) / v({e1.1})"},
            claims=[Claim("gain_e1", "a_e1", within=0.001)],
        ),
        Run(
            "e2_alone",
            OperatingPoint(),
            drive={"e1": "DC 0", "e2": "DC 1"},
            measure={"gain_e2": "v({e_out.1}) / v({e2.1})"},
            claims=[Claim("gain_e2", "a_e2", within=0.001)],
        ),
        Run(
            "difference",
            OperatingPoint(),
            drive={"e1": "DC 0.3", "e2": "DC 0.5"},
            measure={"e_o": "v({e_out.1})"},
            claims=[Claim("e_o", 2.0, within=0.001, unit="V",
                          note="(R_O/R1)(E2 - E1) = 10 x 0.2 V")],
        ),
        Run(
            "common_mode",
            OperatingPoint(),
            drive={"e1": "DC 1", "e2": "DC 1"},
            measure={"e_o": "v({e_out.1})"},
            claims=[
                Claim(
                    "e_o", 0, within=1e-4, absolute=True, unit="V",
                    note=(
                        "1 V on both inputs. With the ratios matched the "
                        "cancellation does not depend on the open-loop gain, so "
                        "what ngspice reads is its own rounding."
                    ),
                )
            ],
        ),
    ],
)
