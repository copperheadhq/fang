"""The "differential output" amplifier, SBOA092B page 73.

    E_O = R_O / R_I x E_I = 10 E_I      "For driving floating load."

What the figure draws is a difference amplifier: E_I arrives between two
input terminals, neither of them ground. The top one reaches the - input
through R_I, with R_O from the output back to it; the bottom one reaches the
+ input through the other R_I, with the other R_O from there to ground. The
output is one terminal against ground. So the input floats and the output
does not, which is the reverse of the title and of the caption; `reading`
records that the program follows the drawing.

The figure marks no polarity on E_I. For E_O = +10 E_I to hold, E_I has to
be positive at the bottom terminal, the one that reaches the + input, and
`polarity` records that. Because the matched pairs make the stage reject
what the two terminals share, the bench also drives them together and finds
nothing at the output.
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
    over,
    ratio,
)


class DifferentialOutput(System):
    """A difference amplifier: E_I between two terminals, E_O against ground."""

    figure = Cites(
        "E_O = R_O / R_I E_I = 10 E_I. For driving floating load.",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 73, Differential Output",
    )

    reading = Chooses(
        "Which side of the circuit floats?",
        selected=(
            "the input: E_I is applied between the two left-hand terminals, "
            "and E_O is taken from the output to ground"
        ),
        alternatives=[
            {
                "reading": "a floating load driven between two outputs",
                "reason": (
                    "the figure has one op amp with one output, and the lower "
                    "right terminal is on the ground symbol; there is no "
                    "second output for a floating load to sit between"
                ),
            },
        ],
        rationale=(
            "the lower left terminal goes to the + input through R_I, not to ground",
            "the drawing is the source of truth; the caption does not match it",
        ),
    )

    polarity = Chooses(
        "Which input terminal is E_I positive at?",
        selected="the bottom one, which reaches the + input, so E_O = +10 E_I as printed",
        alternatives=[
            {
                "option": "the top one",
                "reason": "E_O would be -10 E_I, and the page prints a positive gain",
            },
        ],
        rationale=("the figure marks no polarity",),
    )

    a_v = Parameter("1", default=10 * ratio, description="E_O / E_I, E_I positive at the bottom terminal")

    e_in_top = Terminal()
    e_in_bottom = Terminal()
    e_out = Terminal()
    r_in_top = Resistor(resistance=10 * kOhm)
    r_out_top = Resistor(resistance=100 * kOhm)
    r_in_bottom = Resistor(resistance=10 * kOhm)
    r_out_bottom = Resistor(resistance=100 * kOhm)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in_top.probe >> self.r_in_top.p1
        self.r_in_top.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r_out_top.p1
        self.r_out_top.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe

        self.e_in_bottom.probe >> self.r_in_bottom.p1
        self.r_in_bottom.p2 >> self.amp.non_inverting.signal
        self.amp.non_inverting.signal >> self.r_out_bottom.p1
        self.r_out_bottom.p2 >> self.ground.node

    def constraints(self):
        # The printed gain is R_O / R_I, and it is the difference gain only
        # while the two pairs are matched, which is also what rejects the
        # common mode.
        require(equals(self.a_v, over(self.r_out_top.resistance, self.r_in_top.resistance)))
        require(
            equals(
                over(self.r_out_bottom.resistance, self.r_in_bottom.resistance),
                over(self.r_out_top.resistance, self.r_in_top.resistance),
            )
        )


BENCH = Bench(
    page=73,
    title="Differential Output",
    runs=[
        Run(
            "floating",
            OperatingPoint(),
            drive={"e_in_top": "DC -0.5", "e_in_bottom": "DC 0.5"},
            measure={"gain": "v({e_out.1}) / (v({e_in_bottom.1}) - v({e_in_top.1}))"},
            claims=[Claim("gain", "a_v", within=0.001)],
            note="E_I = 1 V split symmetrically about ground: -0.5 V on the top terminal, +0.5 V on the bottom.",
        ),
        Run(
            "offset_source",
            OperatingPoint(),
            drive={"e_in_top": "DC 3", "e_in_bottom": "DC 4"},
            measure={"gain": "v({e_out.1}) / (v({e_in_bottom.1}) - v({e_in_top.1}))"},
            claims=[Claim("gain", "a_v", within=0.001)],
            note="The same 1 V of E_I, riding 3 V above ground: only the difference reaches E_O.",
        ),
        Run(
            "common_mode",
            OperatingPoint(),
            drive={"e_in_top": "DC 1", "e_in_bottom": "DC 1"},
            measure={"e_out": "v({e_out.1})"},
            claims=[
                Claim(
                    "e_out",
                    0,
                    within=1e-4,
                    absolute=True,
                    unit="V",
                    note="both terminals at 1 V, E_I = 0: the matched pairs reject it",
                )
            ],
        ),
    ],
)
