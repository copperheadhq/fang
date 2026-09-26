"""The a.c. non-inverting amplifier, SBOA092B page 77.

    E_O = (R_O + R_I) / R_I x E_I = 10 E_I
    f_-3dB = 1 / (2 pi R_I C_I) = 0.16 Hz

E_I reaches the + input through C_2, and R_2 returns that input to ground.
R_0 (90 kOhm) from the output and R_1 (10 kOhm) in series with C_1 (100 uF)
to ground set the gain: 1 + 90k/10k = 10 in the midband, falling to 1 at
d.c., where C_1 is open and the output offset is not multiplied.

There are two low-frequency corners, not one. The printed 0.16 Hz is the
gain network's, 1/(2 pi R_1 C_1) = 0.159 Hz (the formula calls them R_I and
C_I; the figure labels them R_1 and C_1). The input network C_2 R_2 turns at
1/(2 pi 100k 1u) = 1.59 Hz, ten times higher, and it is that one the source
sees first: the circuit is 3 dB down at 1.6 Hz, not 0.16. The program encodes
what the drawn circuit does (`f_low`, from C_2 and R_2), cites what the page
prints, and the bench measures both corners.
"""

import sys
from decimal import Decimal
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
    at_least,
    corner,
    equals,
    over,
    product,
    ratio,
    total,
    within,
)


class AcNonInverting(System):
    """E_I through C_2 onto the + input, R_0 over R_1 and C_1 setting the gain."""

    figure = Cites(
        "E_O in phase with E_I. E_O = (R_O + R_I) / R_I = 10 E_I. "
        "Low frequency rolloff f_-3dB = 1 / (2 pi R_I C_I) = 0.16 Hz",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 77, Non-Inverting",
    )

    a_v = Parameter("1", default=10 * ratio, description="E_O / E_I in the midband")
    f_gain = Parameter("Hz", default=Decimal("0.16") * Hz, description="the gain network's corner, as printed")
    f_input = Parameter("Hz", default=Decimal("1.6") * Hz, description="the input network's corner")
    f_low = Parameter("Hz", default=Decimal("1.6") * Hz, description="where the circuit is 3 dB down")

    e_in = Terminal()
    e_out = Terminal()
    c_2 = Capacitor(capacitance=1 * uF)
    r_2 = Resistor(resistance=100 * kOhm)
    r_1 = Resistor(resistance=10 * kOhm)
    c_1 = Capacitor(capacitance=100 * uF)
    r_0 = Resistor(resistance=90 * kOhm)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.c_2.p1
        self.c_2.p2 >> self.amp.non_inverting.signal
        self.amp.non_inverting.signal >> self.r_2.p1

        self.amp.inverting.signal >> self.r_1.p1
        self.r_1.p2 >> self.c_1.p1
        self.amp.inverting.signal >> self.r_0.p1
        self.r_0.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe

        self.r_2.p2 >> self.ground.node
        self.c_1.p2 >> self.ground.node

    def constraints(self):
        require(
            equals(
                self.a_v,
                over(total(self.r_0.resistance, self.r_1.resistance), self.r_1.resistance),
            )
        )
        # The printed corner is the gain network's, rounded from 0.159 Hz.
        require(within(self.f_gain, corner(self.r_1.resistance, self.c_1.capacitance), 0.01))
        # The input network's is ten times higher, 1.59 Hz, and it is the one
        # that sets the circuit's -3 dB point.
        require(within(self.f_input, corner(self.r_2.resistance, self.c_2.capacitance), 0.01))
        require(at_least(self.f_input, product(self.f_gain, 5 * ratio)))
        require(equals(self.f_low, self.f_input))


BENCH = Bench(
    page=77,
    title="Non-Inverting",
    runs=[
        Run(
            "response",
            ACSweep(points=40, start="0.001", stop="10meg"),
            drive={"e_in": "DC 0 AC 1"},
            measure={
                "gain_1k": "find vm({e_out.1}) at=1k",
                "phase_1k": "find vp({e_out.1}) at=1k",
                "f_3db": "when vdb({e_out.1})=16.9897 cross=1",
                "out_at_gain_corner": "find vm({e_out.1}) at=0.159155",
                "plus_at_gain_corner": "find vm({amp.IN+}) at=0.159155",
                "gain_network": "out_at_gain_corner / plus_at_gain_corner",
                "plus_at_input_corner": "find vm({amp.IN+}) at=1.59155",
            },
            claims=[
                Claim("gain_1k", "a_v", within=0.001),
                Claim(
                    "phase_1k",
                    0,
                    within=0.01,
                    absolute=True,
                    note="in radians: E_O in phase with E_I, as the page says",
                ),
                Claim(
                    "f_3db",
                    "f_low",
                    within=0.01,
                    unit="Hz",
                    note=(
                        "the handbook prints 0.16 Hz; the drawn circuit is 3 dB "
                        "down at 1.61 Hz, set by C_2 R_2 (1.59 Hz) with a "
                        "little from the gain network"
                    ),
                ),
                Claim(
                    "gain_network",
                    7.106,
                    within=0.001,
                    note=(
                        "E_O over the + input at 1/(2 pi R_1 C_1) = 0.159 Hz: "
                        "sqrt(1 + 10^2) / sqrt(2), the gain network 3 dB down "
                        "from 10. This is the corner the page prints"
                    ),
                ),
                Claim(
                    "plus_at_input_corner",
                    0.7071,
                    within=0.001,
                    unit="V",
                    note="the + input 3 dB down at 1/(2 pi R_2 C_2) = 1.59 Hz: the corner that comes first",
                ),
            ],
            units={"out_at_gain_corner": "V", "plus_at_gain_corner": "V"},
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
                    note="C_2 blocks the 1 V; R_2 holds the + input at ground",
                )
            ],
        ),
    ],
)
