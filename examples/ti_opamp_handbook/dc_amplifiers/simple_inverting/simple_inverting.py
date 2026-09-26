"""The simple inverting (sign changing) amplifier, SBOA092B page 70.

    E_O = -(R_O / R_I) E_I = -100 E_I
    resistor = R_O R_I / (R_I + R_O) = 1 kOhm
    Z_in = R_I = 1 kOhm

The inverting amplifier of page 54 with values: R_I = 1 kOhm, R_O = 100 kOhm.
The page also gives a third resistance, R_O R_I / (R_I + R_O), and does not
draw it. It is the usual bias-compensation resistor, from the non-inverting
input to ground, sized to the resistance the inverting input sees so the two
input bias currents drop the same voltage. In the figure the + input goes
straight to ground, and the program builds what is drawn. The value is kept
as a parameter, `r_compensation`, held to the two resistors; it is 990 Ohm,
which the page rounds to 1 kOhm.

The bench's op amp has no input bias current, so its gain and input impedance
are the page's algebra. One more run puts a bias current on the inverting
input with a card, to show the output error the undrawn resistor is there to
cancel; `bias` records the value used.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Parameter, System, kOhm, Ohm, nA, mV, require
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
    parallel,
    product,
    ratio,
    within,
)


class SimpleInverting(System):
    """E_I through R_I into the summing point, R_O back from E_O, + on ground."""

    figure = Cites(
        "E_O = -(R_O/R_I) E_I = -100 E_I; resistor = R_O R_I/(R_I + R_O) = 1 kOhm; "
        "Z_in = R_I = 1 kOhm",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 70, Simple Inverting sign changing amplifier",
    )

    bias = Chooses(
        "What input bias current does the bias-error run apply?",
        selected="100 nA into the inverting input, applied by a card, in one run only",
        alternatives=[
            {
                "option": "none, and say nothing about the undrawn resistor",
                "reason": (
                    "the page prints its value, so a program that ignores it "
                    "leaves a line of the page unexplained"
                ),
            },
            {
                "option": "a bias-current parameter on the op amp",
                "reason": (
                    "the shared model has an input offset voltage and no bias "
                    "current, and the harness is not this program's to change"
                ),
            },
        ],
        rationale=(
            "100 nA is the order of a general-purpose bipolar input; it is an "
            "illustration, not a part's datasheet value",
            "the + input is on ground as drawn, so there is no resistor there "
            "for the matching current to cross, and the error is the whole I_B R_O",
        ),
    )

    a_v = Parameter("1", default=-100 * ratio, description="E_O / E_I")
    z_in = Parameter("Ohm", default=1 * kOhm, description="what E_I sees: R_I, into a virtual ground")
    r_compensation = Parameter(
        "Ohm",
        default=990 * Ohm,
        description="R_O || R_I, the undrawn resistor from the + input to ground",
    )
    r_compensation_printed = Parameter(
        "Ohm", default=1 * kOhm, description="the value the page prints for it"
    )
    i_bias = Parameter("A", default=100 * nA, description="the bias current the bias run applies")
    e_bias = Parameter(
        "V", default=10 * mV, description="E_O with E_I = 0 and I_B on the - input: I_B R_O"
    )

    e_in = Terminal()
    e_out = Terminal()
    r_in = Resistor(resistance=1 * kOhm)
    r_out = Resistor(resistance=100 * kOhm)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.r_in.p1
        self.r_in.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r_out.p1
        self.r_out.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe
        self.amp.non_inverting.signal >> self.ground.node

    def constraints(self):
        require(equals(self.a_v, negative(over(self.r_out.resistance, self.r_in.resistance))))
        require(equals(self.z_in, self.r_in.resistance))

        # The undrawn compensation resistor: R_O in parallel with R_I is
        # 990.1 Ohm, which the page rounds to 1 kOhm.
        require(
            within(
                parallel(self.r_out.resistance, self.r_in.resistance),
                self.r_compensation,
                0.001,
            )
        )
        require(within(self.r_compensation, self.r_compensation_printed, 0.01))

        # With the + input on ground, the bias current has only R_O to flow in.
        require(equals(self.e_bias, product(self.i_bias, self.r_out.resistance)))


BENCH = Bench(
    page=70,
    title="Simple Inverting sign changing amplifier",
    runs=[
        Run(
            "gain",
            OperatingPoint(),
            drive={"e_in": "DC 0.1"},
            measure={
                "gain": "v({e_out.1}) / v({e_in.1})",
                "z_in": "-v({e_in.1}) / i(vdrive_e_in)",
            },
            claims=[
                Claim("gain", "a_v", within=0.001),
                Claim("z_in", "z_in", within=0.001, unit="Ohm"),
            ],
            note=(
                "E_I = 0.1 V, so E_O = -10 V stays inside the swing. The drive's "
                "current is taken positive into its + terminal, hence the sign."
            ),
        ),
        Run(
            "bias_error",
            OperatingPoint(),
            drive={"e_in": "DC 0"},
            cards=["IBIAS_MINUS {amp.IN-} 0 DC 100n"],
            measure={"e_o": "v({e_out.1})"},
            claims=[
                Claim(
                    "e_o", "e_bias", within=0.001, unit="V",
                    note=(
                        "100 nA drawn out of the - input (see `bias`), E_I at 0 V. "
                        "The same current into the + input through the page's 990 "
                        "Ohm would put it at -99 uV, which times the noise gain of "
                        "101 cancels this; the figure does not draw that resistor, "
                        "so the run does not either"
                    ),
                )
            ],
        ),
    ],
)
