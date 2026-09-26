"""The differential (balanced) output amplifier, SBOA092B page 69.

    E_O = (R_O / R_I) (E2 - E1)

An op amp with two outputs. E1 reaches the inverting input through R_I, with
R_O from there to the top output; E2 reaches the non-inverting input through
R_I, with R_O from there to the bottom output. The handbook calls the bottom
output E_P and the top one E_O + E_P, so E_O is the difference between them.

The page says what the loop does not set: "the values of E_f and E_P are not
uniquely determined". Where the two outputs sit together is the op amp's own
business, and the bench's model holds that common level at ground. So E_P is
reported and not claimed; only the difference is.

The figure names the resistors and gives no values, so `values` records the
pair chosen here: 10 kOhm and 100 kOhm, a differential gain of 10.
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
    DifferentialOpAmp,
    Ground,
    Run,
    Terminal,
    equals,
    over,
    ratio,
)


class BalancedOutputAmplifier(System):
    """Two inverting legs around one op amp with two outputs."""

    figure = Cites(
        "E_O = (R_O/R_I)(E2 - E1). Note that the values of E_f and E_P are not "
        "uniquely determined by the above equations",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 69, The Differential (Balanced) Output Amplifier",
    )

    values = Chooses(
        "What are R_I and R_O?",
        selected="10 kOhm and 100 kOhm in both legs, a differential gain of 10",
        alternatives=[
            {
                "option": "leave them unknown",
                "reason": "a gain nobody can compute is not a claim anything can check",
            },
            {
                "option": "different pairs in the two legs",
                "reason": (
                    "the page's subtraction of the two leg equations needs the "
                    "same R_I and R_O in both; the figure labels them alike"
                ),
            },
        ],
        rationale=(
            "the figure names the resistors and gives no values",
            "a gain of 10 keeps each output far inside the swing for the drives used",
        ),
    )

    a_d = Parameter("1", default=10 * ratio, description="E_O / (E2 - E1)")

    e1 = Terminal()
    e2 = Terminal()
    e_o = Terminal()
    e_p = Terminal()
    common = Terminal()
    r_in_top = Resistor(resistance=10 * kOhm)
    r_out_top = Resistor(resistance=100 * kOhm)
    r_in_bottom = Resistor(resistance=10 * kOhm)
    r_out_bottom = Resistor(resistance=100 * kOhm)
    amp = DifferentialOpAmp()
    ground = Ground()

    def architecture(self):
        # The top leg: E1 into the - input, R_O to the output that falls when
        # that input rises.
        self.e1.probe >> self.r_in_top.p1
        self.r_in_top.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r_out_top.p1
        self.r_out_top.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_o.probe

        # The bottom leg: E2 into the + input, R_O to the other output.
        self.e2.probe >> self.r_in_bottom.p1
        self.r_in_bottom.p2 >> self.amp.non_inverting.signal
        self.amp.non_inverting.signal >> self.r_out_bottom.p1
        self.r_out_bottom.p2 >> self.amp.output_minus.signal
        self.amp.output_minus.signal >> self.e_p.probe

        # Nothing in the figure touches ground but the grounded terminal
        # between E1 and E2: the op amp's common level is its own.
        self.common.probe >> self.ground.node

    def constraints(self):
        require(equals(self.r_in_top.resistance, self.r_in_bottom.resistance))
        require(equals(self.r_out_top.resistance, self.r_out_bottom.resistance))
        require(equals(self.a_d, over(self.r_out_top.resistance, self.r_in_top.resistance)))


BENCH = Bench(
    page=69,
    title="The Differential (Balanced) Output Amplifier",
    runs=[
        Run(
            "difference",
            OperatingPoint(),
            drive={"e1": "DC 0.2", "e2": "DC 0.5"},
            measure={
                "gain": "(v({e_o.1}) - v({e_p.1})) / (v({e2.1}) - v({e1.1}))",
                "e_p": "v({e_p.1})",
            },
            claims=[Claim("gain", "a_d", within=0.001)],
            units={"e_p": "V"},
            note=(
                "E_O is the top output less the bottom one. E_P, where the bottom "
                "output sits, is set inside the op amp; this model centres the "
                "pair on ground, so E_P is -E_O/2 here and not a handbook claim."
            ),
        ),
        Run(
            "floating",
            OperatingPoint(),
            drive={"e1": "DC 2.2", "e2": "DC 2.5"},
            measure={"e_o": "v({e_o.1}) - v({e_p.1})"},
            claims=[
                Claim("e_o", 3.0, within=0.001, unit="V",
                      note="the same 0.3 V difference riding on 2.2 V: still 10 x 0.3 V"),
            ],
        ),
        Run(
            "common_mode",
            OperatingPoint(),
            drive={"e1": "DC 1", "e2": "DC 1"},
            measure={"e_o": "v({e_o.1}) - v({e_p.1})"},
            claims=[Claim("e_o", 0, within=1e-4, absolute=True, unit="V",
                          note="1 V on both inputs gives no difference out")],
        ),
    ],
)
