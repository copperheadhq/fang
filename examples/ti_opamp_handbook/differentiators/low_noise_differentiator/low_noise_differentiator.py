"""The low-noise differentiator, SBOA092B page 62.

    E_O / E_I = -j 2 pi f R_O C_I / ((1 + j 2 pi f R_I C_I)(1 + j 2 pi f R_O C_O))

The differentiator with stop, with a 0.001 uF C_O across R_O. The page asks
for R_I C_I = R_O C_O, and its parts meet it: 1 kOhm x 0.1 uF and 100 kOhm x
0.001 uF are both 100 us. So the two poles sit together at
1/(2 pi 100 us) = 1.59 kHz, the "double high frequency cutoff": where the
circuit with stop flattens at R_O/R_I = 100, this one turns over and falls at
20 dB per decade, so the noise the plain differentiator amplifies most is cut
instead.

With both poles at one frequency the top of the response is a single point,
not a plateau. At f_c the two poles each take a factor of sqrt(2) and turn
the phase by 90 degrees between them, so the gain there is
(R_O/R_I) / 2 = 50, real and inverted. A decade above, 2 pi f R_O C_I is 1000
and the poles divide it by 101.

The figure gives every value, so nothing was chosen. The page's phrase "drift
compensating resistor" beside R_I C_I = R_O C_O names no part in the figure,
and the program does not invent one.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from decimal import Decimal

from fang.lang import Hz, Parameter, System, kHz, kOhm, nF, require, uF
from fang.parts import Capacitor, Resistor
from fang.rationale import Cites
from fang.simulation import ACSweep

from handbook import (
    Bench,
    Claim,
    Ground,
    OpAmp,
    Run,
    Terminal,
    corner,
    equals,
    over,
    product,
    ratio,
    total,
    within,
)


class LowNoiseDifferentiator(System):
    """E_I through R_I and C_I into the summing point, R_O and C_O across it."""

    figure = Cites(
        "R_I C_I = R_O C_O drift compensating resistor. Double high frequency cutoff",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 62, Low Noise",
    )

    f_corner = Parameter(
        "Hz",
        default=Decimal("1.59155") * kHz,
        description="1/(2 pi R_I C_I) = 1/(2 pi R_O C_O): both poles",
    )
    f_unity = Parameter(
        "Hz", default=Decimal("15.9155") * Hz, description="1/(2 pi R_O C_I), gain 1"
    )
    a_peak = Parameter(
        "1", default=50 * ratio, description="R_O / (2 R_I): the gain at f_corner"
    )
    a_decade = Parameter(
        "1",
        default=Decimal("9.90099") * ratio,
        description="10 R_O / R_I / (1 + 10^2): the gain a decade above f_corner",
    )

    e_in = Terminal()
    common = Terminal()
    e_out = Terminal()
    r_in = Resistor(resistance=1 * kOhm)
    c_in = Capacitor(capacitance=Decimal("0.1") * uF)
    r_out = Resistor(resistance=100 * kOhm)
    c_out = Capacitor(capacitance=1 * nF)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.r_in.p1
        self.r_in.p2 >> self.c_in.p1
        self.c_in.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r_out.p1
        self.amp.inverting.signal >> self.c_out.p1
        self.r_out.p2 >> self.amp.output.signal
        self.c_out.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe
        self.amp.non_inverting.signal >> self.ground.node
        self.common.probe >> self.ground.node

    def constraints(self):
        r_i, c_i = self.r_in.resistance, self.c_in.capacitance
        r_o, c_o = self.r_out.resistance, self.c_out.capacitance
        # The page's rule, which puts the two poles together.
        require(equals(product(r_i, c_i), product(r_o, c_o)))
        require(within(self.f_corner, corner(r_i, c_i), 0.00001))
        require(within(self.f_unity, corner(r_o, c_i), 0.00001))
        # At f_corner, 2 pi f R_O C_I is R_O/R_I and each pole divides by
        # |1 + j| = sqrt(2), so the two together halve it.
        require(equals(self.a_peak, over(r_o, product(2 * ratio, r_i))))
        require(
            within(
                self.a_decade,
                over(product(10 * ratio, over(r_o, r_i)), total(1 * ratio, 100 * ratio)),
                0.00001,
            )
        )


BENCH = Bench(
    page=62,
    title="Low Noise Differentiator",
    runs=[
        Run(
            "response",
            ACSweep(points=200, start="1", stop="1meg"),
            drive={"e_in": "DC 0 AC 1"},
            measure={
                "f_unity": "when vm({e_out.1})=1",
                "gain_corner": "find vm({e_out.1}) at=1591.55",
                "gain_peak": "max vm({e_out.1})",
                "gain_decade": "find vm({e_out.1}) at=15915.5",
                "f_unity_high": "when vm({e_out.1})=1 fall=1",
            },
            claims=[
                Claim("f_unity", "f_unity", within=0.001, unit="Hz"),
                Claim("gain_corner", "a_peak", within=0.001,
                      note="Half of R_O/R_I: both poles at once, sqrt(2) each"),
                Claim("gain_peak", "a_peak", within=0.001,
                      note="and it is the top of the response: no plateau"),
                Claim("gain_decade", "a_decade", within=0.02,
                      note=(
                          "1000/101: falling at 20 dB per decade, where the circuit "
                          "with stop holds near 100. 2%: a decade up, the op amp's "
                          "loop gain is only about 60 and takes 1.5% off."
                      )),
            ],
            units={"f_unity_high": "Hz"},
            note=(
                "The second unity crossing, near 159 kHz, is where the falling "
                "gain passes 1 on its way down; it is not a claim of the page."
            ),
        ),
    ],
)
