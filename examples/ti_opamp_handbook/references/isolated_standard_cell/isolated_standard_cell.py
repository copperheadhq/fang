"""The isolated standard cell, SBOA092B page 51.

    E_O = Eref, and the cell supplies no current

A standard cell is a voltage reference that is spoiled by drawing current
from it, and the handbook's point is that a follower in front of it lets a
low-impedance meter (it names 20 kOhm per volt) read the cell without loading
it: the meter's current comes from the op amp's output, and the cell sees only
the + input.

The figure draws the cell and gives it no value, and draws no meter, so the
program decides both. `cell` records a saturated Weston cell, 1.0183 V.
`load` puts a 20 kOhm resistor on the output: a 20 kOhm/V meter on its 1 V
range, the load the text warns about. The claims are that the output is Eref
with the load on it, that the load's current (51 uA) comes from the output,
and that the cell's own current stays at zero.
"""

import sys
from decimal import Decimal
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import A, Parameter, System, V, kOhm, require, uA
from fang.parts import Resistor
from fang.rationale import Chooses, Cites
from fang.simulation import OperatingPoint

from handbook import Bench, Cell, Claim, Ground, OpAmp, Run, Terminal, equals, over


class IsolatedStandardCell(System):
    """The cell on the + input, the output fed back to the - input, a meter on the output."""

    figure = Cites(
        "Prevent damage to standard cells induced by drawing current from them "
        "with low impedance (20 KOhm / Volt) measuring devices.",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 51, Isolated Standard Cell",
    )

    cell = Chooses(
        "What is Eref?",
        selected="a saturated Weston standard cell, 1.0183 V",
        alternatives=[
            {
                "option": "a 1.2 V bandgap reference",
                "reason": (
                    "the page is about standard cells, whose EMF is spoiled by "
                    "current; a bandgap has an output stage of its own"
                ),
            },
        ],
        rationale=(
            "the figure labels the cell Eref and gives no value",
            "the Weston cell is the standard cell the text has in mind",
        ),
    )

    load = Chooses(
        "What does the output drive?",
        selected="20 kOhm to ground: a 20 kOhm/V meter on its 1 V range",
        alternatives=[
            {
                "option": "nothing",
                "reason": (
                    "an unloaded follower says nothing about where the meter's "
                    "current comes from, which is the point of the circuit"
                ),
            },
        ],
        rationale=(
            "the text names 20 kOhm/V measuring devices as what damages the cell",
            "the figure draws the output terminals and no meter",
        ),
    )

    e_out = Parameter("V", default=1.0183 * V, description="the output, which is Eref")
    i_load = Parameter("A", default=Decimal("50.915") * uA, description="what the meter draws")
    i_cell = Parameter("A", default=0 * A, description="what the cell supplies")

    e_ref = Cell(voltage=1.0183 * V)
    amp = OpAmp()
    r_load = Resistor(resistance=20 * kOhm)
    out = Terminal()
    out_return = Terminal()
    ground = Ground()

    def architecture(self):
        self.e_ref.p1 >> self.amp.non_inverting.signal
        self.e_ref.p2 >> self.ground.node
        self.amp.output.signal >> self.amp.inverting.signal
        self.amp.output.signal >> self.out.probe
        self.out.probe >> self.r_load.p1
        self.r_load.p2 >> self.ground.node
        self.out_return.probe >> self.ground.node

    def constraints(self):
        require(equals(self.e_out, self.e_ref.voltage))
        require(equals(self.i_load, over(self.e_out, self.r_load.resistance)))
        # The cell's only connection besides ground is the + input, which the
        # ideal op amp draws nothing through.
        require(equals(self.i_cell, 0 * A))


BENCH = Bench(
    page=51,
    title="Isolated Standard Cell",
    runs=[
        Run(
            "loaded",
            OperatingPoint(),
            measure={
                "e_out": "v({out.1})",
                "i_load": "v({out.1}) / 20e3",
                "i_cell": "-i(v1)",
            },
            claims=[
                Claim("e_out", "e_out", within=0.001, unit="V"),
                Claim("i_load", "i_load", within=0.001, unit="A"),
                Claim(
                    "i_cell",
                    "i_cell",
                    within=1e-9,
                    absolute=True,
                    unit="A",
                    note=(
                        "Held to 1 nA, absolute. The model's inputs are 1 TOhm "
                        "apart and draw no bias current, so it measures near "
                        "zero; a real FET-input part would draw picoamps. "
                        "Without the follower the meter would draw its 51 uA "
                        "from the cell."
                    ),
                ),
            ],
            units={"e_out": "V", "i_load": "A", "i_cell": "A"},
        ),
    ],
)
