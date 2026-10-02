"""The single-supply a.c. amplifier, SBOA092B page 76.

    "Equivalent to above, with the supply 'floated' above ground."

The simple a.c. amplifier on the same page, run from one supply. R_2 and R_2'
split the supply in half onto the + input, and C_2 holds that node still.
C_I blocks the half-supply from the source, and at d.c. the stage is a
follower of its + input, so the output rests at half the supply. Above the
C_I R_I corner the signal sees the inverting amplifier of page 54 again,
-R_O / R_I = -10, riding on that level.

The page gives no formula and no supply voltage, so the claims are the ones
"equivalent to above" implies: a gain of -10, the 16 Hz corner, and a d.c.
output of half the supply. The program chose the supply and what the op amp
can swing on it (`supply`).
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Hz, Parameter, System, V, kOhm, require, uF
from fang.parts import Capacitor, Resistor
from fang.rationale import Chooses, Cites
from fang.simulation import ACSweep, OperatingPoint, Transient

from handbook import (
    Bench,
    Cell,
    Claim,
    Ground,
    OpAmp,
    Run,
    Terminal,
    corner,
    equals,
    negative,
    over,
    product,
    ratio,
    total,
    within,
)


class SingleSupply(System):
    """The simple a.c. amplifier with its + input biased at half of one supply."""

    figure = Cites(
        "Equivalent to above, with the supply \"floated\" above ground. "
        "(Above: E_O = -10 E_I, f_-3dB = 1 / (2 pi R_I C_I) = 16 Hz.)",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 76, Single Supply",
    )

    supply = Chooses(
        "What is +Supply, and what can the op amp swing on it?",
        selected=(
            "15 V, and an output from 0 V to 13.5 V: to ground at the bottom, "
            "and 1.5 V short of the rail at the top, like the bench's op amp on "
            "+/-15 V"
        ),
        alternatives=[
            {
                "option": "the bench's default +/-13.5 V swing",
                "reason": "a single-supply part cannot go below its only other rail, ground",
            },
            {
                "option": "a rail-to-rail 0 to 15 V swing",
                "reason": "the handbook's op amps are not rail-to-rail; the headroom is the conservative reading",
            },
        ],
        rationale=(
            "the figure labels the rail +Supply and gives no value",
            "15 V is the rail the handbook's other circuits run from",
        ),
    )

    a_v = Parameter("1", default=-10 * ratio, description="E_O / E_I in the midband")
    f_low = Parameter("Hz", default=16 * Hz, description="the low-frequency -3 dB point")
    e_bias = Parameter("V", default=7.5 * V, description="the d.c. level at the output")

    e_in = Terminal()
    e_out = Terminal()
    supply_rail = Cell(voltage=15 * V)
    c_in = Capacitor(capacitance=1 * uF)
    r_in = Resistor(resistance=10 * kOhm)
    r_out = Resistor(resistance=100 * kOhm)
    r_2 = Resistor(resistance=10 * kOhm)
    r_2_prime = Resistor(resistance=10 * kOhm)
    c_2 = Capacitor(capacitance=100 * uF)
    amp = OpAmp(output_high=13.5 * V, output_low=0 * V)
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.c_in.p1
        self.c_in.p2 >> self.r_in.p1
        self.r_in.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r_out.p1
        self.r_out.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe

        # Half the supply onto the + input, held there by C_2.
        self.supply_rail.p1 >> self.r_2.p1
        self.r_2.p2 >> self.amp.non_inverting.signal
        self.amp.non_inverting.signal >> self.r_2_prime.p1
        self.amp.non_inverting.signal >> self.c_2.p1

        self.supply_rail.p2 >> self.ground.node
        self.r_2_prime.p2 >> self.ground.node
        self.c_2.p2 >> self.ground.node

    def constraints(self):
        require(equals(self.a_v, negative(over(self.r_out.resistance, self.r_in.resistance))))
        require(within(self.f_low, corner(self.r_in.resistance, self.c_in.capacitance), 0.01))
        # C_I blocks d.c., so the output follows the + input: the divider's tap.
        require(
            equals(
                self.e_bias,
                product(
                    self.supply_rail.voltage,
                    over(self.r_2_prime.resistance, total(self.r_2.resistance, self.r_2_prime.resistance)),
                ),
            )
        )


BENCH = Bench(
    page=76,
    title="Single Supply",
    runs=[
        Run(
            "bias",
            OperatingPoint(),
            drive={"e_in": "DC 0"},
            measure={"e_out": "v({e_out.1})", "e_plus": "v({amp.IN+})"},
            claims=[Claim("e_out", "e_bias", within=0.001, unit="V")],
            units={"e_plus": "V"},
        ),
        Run(
            "response",
            ACSweep(points=40, start="0.1", stop="10meg"),
            drive={"e_in": "DC 0 AC 1"},
            measure={
                "gain_1k": "find vm({e_out.1}) at=1k",
                "f_3db": "when vdb({e_out.1})=16.9897 cross=1",
            },
            claims=[
                Claim("gain_1k", 10, within=0.001, note="the magnitude of -10"),
                Claim(
                    "f_3db",
                    "f_low",
                    within=0.01,
                    unit="Hz",
                    note="1/(2 pi R_I C_I) is 15.92 Hz, as above; the handbook prints 16",
                ),
            ],
            units={"f_3db": "Hz"},
        ),
        Run(
            "signal",
            Transient(stop="80m", step="2u"),
            drive={"e_in": "SIN(0 0.5 1k)"},
            measure={
                "e_top": "max v({e_out.1}) from=75m to=80m",
                "e_bottom": "min v({e_out.1}) from=75m to=80m",
                "e_mean": "avg v({e_out.1}) from=75m to=80m",
            },
            claims=[
                Claim("e_top", 12.5, within=0.005, unit="V", note="7.5 V + 10 x 0.5 V"),
                Claim("e_bottom", 2.5, within=0.005, unit="V", note="7.5 V - 10 x 0.5 V"),
                Claim("e_mean", "e_bias", within=0.005, unit="V"),
            ],
            note=(
                "A 0.5 V, 1 kHz sine: the output swings 5 V either side of its "
                "7.5 V rest, inside the 0 V to 13.5 V it can reach. It is read "
                "over the last 5 ms of 80, after the 10 ms C_I R_I transient "
                "of switching the sine on has died away. The tolerance is "
                "0.5% for the sampled peaks."
            ),
        ),
    ],
)
