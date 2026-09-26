"""The buffer variation, SBOA092B page 52.

    E_O = Eref

The cell sits in the feedback path, between the output and the - input, and
the + input is on ground. The loop holds the - input at ground, so the output
stands one cell voltage above it, and the only current through the cell is
what the - input draws. The figure names the op amp, a TLC265x, a
chopper-stabilized part, and the text's point is its low drift: whatever
offset the op amp has adds straight to E_O, since nothing divides it.

Two things are open. The cell has no value, and its polarity in the drawing
does not say which plate is which, so `cell` records a Weston cell with its +
terminal on the output, for E_O = +1.0183 V. The op amp is modelled with the
1 uV offset a chopper-stabilized part is specified to (`amp`). A second run
gives the same circuit a general-purpose part's 5 mV offset, to show what the
chopper buys.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import A, Parameter, System, V, require, uV
from fang.rationale import Chooses, Cites
from fang.simulation import OperatingPoint

from handbook import Bench, Cell, Claim, Ground, OpAmp, Run, Terminal, equals


class BufferVariation(System):
    """The cell from the - input to the output, the + input on ground."""

    figure = Cites(
        "Low current drift of chopper - stabilized amplifiers improves stability "
        "and cell protection.",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 52, Buffer Variation",
    )

    cell = Chooses(
        "What is Eref, and which way round is it?",
        selected=(
            "a saturated Weston cell, 1.0183 V, + terminal on the output, so "
            "E_O = +Eref"
        ),
        alternatives=[
            {
                "option": "+ terminal on the - input",
                "reason": (
                    "gives E_O = -Eref; the figure labels the output Eref, "
                    "not -Eref"
                ),
            },
        ],
        rationale=(
            "the figure gives the cell no value and its plates are not marked",
            "the output terminal is labelled Eref",
        ),
    )

    amp_model = Chooses(
        "What offset does the TLC265x have?",
        selected="1 uV, the maximum a chopper-stabilized TLC2652A is specified to",
        alternatives=[
            {
                "option": "the bench default of 0 V",
                "reason": (
                    "the figure names a chopper-stabilized part because its "
                    "offset is small, not zero; E_O carries all of it"
                ),
            },
        ],
        rationale=("the figure names the TLC265x", "offset adds to E_O undivided"),
    )

    e_out = Parameter("V", default=1.0183 * V, description="the output, which is Eref")
    i_cell = Parameter("A", default=0 * A, description="what flows through the cell")

    e_ref = Cell(voltage=1.0183 * V)
    amp = OpAmp(input_offset=1 * uV)
    out = Terminal()
    out_return = Terminal()
    ground = Ground()

    def architecture(self):
        self.e_ref.p2 >> self.amp.inverting.signal
        self.e_ref.p1 >> self.amp.output.signal
        self.amp.output.signal >> self.out.probe
        self.amp.non_inverting.signal >> self.ground.node
        self.out_return.probe >> self.ground.node

    def constraints(self):
        # The - input sits at ground, so the output is one cell above it.
        require(equals(self.e_out, self.e_ref.voltage))
        # The cell's far end is the - input, which draws nothing.
        require(equals(self.i_cell, 0 * A))


BENCH = Bench(
    page=52,
    title="Buffer Variation",
    runs=[
        Run(
            "chopper",
            OperatingPoint(),
            measure={"e_out": "v({out.1})", "i_cell": "i(v1)"},
            claims=[
                Claim(
                    "e_out",
                    "e_out",
                    within=1e-5,
                    unit="V",
                    note="Held to 10 ppm: the 1 uV offset is 1 ppm of Eref.",
                ),
                Claim(
                    "i_cell",
                    "i_cell",
                    within=1e-9,
                    absolute=True,
                    unit="A",
                    note=(
                        "Held to 1 nA, absolute. The model's - input draws no "
                        "bias current; a TLC2652 draws a few picoamps."
                    ),
                ),
            ],
            units={"e_out": "V", "i_cell": "A"},
        ),
        Run(
            "general_part",
            OperatingPoint(),
            settings={"amp": {"input_offset": 0.005}},
            measure={"error": "v({out.1}) - 1.0183"},
            claims=[
                Claim(
                    "error",
                    -0.005,
                    within=1e-3,
                    unit="V",
                    note=(
                        "Not a handbook claim: with a 5 mV offset (the model's "
                        "offset is in series with the + input) the output "
                        "is off by the whole 5 mV, 0.5% of Eref, because "
                        "nothing in the loop divides it."
                    ),
                ),
            ],
            units={"error": "V"},
        ),
    ],
)
