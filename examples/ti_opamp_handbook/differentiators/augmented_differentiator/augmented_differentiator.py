"""The augmented differentiator, SBOA092B page 62.

    E_O = -(R_O/R_I) E_I - R_O C_I dE_I/dt = -E_I - (1/100) dE_I/dt

C_I and R_I sit side by side between E_I and the summing point, and R_O runs
from the output back to it. R_I makes an inverting amplifier of gain
-R_O/R_I = -1, C_I a differentiator of time constant R_O C_I = 10 ms, and the
summing point adds the two currents: "sums input and its derivative". In
frequency terms the gain is -(1 + j 2 pi f 10 ms), flat at 1 up to
1/(2 pi 10 ms) = 15.9 Hz and a derivative above it.

R2, 50 kOhm from the + input to ground, carries no signal. It is R_I in
parallel with R_O, the resistance the - input sees to ground at DC, so the
two input bias currents drop the same voltage and cancel. The program holds it
to that rule. The bench's op amp has no bias current, so the simulation cannot
show what R2 is for; it shows only that R2 does no harm.

The derivative has no stop, so this circuit shares the plain differentiator's
peak near 12.6 kHz, where its rising noise gain meets the op amp's roll-off.
The page does not mention it; the bench measures it, and does not claim it.

The figure gives every value, so nothing was chosen.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from decimal import Decimal

from fang.lang import Hz, Parameter, System, kOhm, ms, require, uF
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
    parallel,
    product,
    ratio,
    within,
)


class AugmentedDifferentiator(System):
    """E_I through C_I and R_I side by side into the summing point, R_O back."""

    figure = Cites(
        "E_O = -R_O E_I / R_I - R_O C_I dE_I/dt; E_O = -E_I - (1/100) dE_I/dt. "
        "Sums input and its derivative",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 62, Augmented Differentiator",
    )

    a_dc = Parameter("1", default=-1 * ratio, description="-R_O / R_I, the E_I term")
    time_constant = Parameter(
        "s", default=10 * ms, description="R_O C_I, the dE_I/dt term: 1/100 s"
    )
    f_equal = Parameter(
        "Hz",
        default=Decimal("15.9155") * Hz,
        description="1/(2 pi R_I C_I): where the two terms are equal",
    )

    e_in = Terminal()
    common = Terminal()
    e_out = Terminal()
    c_in = Capacitor(capacitance=Decimal("0.1") * uF)
    r_in = Resistor(resistance=100 * kOhm)
    r_out = Resistor(resistance=100 * kOhm)
    r_bias = Resistor(resistance=50 * kOhm)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.c_in.p1
        self.e_in.probe >> self.r_in.p1
        self.c_in.p2 >> self.amp.inverting.signal
        self.r_in.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r_out.p1
        self.r_out.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe
        self.amp.non_inverting.signal >> self.r_bias.p1
        self.r_bias.p2 >> self.ground.node
        self.common.probe >> self.ground.node

    def constraints(self):
        r_i, c_i, r_o = self.r_in.resistance, self.c_in.capacitance, self.r_out.resistance
        require(equals(self.a_dc, negative(over(r_o, r_i))))
        require(equals(self.time_constant, product(r_o, c_i)))
        # The two terms meet where C_I's reactance equals R_I.
        require(within(self.f_equal, corner(r_i, c_i), 0.00001))
        # Bias compensation: the + input sees what the - input sees at DC.
        require(equals(self.r_bias.resistance, parallel(r_i, r_o)))


BENCH = Bench(
    page=62,
    title="Augmented Differentiator",
    runs=[
        Run(
            "input_term",
            OperatingPoint(),
            drive={"e_in": "DC 1"},
            measure={"gain": "v({e_out.1}) / v({e_in.1})"},
            claims=[Claim("gain", "a_dc", within=0.001,
                          note="At DC the derivative is zero and only -E_I is left")],
        ),
        Run(
            "both_terms",
            ACSweep(points=100, start="1", stop="1k"),
            drive={"e_in": "DC 0 AC 1"},
            measure={
                "gain_equal": "find vm({e_out.1}) at=15.9155",
                "phase_equal": "find vp({e_out.1}) at=15.9155",
                "gain_159": "find vm({e_out.1}) at=159.155",
                "gain_1": "find vm({e_out.1}) at=1",
            },
            claims=[
                Claim("gain_equal", 1.41421, within=0.001,
                      note="|1 + j| at f_equal: the two terms equal and 90 degrees apart"),
                Claim("phase_equal", -2.35619, within=0.001,
                      note="-3 pi/4 radians: -(1 + j), inverted and 45 degrees ahead"),
                Claim("gain_159", 10.0499, within=0.001,
                      note="|1 + j 10| a decade up, where the derivative dominates"),
                Claim("gain_1", 1.00197, within=0.001,
                      note="|1 + j 2 pi 1 Hz 10 ms|: at 1 Hz, nearly E_I alone"),
            ],
            note=(
                "The page's E_O = -E_I - (1/100) dE_I/dt, in frequency terms: "
                "E_O/E_I = -(1 + j 2 pi f x 0.01 s)."
            ),
        ),
        Run(
            "peak",
            ACSweep(variation="lin", points=2401, start="12k", stop="13.2k"),
            drive={"e_in": "DC 0 AC 1"},
            measure={
                "f_peak": "when vi({e_out.1})=0",
                "gain_peak_db": "max vdb({e_out.1})",
            },
            units={"f_peak": "Hz", "gain_peak_db": "dB"},
            note=(
                "Not a claim of the page. The derivative has no stop, so the "
                "noise gain rises like the plain differentiator's and meets the "
                "10 MHz op amp's roll-off near sqrt(GBW x 15.9 Hz) = 12.6 kHz."
            ),
        ),
    ],
)
