"""The chopper-stabilized inverting amplifier, SBOA092B page 70.

    E_O = -(R_O / R_I) E_I = -100 E_I        "Improved drift and stability."

The same circuit as the simple inverting amplifier above it on the page,
R_I = 1 kOhm and R_O = 100 kOhm, with the op amp named: a TLC265x, a
chopper-stabilized part. The page's only claim for it is improved drift, and
a DC amplifier's drift shows up as its input offset voltage multiplied by the
noise gain, 1 + R_O/R_I = 101.

The page gives no offsets, so `offsets` records the two used: 1 uV for the
TLC2652 (its datasheet maximum at 25 C) and 2 mV for a general-purpose op amp
in the same socket. The bench runs the gain once, then E_I = 0 with each
offset, and claims the output error is 101 times the offset in both.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Parameter, System, kOhm, mV, uV, require
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
    product,
    ratio,
    total,
)


class ChopperStabilized(System):
    """E_I through R_I into a chopper-stabilized op amp's summing point, R_O back."""

    figure = Cites(
        "E_O = -(R_O/R_I) E_I (R_I 1 kOhm, R_O 100 kOhm, TLC265x). "
        "Improved drift and stability",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 70, Chopper Stabilized",
    )

    offsets = Chooses(
        "What input offsets does the comparison use?",
        selected=(
            "1 uV for the TLC265x, and 2 mV for a general-purpose op amp put in "
            "its place for one run"
        ),
        alternatives=[
            {
                "option": "the model's default of no offset",
                "reason": "then both parts give 0 V out and the page's claim shows nothing",
            },
            {
                "option": "a drift in uV per degree, swept over temperature",
                "reason": (
                    "the model has no temperature dependence; an offset at one "
                    "temperature is what it can carry, and drift is that offset "
                    "moving"
                ),
            },
        ],
        rationale=(
            "1 uV is the TLC2652's maximum input offset at 25 C in its datasheet "
            "(typically about 0.5 uV)",
            "2 mV is the order of a general-purpose bipolar or JFET op amp's "
            "offset; it stands for the class, not a named part",
        ),
    )

    a_v = Parameter("1", default=-100 * ratio, description="E_O / E_I")
    noise_gain = Parameter(
        "1", default=101 * ratio, description="1 + R_O / R_I: what an input offset is multiplied by"
    )
    vos_general = Parameter(
        "V", default=2 * mV, description="a general-purpose op amp's offset, for comparison"
    )
    error_chopper = Parameter(
        "V", default=101 * uV, description="|E_O| at E_I = 0 with the TLC265x"
    )
    error_general = Parameter(
        "V", default=202 * mV, description="|E_O| at E_I = 0 with the general-purpose part"
    )

    e_in = Terminal()
    e_out = Terminal()
    r_in = Resistor(resistance=1 * kOhm)
    r_out = Resistor(resistance=100 * kOhm)
    amp = OpAmp(input_offset=1 * uV)
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
        require(
            equals(
                self.noise_gain,
                total(1 * ratio, over(self.r_out.resistance, self.r_in.resistance)),
            )
        )
        # An offset at either input is amplified by the noise gain, not the
        # signal gain: 101, not 100.
        require(equals(self.error_chopper, product(self.amp.input_offset, self.noise_gain)))
        require(equals(self.error_general, product(self.vos_general, self.noise_gain)))


BENCH = Bench(
    page=70,
    title="Chopper Stabilized",
    runs=[
        Run(
            "gain",
            OperatingPoint(),
            drive={"e_in": "DC 0.1"},
            measure={"gain": "v({e_out.1}) / v({e_in.1})"},
            claims=[
                Claim("gain", "a_v", within=0.001,
                      note="the 1 uV offset moves E_O by 101 uV of its -10 V"),
            ],
        ),
        Run(
            "offset_chopper",
            OperatingPoint(),
            drive={"e_in": "DC 0"},
            measure={"error": "abs(v({e_out.1}))"},
            claims=[Claim("error", "error_chopper", within=0.001, unit="V")],
            note="E_I at 0 V: everything at the output is the TLC265x's 1 uV times 101.",
        ),
        Run(
            "offset_general",
            OperatingPoint(),
            drive={"e_in": "DC 0"},
            settings={"amp": {"input_offset": 0.002}},
            measure={"error": "abs(v({e_out.1}))"},
            claims=[Claim("error", "error_general", within=0.001, unit="V")],
            note=(
                "The same circuit with a 2 mV general-purpose op amp in the "
                "socket: 2000 times the error."
            ),
        ),
    ],
)
