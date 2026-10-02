"""The constant current generator, SBOA092B page 51.

    I = V_Z / R_2 = 6 / 300 = 20 mA
    R_1 = (15 - V_Z) / I_Z = 9 / 25 = 360 Ohm
    R_L min = Saturation Voltage / I = 13.5 V / 20 mA = 675 Ohm

R_1 from +15 V biases a 6 V zener, and R_2 turns the zener's voltage into a
current into the summing point, which the loop holds at ground. All of that
current leaves through R_L to the output, whatever R_L is, so R_L is the load
and I is set by V_Z and R_2 alone.

Three things in the page do not hold up, and the program records each.

The figure has the op amp's inputs the wrong way round. As drawn, the node R_2
and R_L share goes to the + input and the - input to ground, so R_L feeds the
output back positively and the output latches at the rail (a transient of the
drawn wiring, run by hand, sits at +13.5 V). `reading` takes the inputs the
other way, which is the circuit the page's formulas describe.

R_1's formula forgets that R_2's 20 mA comes out of the zener node too: R_1
carries I_Z + I, not I_Z. With the drawn 330 Ohm, R_1 carries 27.3 mA and the
zener keeps 7.3 mA, not 25 mA. The drawn 330 Ohm is not the printed 360 Ohm
either; neither is a rounding of the other, and 360 Ohm would leave the zener
5 mA. `bias` keeps the drawn value.

And "R_L min" is a maximum. The output sits at -I R_L, so the largest load the
output can drive 20 mA through before it saturates at -13.5 V is 675 Ohm.
The bench runs R_L at 500 Ohm and then at 800 Ohm, past the limit, where the
output pins at -13.5 V and the current falls to about 17.8 mA.

The current depends on the zener's actual voltage, and the model's is not
6.000 V at 7.3 mA. The bench measures V_Z and checks I = V_Z / R_2 against the
measurement tightly, and against the nominal 20 mA to 1%.
"""

import sys
from decimal import Decimal
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Ohm, Parameter, System, V, mA, require
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
    Zener,
    at_most,
    equals,
    minus,
    negative,
    over,
    ratio,
    within,
)


class ConstantCurrentGenerator(System):
    """A zener's voltage across R_2 sets a current; the op amp forces it through R_L."""

    figure = Cites(
        "Convenient current reference up to 20 mA: I = V_Z / R_2 = 6 / 300 = 20 mA; "
        "R_1 = (15 - V_Z) / I_Z = 9 / 25 = 360 Ohm; "
        "R_L min = Saturation Voltage / I = 13.5 V / 20 mA = 675 Ohm",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 51, Constant Current Generator",
    )

    reading = Chooses(
        "Which op amp input does the R_2 / R_L node go to?",
        selected="the - input, with the + input on ground",
        alternatives=[
            {
                "option": "the + input, as drawn",
                "reason": (
                    "R_L then returns the output to the + input, positive "
                    "feedback, and the output latches at +13.5 V; a transient "
                    "of that wiring does exactly that"
                ),
            },
        ],
        rationale=(
            "I = V_Z / R_2 needs the node held at ground, which only negative "
            "feedback does",
            "the drawing's + and - markings are swapped against every formula on the page",
        ),
    )

    bias = Chooses(
        "Is R_1 330 Ohm, as drawn, or 360 Ohm, as printed?",
        selected="330 Ohm, as drawn",
        alternatives=[
            {
                "option": "360 Ohm, the printed result",
                "reason": (
                    "it comes from (15 - V_Z) / I_Z, which leaves out the 20 mA "
                    "R_2 takes from the same node; it would leave the zener "
                    "5 mA, not 25 mA"
                ),
            },
        ],
        rationale=(
            "the drawing is the circuit; the printed formula is wrong either way",
            "330 Ohm leaves the zener 7.3 mA, which keeps it in breakdown",
        ),
    )

    load = Chooses(
        "What is R_L?",
        selected=(
            "a rheostat (a potentiometer with its wiper on one end) at 500 Ohm, "
            "turned to 800 Ohm for one run"
        ),
        alternatives=[
            {
                "option": "a fixed resistor",
                "reason": "a run could not take the load past its limit",
            },
        ],
        rationale=(
            "the figure gives R_L no value: it is whatever is being fed",
            "500 Ohm is inside the 675 Ohm limit, 800 Ohm is past it",
        ),
    )

    zener_current = Calculates(
        "I_Z = (15 - V_Z) / R_1 - V_Z / R_2",
        inputs=("supply", "zener", "r_1", "r_2"),
        result=(
            "9 / 330 - 6 / 300 = 27.3 mA - 20 mA = 7.3 mA. The handbook's "
            "R_1 = (15 - V_Z) / I_Z drops the second term"
        ),
    )

    i_out = Parameter("A", default=20 * mA, description="I, the current through R_L")
    i_zener = Parameter("A", default=Decimal("7.273") * mA, description="what the zener keeps")
    swing = Parameter("V", default=13.5 * V, description="how far the output can go")
    r_load_max = Parameter("Ohm", default=675 * Ohm, description="the handbook's 'R_L min'")

    supply = Cell(voltage=15 * V)
    r_1 = Resistor(resistance=330 * Ohm)
    zener = Zener(reverse_voltage=6 * V)
    r_2 = Resistor(resistance=300 * Ohm)
    r_load = Potentiometer(resistance=500 * Ohm, setting=1 * ratio)
    amp = OpAmp()
    load_top = Terminal()
    load_bottom = Terminal()
    ground = Ground()

    def architecture(self):
        # The zener node: R_1 from the rail, the zener to ground, R_2 onward.
        self.supply.p1 >> self.r_1.p1
        self.r_1.p2 >> self.zener.p2
        self.zener.p2 >> self.r_2.p1
        # The summing point, and the load from it to the output. The figure's
        # two load terminals are joined by a wire; the current I flows there.
        self.r_2.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r_load.end_a
        self.r_load.wiper >> self.r_load.end_b
        self.r_load.end_b >> self.load_top.probe
        self.load_top.probe >> self.load_bottom.probe
        self.load_bottom.probe >> self.amp.output.signal
        # Ground.
        self.supply.p2 >> self.ground.node
        self.zener.p1 >> self.ground.node
        self.amp.non_inverting.signal >> self.ground.node

    def constraints(self):
        require(equals(self.i_out, over(self.zener.reverse_voltage, self.r_2.resistance)))
        require(
            within(
                self.i_zener,
                minus(
                    over(minus(self.supply.voltage, self.zener.reverse_voltage), self.r_1.resistance),
                    self.i_out,
                ),
                0.001,
            )
        )
        # The output stands at -I R_L, and cannot pass the swing.
        require(equals(self.swing, negative(self.amp.output_low)))
        require(equals(self.r_load_max, over(self.swing, self.i_out)))
        require(at_most(self.r_load.resistance, self.r_load_max))


BENCH = Bench(
    page=51,
    title="Constant Current Generator",
    runs=[
        Run(
            "inside_limit",
            OperatingPoint(),
            measure={
                "i_load": "(v({amp.IN-}) - v({amp.OUT})) / 500",
                "v_zener": "v({zener.K})",
                "i_over_vz_r2": "(v({amp.IN-}) - v({amp.OUT})) / 500 * 300 / v({zener.K})",
                "i_zener": "(15 - v({zener.K})) / 330 - (v({zener.K}) - v({amp.IN-})) / 300",
                "e_out": "v({amp.OUT})",
            },
            claims=[
                Claim(
                    "i_over_vz_r2",
                    1.0,
                    within=1e-4,
                    note=(
                        "I = V_Z / R_2 against the zener voltage the run "
                        "measured: the op amp adds nothing to it."
                    ),
                ),
                Claim(
                    "i_load",
                    "i_out",
                    within=0.01,
                    unit="A",
                    note=(
                        "Held to 1%, not 0.1%: the current is only as good "
                        "as V_Z, and the zener model sits about 0.5% above "
                        "6 V at 7.3 mA. A real 6 V zener is a 5% part."
                    ),
                ),
                Claim(
                    "i_zener",
                    "i_zener",
                    within=0.05,
                    unit="A",
                    note=(
                        "Held to 5%: every 10 mV of V_Z moves it by 64 uA. "
                        "The printed 25 mA is not what 330 Ohm gives."
                    ),
                ),
            ],
            units={"v_zener": "V", "e_out": "V"},
        ),
        Run(
            "past_limit",
            OperatingPoint(),
            settings={"r_load": {"resistance": 800}},
            measure={
                "i_load": "(v({amp.IN-}) - v({amp.OUT})) / 800",
                "e_out": "v({amp.OUT})",
                "i_over_divider": (
                    "(v({amp.IN-}) - v({amp.OUT})) / 800 * 1100 / (v({zener.K}) + 13.5)"
                ),
            },
            claims=[
                Claim(
                    "e_out",
                    -13.5,
                    within=0.001,
                    unit="V",
                    note=(
                        "Not a handbook claim: at 800 Ohm, past the 675 Ohm "
                        "limit, the output is pinned at the -13.5 V swing. "
                        "So 675 Ohm is the largest load, not the smallest."
                    ),
                ),
                Claim(
                    "i_over_divider",
                    1.0,
                    within=1e-3,
                    note=(
                        "With the output pinned the loop is open, and the "
                        "summing point is no longer at ground: R_2 and R_L "
                        "are a plain divider from V_Z to -13.5 V, and I is "
                        "(V_Z + 13.5 V) / (R_2 + R_L), about 17.8 mA."
                    ),
                ),
            ],
            units={"e_out": "V", "i_load": "A"},
        ),
    ],
)
