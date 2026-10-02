"""The presettable voltage source, SBOA092B page 52.

    E_O = (R_I + R_O) / R_I x Eref

The cell's - terminal is on the - input, which the loop holds at ground, so
its + terminal, the node R_I and R_O share, stands at +Eref. R_I then carries
Eref / R_I to ground, all of it from the output through R_O, and the output
settles at Eref (1 + R_O / R_I). The cell carries only what the - input draws.

The figure sizes R_I as "1000 x Eref" ohms. That makes the current through it
1 mA whatever the cell is, so the decade box reads directly: every ohm of R_O
is a millivolt of E_O above Eref. The program records that as a calculation
of its own (`scale`), since the handbook does not say it.

Open: the cell's value, and R_O's dial. `cell` records a Weston cell,
1.0183 V, so R_I is 1018.3 Ohm. `dial` sets R_O to 8981.7 Ohm, for 10.000 V.
The decade box is drawn as a variable resistor, so the program models it as a
potentiometer with its wiper on one end (`decade_box`), and a run can turn it:
3981.7 Ohm for 5 V, and 0 Ohm for Eref itself. The op amp is the TLC265x the
figure names, with a chopper's 1 uV offset.
"""

import sys
from decimal import Decimal
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import A, Ohm, Parameter, System, V, mA, require, uV
from fang.parts import Resistor
from fang.rationale import Calculates, Chooses, Cites
from fang.simulation import OperatingPoint

from handbook import (
    Bench,
    Cell,
    Claim,
    Ground,
    OpAmp,
    Potentiometer,
    Run,
    Terminal,
    equals,
    over,
    product,
    ratio,
    total,
)


class PresettableVoltageSource(System):
    """Eref from the R_I/R_O node to the - input; R_O on to the output, R_I to ground."""

    figure = Cites(
        "E_O = (R_I + R_O) / R_I x Eref. Gives wide range of very stable "
        "reference voltages.",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 52, Presettable Voltage Source",
    )

    cell = Chooses(
        "What is Eref?",
        selected="a saturated Weston cell, 1.0183 V, so R_I = 1000 x Eref = 1018.3 Ohm",
        alternatives=[
            {
                "option": "a 1.2 V bandgap",
                "reason": "the page's other circuits are standard-cell circuits",
            },
        ],
        rationale=("the figure labels the cell Eref and gives no value",),
    )

    dial = Chooses(
        "Where is the decade box set?",
        selected="8981.7 Ohm, for E_O = 10.000 V",
        alternatives=[
            {
                "option": "a round 9000 Ohm",
                "reason": "gives 10.0183 V; the dial exists to land on a round output",
            },
        ],
        rationale=(
            "the figure draws a decade box and no setting",
            "10 V is the reference such a circuit is usually asked for",
        ),
    )

    decade_box = Chooses(
        "How is a decade box drawn in parts?",
        selected="a potentiometer with its wiper tied to its far end, set to full travel",
        alternatives=[
            {
                "option": "a fixed resistor",
                "reason": "a run could not turn the dial without editing the program",
            },
        ],
        rationale=(
            "a rheostat is a potentiometer with its wiper on one end",
            "the bench can override a potentiometer's resistance for one run",
        ),
    )

    scale = Calculates(
        "i_set = Eref / R_I, with R_I = 1000 x Eref",
        inputs=("e_ref", "r_in"),
        result=(
            "1 mA whatever the cell, so E_O = Eref + R_O x 1 mA: each ohm on "
            "the decade box is a millivolt above Eref"
        ),
    )

    e_out = Parameter("V", default=10 * V, description="E_O")
    i_set = Parameter("A", default=1 * mA, description="the current through R_I and R_O")
    i_cell = Parameter("A", default=0 * A, description="what flows through the cell")

    e_ref = Cell(voltage=Decimal("1.0183") * V)
    r_in = Resistor(resistance=Decimal("1018.3") * Ohm)
    r_out = Potentiometer(resistance=Decimal("8981.7") * Ohm, setting=1 * ratio)
    amp = OpAmp(input_offset=1 * uV)
    out = Terminal()
    out_return = Terminal()
    ground = Ground()

    def architecture(self):
        # The node the cell's + terminal, R_I and R_O share.
        self.e_ref.p1 >> self.r_in.p1
        self.r_in.p1 >> self.r_out.end_a
        self.e_ref.p2 >> self.amp.inverting.signal
        # The decade box: its wiper on its far end, so all of it is in circuit.
        self.r_out.wiper >> self.r_out.end_b
        self.r_out.end_b >> self.amp.output.signal
        self.amp.output.signal >> self.out.probe
        self.r_in.p2 >> self.ground.node
        self.amp.non_inverting.signal >> self.ground.node
        self.out_return.probe >> self.ground.node

    def constraints(self):
        require(
            equals(
                self.e_out,
                product(
                    over(total(self.r_in.resistance, self.r_out.resistance), self.r_in.resistance),
                    self.e_ref.voltage,
                ),
            )
        )
        # The handbook's sizing rule, and what it buys.
        require(equals(self.r_in.resistance, product(self.e_ref.voltage, over(1000 * Ohm, 1 * V))))
        require(equals(self.i_set, over(self.e_ref.voltage, self.r_in.resistance)))
        require(equals(self.i_cell, 0 * A))


BENCH = Bench(
    page=52,
    title="Presettable Voltage Source",
    runs=[
        Run(
            "ten_volts",
            OperatingPoint(),
            measure={
                "e_out": "v({out.1})",
                "i_set": "v({r_in.1}) / 1018.3",
                "i_cell": "i(v1)",
            },
            claims=[
                Claim(
                    "e_out",
                    "e_out",
                    within=1e-4,
                    unit="V",
                    note=(
                        "Held to 100 ppm: a noise gain near 10 costs 10 ppm "
                        "of loop-gain error, and the 1 uV offset another 1 ppm."
                    ),
                ),
                Claim("i_set", "i_set", within=1e-4, unit="A"),
                Claim(
                    "i_cell",
                    "i_cell",
                    within=1e-9,
                    absolute=True,
                    unit="A",
                    note="Held to 1 nA, absolute: the model's - input draws no bias current.",
                ),
            ],
            units={"e_out": "V", "i_set": "A", "i_cell": "A"},
        ),
        Run(
            "five_volts",
            OperatingPoint(),
            settings={"r_out": {"resistance": 3981.7}},
            measure={"e_out": "v({out.1})"},
            claims=[
                Claim(
                    "e_out",
                    5.0,
                    within=1e-4,
                    unit="V",
                    note="The dial at 3981.7 Ohm: 3981.7 mV above Eref.",
                )
            ],
            units={"e_out": "V"},
        ),
        Run(
            "dial_at_zero",
            OperatingPoint(),
            settings={"r_out": {"resistance": 0}},
            measure={"e_out": "v({out.1})"},
            claims=[
                Claim(
                    "e_out",
                    1.0183,
                    within=1e-4,
                    unit="V",
                    note="The dial at zero: the lowest E_O the circuit gives is Eref.",
                )
            ],
            units={"e_out": "V"},
        ),
    ],
)
