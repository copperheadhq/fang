"""The simple a.c. amplifier, SBOA092B page 76.

    E_O = -R_O / R_I x E_I = -10 E_I
    Z_in = 10 kOhm
    f_-3dB = 1 / (2 pi R_I C_I) = 16 Hz

The inverting amplifier of page 54 with C_I in series with R_I. The summing
point is a virtual ground, so C_I and R_I make a single high-pass whose
corner is the whole of the low-frequency roll-off, and above it the stage is
the inverting amplifier again. At d.c. C_I is open and the output sits at the
+ input, ground.

The figure gives every value, so the program chooses nothing. 1/(2 pi 10k 1u)
is 15.92 Hz, which the page rounds to 16, and the claim is held with that
rounding (`within`, 1%).
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Hz, Parameter, System, kOhm, require, uF
from fang.parts import Capacitor, Resistor
from fang.rationale import Cites
from fang.simulation import ACSweep, OperatingPoint

from handbook import (
    Bench,
    Claim,
    Ground,
    OpAmp,
    Run,
    Terminal,
    corner,
    equals,
    negative,
    over,
    ratio,
    within,
)


class SimpleAcAmplifier(System):
    """E_I through C_I and R_I into the summing point, R_O back from the output."""

    figure = Cites(
        "E_O = -R_O / R_I E_I = -10 E_I, Z_in = 10 kOhm; "
        "low frequency rolloff begins: f_-3dB = 1 / (2 pi R_I C_I) = 16 Hz",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 76, Simple Amplifier",
    )

    a_v = Parameter("1", default=-10 * ratio, description="E_O / E_I in the midband")
    z_in = Parameter("Ohm", default=10 * kOhm, description="what E_I sees in the midband")
    f_low = Parameter("Hz", default=16 * Hz, description="the low-frequency -3 dB point, as printed")

    e_in = Terminal()
    e_out = Terminal()
    c_in = Capacitor(capacitance=1 * uF)
    r_in = Resistor(resistance=10 * kOhm)
    r_out = Resistor(resistance=100 * kOhm)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.c_in.p1
        self.c_in.p2 >> self.r_in.p1
        self.r_in.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r_out.p1
        self.r_out.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe
        self.amp.non_inverting.signal >> self.ground.node

    def constraints(self):
        require(equals(self.a_v, negative(over(self.r_out.resistance, self.r_in.resistance))))
        require(equals(self.z_in, self.r_in.resistance))
        # 15.92 Hz, printed as 16.
        require(within(self.f_low, corner(self.r_in.resistance, self.c_in.capacitance), 0.01))


BENCH = Bench(
    page=76,
    title="Simple Amplifier",
    runs=[
        Run(
            "response",
            ACSweep(points=40, start="0.1", stop="10meg"),
            drive={"e_in": "DC 0 AC 1"},
            measure={
                "gain_1k": "find vm({e_out.1}) at=1k",
                "i_in_1k": "find i(vdrive_e_in) at=1k",
                "z_in": "-1 / i_in_1k",
                "f_3db": "when vdb({e_out.1})=16.9897 cross=1",
                "gain_1hz": "find vm({e_out.1}) at=1",
                "f_high": "when vdb({e_out.1})=16.9897 cross=2",
            },
            claims=[
                Claim("gain_1k", 10, within=0.001, note="the magnitude of -10"),
                Claim(
                    "z_in",
                    "z_in",
                    within=0.001,
                    unit="Ohm",
                    note=(
                        "the 1 V drive over the in-phase part of its current at "
                        "1 kHz, where C_I is 159 Ohm against 10 kOhm and moves "
                        "it by 0.03%"
                    ),
                ),
                Claim(
                    "f_3db",
                    "f_low",
                    within=0.01,
                    unit="Hz",
                    note="1/(2 pi R_I C_I) is 15.92 Hz; the handbook prints 16",
                ),
            ],
            units={"f_high": "Hz", "i_in_1k": "A"},
            note=(
                "The -3 dB points are where the gain falls to 20 dB - 3.01 dB. "
                "The upper one is not a handbook claim: it is the op amp's "
                "10 MHz over a noise gain of 11. At 1 Hz, a decade and more "
                "below the corner, the gain falls 20 dB per decade."
            ),
        ),
        Run(
            "dc",
            OperatingPoint(),
            drive={"e_in": "DC 1"},
            measure={"e_out": "v({e_out.1})"},
            claims=[
                Claim(
                    "e_out",
                    0,
                    within=1e-6,
                    absolute=True,
                    unit="V",
                    note="C_I blocks the 1 V: at d.c. the stage follows its + input, ground",
                )
            ],
        ),
    ],
)
