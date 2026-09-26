"""The deflection coil driver, SBOA092B page 82.

    I / E_I = -R0 / (R1 R3) = -100 mA / Volt

The load floats between the op amp's output and R3 (10 Ohm) to ground, and
R0 feeds the voltage across R3 back to the - input, so the loop holds that
voltage at -E_I R0 / R1 and the current through R3 at -E_I R0 / (R1 R3),
whatever the load is. The load also carries what R0 takes from the same
node, E_I / R1, so the load current is

    I / E_I = -(R0 / (R1 R3) + 1 / R1) = -100.1 mA / Volt

The page drops the second term, which is a thousandth of the first here.

The load is a coil. The figure draws R_L as a resistor; the program makes it
an inductance in series with its winding resistance and records the values
in `coil`. The point of a current drive into a coil is that the current
follows the input even where the coil's own L / R would make a voltage-driven
current lag, so the bench runs d.c. and then a 1 kHz sine, eleven times the
coil's corner, and measures how far the current lags the input.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from decimal import Decimal

from fang.lang import Ohm, Parameter, System, UnitLiteral, kOhm, mH, require
from fang.parts import Inductor, Resistor
from fang.rationale import Chooses, Cites
from fang.simulation import OperatingPoint, Transient

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

#: A transconductance: the current out per volt in.
mA_per_V = UnitLiteral("mA/V")


class DeflectionCoilDriver(System):
    """An inverting amplifier whose feedback is taken from a current-sense resistor."""

    figure = Cites(
        "I / E_I = -R0 / (R1 R3) = -100 mA / Volt. Load must be 'floating', "
        "i.e. ungrounded.",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 82, Deflection Coil Driver",
    )

    coil = Chooses(
        "What is the load?",
        selected="a 10 mH coil with 5 Ohm of winding, as an inductor and a resistor in series",
        alternatives=[
            {
                "option": "a plain resistor, as drawn",
                "reason": "a deflection coil is an inductance, and the reason to "
                "drive one with current is the lag its inductance causes",
            },
        ],
        rationale=(
            "the figure names the load R_L and gives no value",
            "10 mH over 5 Ohm is a 2 ms time constant, an 80 Hz corner, so at "
            "1 kHz a voltage-driven current would lag by 85 degrees",
            "at 50 mA and 1 kHz the coil needs 3.2 V, inside the swing",
        ),
    )

    i_per_volt = Parameter(
        "mA/V",
        default=Decimal("-100.1") * mA_per_V,
        description="coil current per volt: -(R0 / (R1 R3) + 1 / R1)",
    )

    e_in = Terminal()
    r1 = Resistor(resistance=10 * kOhm)
    r0 = Resistor(resistance=10 * kOhm)
    r3 = Resistor(resistance=10 * Ohm)
    coil_winding = Resistor(resistance=5 * Ohm)
    coil_inductance = Inductor(inductance=10 * mH)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.r1.p1
        self.r1.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r0.p1
        self.amp.non_inverting.signal >> self.ground.node

        # The coil floats from the output to the sense node.
        self.amp.output.signal >> self.coil_winding.p1
        self.coil_winding.p2 >> self.coil_inductance.p1
        self.coil_inductance.p2 >> self.r3.p1
        self.r3.p1 >> self.r0.p2
        self.r3.p2 >> self.ground.node

    def constraints(self):
        require(
            equals(
                self.i_per_volt,
                negative(
                    total(
                        over(self.r0.resistance, product(self.r1.resistance, self.r3.resistance)),
                        over(1 * ratio, self.r1.resistance),
                    )
                ),
            )
        )


DROPPED = (
    "The page prints -100 mA / Volt, the current through R3 alone; the coil "
    "also carries the E_I / R1 that R0 takes, 0.1 mA per volt more."
)

BENCH = Bench(
    page=82,
    title="Deflection Coil Driver",
    runs=[
        Run(
            "dc",
            OperatingPoint(),
            drive={"e_in": "DC 1"},
            measure={
                "i_per_volt": "i(l1) / v({e_in.1})",
                "e_out": "v({amp.OUT})",
            },
            claims=[Claim("i_per_volt", "i_per_volt", within=0.001, unit="A/V", note=DROPPED)],
            units={"e_out": "V"},
        ),
        Run(
            "sine",
            Transient(stop="5m", step="0.5u"),
            drive={"e_in": "SIN(0 0.5 1k)"},
            measure={
                "i_pp": "pp i(l1) from=3m to=5m",
                "e_pp": "pp v({e_in.1}) from=3m to=5m",
                "i_per_volt": "-i_pp / e_pp",
                "t_in": "when v({e_in.1})=0 rise=1 td=3.5m",
                "t_coil": "when i(l1)=0 fall=1 td=3.5m",
                "lag": "t_coil - t_in",
                "out_peak": "max v({amp.OUT}) from=3m to=5m",
            },
            claims=[
                Claim(
                    "i_per_volt", "i_per_volt", within=0.005, unit="A/V",
                    note="0.5% rather than 0.1%: at 1 kHz the op amp has 80 dB "
                    "of gain left, and the coil's 63 Ohm of reactance against "
                    "R3 divides what comes back, so the loop is a few hundred "
                    "strong rather than a million",
                ),
                Claim(
                    "lag", 0, within=1e-6, absolute=True, unit="s",
                    note="a voltage across the same coil would drive a current "
                    "lagging 85 degrees, 236 us at 1 kHz",
                ),
            ],
            units={"i_pp": "A", "e_pp": "V", "t_in": "s", "t_coil": "s",
                   "out_peak": "V"},
            note="0.5 V peak at 1 kHz. The coil current is inverted, so it "
            "falls through zero as the input rises through it; the lag is "
            "between the two crossings.",
        ),
    ],
)
