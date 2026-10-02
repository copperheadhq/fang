"""The reference voltage supply, SBOA092B page 52.

    -E_O = -(R_0 / R_1) Eref = -10 Eref,   +E_O = -(R_2 / R_3)(-E_O) = +10 Eref

The first amplifier inverts the cell with a gain of -10, and the second
inverts that with a gain of -1, so the pair gives both polarities of ten
times the cell. The handbook prints no formula for this figure; the two
above are what its drawing does.

R_4 is the part worth reading. It runs from +E_O back to the cell's +
terminal, so it carries (10 Eref - Eref) / 90 kOhm = Eref / 10 kOhm into that
node, which is exactly the current R_1 draws out of it into the first
amplifier's summing point. The cell's net current is zero: the circuit
supplies its own reference's load. `bootstrap` below writes that down, and
the bench measures the cell's current to check it.

The figure gives every resistor and no cell value, so `cell` records a
Weston cell, 1.0183 V, for outputs of +/-10.183 V.
"""

import sys
from decimal import Decimal
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import A, Parameter, System, V, kOhm, require
from fang.parts import Resistor
from fang.rationale import Calculates, Chooses, Cites
from fang.simulation import OperatingPoint

from handbook import (
    Bench,
    Cell,
    Claim,
    Ground,
    OpAmp,
    Run,
    Terminal,
    equals,
    minus,
    negative,
    over,
    product,
)


class ReferenceVoltageSupply(System):
    """Eref through R_1 into an inverter of -10, then an inverter of -1; R_4 back to the cell."""

    figure = Cites(
        "Reference Voltage Supply: Eref; R1 10 kOhm, R0 100 kOhm, R3 10 kOhm, "
        "R2 10 kOhm, R4 90 kOhm; outputs -E_O and +E_O",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 52, Reference Voltage Supply",
    )

    cell = Chooses(
        "What is Eref?",
        selected="a saturated Weston cell, 1.0183 V, for outputs of +/-10.183 V",
        alternatives=[
            {
                "option": "a 1.000 V reference, for round +/-10 V outputs",
                "reason": (
                    "the page's circuits are standard-cell circuits, and the "
                    "point of R_4 is protecting a cell"
                ),
            },
        ],
        rationale=("the figure labels the cell Eref and gives no value",),
    )

    bootstrap = Calculates(
        "i_cell = Eref / R_1 - (+E_O - Eref) / R_4",
        inputs=("e_ref", "r_1", "r_4", "r_0", "r_2", "r_3"),
        result=(
            "Eref / 10 kOhm - 9 Eref / 90 kOhm = 0: R_4 returns to the cell's "
            "node exactly the 101.8 uA that R_1 takes from it"
        ),
    )

    e_out_minus = Parameter("V", default=Decimal("-10.183") * V, description="-E_O")
    e_out_plus = Parameter("V", default=Decimal("10.183") * V, description="+E_O")
    i_cell = Parameter("A", default=0 * A, description="what the cell supplies")

    e_ref = Cell(voltage=Decimal("1.0183") * V)
    r_1 = Resistor(resistance=10 * kOhm)
    r_0 = Resistor(resistance=100 * kOhm)
    r_3 = Resistor(resistance=10 * kOhm)
    r_2 = Resistor(resistance=10 * kOhm)
    r_4 = Resistor(resistance=90 * kOhm)
    amp_1 = OpAmp()
    amp_2 = OpAmp()
    out_minus = Terminal()
    out_plus = Terminal()
    out_return = Terminal()
    ground = Ground()

    def architecture(self):
        # The cell's + node: R_1 leaves it, R_4 returns to it.
        self.e_ref.p1 >> self.r_1.p1
        self.r_1.p1 >> self.r_4.p1
        # The first inverter, gain -R_0 / R_1.
        self.r_1.p2 >> self.amp_1.inverting.signal
        self.amp_1.inverting.signal >> self.r_0.p1
        self.r_0.p2 >> self.amp_1.output.signal
        self.amp_1.output.signal >> self.out_minus.probe
        # The second, gain -R_2 / R_3.
        self.amp_1.output.signal >> self.r_3.p1
        self.r_3.p2 >> self.amp_2.inverting.signal
        self.amp_2.inverting.signal >> self.r_2.p1
        self.r_2.p2 >> self.amp_2.output.signal
        self.amp_2.output.signal >> self.out_plus.probe
        self.amp_2.output.signal >> self.r_4.p2
        # The bottom wire.
        self.e_ref.p2 >> self.ground.node
        self.amp_1.non_inverting.signal >> self.ground.node
        self.amp_2.non_inverting.signal >> self.ground.node
        self.out_return.probe >> self.ground.node

    def constraints(self):
        require(
            equals(
                self.e_out_minus,
                negative(product(over(self.r_0.resistance, self.r_1.resistance), self.e_ref.voltage)),
            )
        )
        require(
            equals(
                self.e_out_plus,
                negative(product(over(self.r_2.resistance, self.r_3.resistance), self.e_out_minus)),
            )
        )
        require(
            equals(
                self.i_cell,
                minus(
                    over(self.e_ref.voltage, self.r_1.resistance),
                    over(minus(self.e_out_plus, self.e_ref.voltage), self.r_4.resistance),
                ),
            )
        )


BENCH = Bench(
    page=52,
    title="Reference Voltage Supply",
    runs=[
        Run(
            "outputs",
            OperatingPoint(),
            measure={
                "e_out_minus": "v({out_minus.1})",
                "e_out_plus": "v({out_plus.1})",
                "i_r1": "(v({r_1.1}) - v({r_1.2})) / 10e3",
                "i_cell": "-i(v1)",
            },
            claims=[
                Claim(
                    "e_out_minus",
                    "e_out_minus",
                    within=1e-4,
                    unit="V",
                    note="Held to 100 ppm: a noise gain of 11 costs 11 ppm of loop-gain error.",
                ),
                Claim("e_out_plus", "e_out_plus", within=1e-4, unit="V"),
                Claim(
                    "i_cell",
                    "i_cell",
                    within=1e-9,
                    absolute=True,
                    unit="A",
                    note=(
                        "Held to 1 nA, absolute, against the 101.8 uA R_1 "
                        "draws (i_r1): the two currents at the cell's node "
                        "cancel to within the outputs' ppm-level error."
                    ),
                ),
            ],
            units={"e_out_minus": "V", "e_out_plus": "V", "i_r1": "A", "i_cell": "A"},
        ),
    ],
)
