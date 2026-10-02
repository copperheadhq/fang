"""The differentiator with "stop", SBOA092B page 61.

    E_O / E_I = -j 2 pi f R_O C_I / (1 + j 2 pi f R_I C_I)

The plain differentiator above it on the page, with a 1 kOhm R_I in series
with C_I. Below 1/(2 pi R_I C_I) C_I's reactance dominates R_I and the
circuit differentiates, its gain 2 pi f R_O C_I passing unity at
1/(2 pi R_O C_I). Above it R_I dominates, and the circuit becomes an inverting
amplifier of gain R_O/R_I = 100: the "stop" that keeps the gain from rising
into the op amp's roll-off, which is what made the plain circuit ring.

The page prints the two corners as 0.6 kHz and 16 kHz. Neither is what its own
formula gives for its own parts: 1/(2 pi 1k 0.1u) is 1.59 kHz and
1/(2 pi 100k 0.1u) is 15.9 Hz. The program holds the values the formulas give
and the bench measures them; the printed numbers are quoted in `figure` and
the discrepancy is stated beside each claim.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from decimal import Decimal

from fang.lang import Hz, Parameter, System, kHz, kOhm, require, uF
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
    ratio,
    within,
)


class DifferentiatorWithStop(System):
    """E_I through R_I and C_I in series into the summing point, R_O back."""

    figure = Cites(
        "Input resistor sets high frequency cutoff. High frequency cutoff: "
        "F_O = 1/(2 pi R_I C_I) = 0.6 kHz. Low frequency cutoff: "
        "F_I = 1/(2 pi R_O C_I) = 16 kHz",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 61, With \"Stop\"",
    )

    f_high = Parameter(
        "Hz",
        default=Decimal("1.59155") * kHz,
        description="1/(2 pi R_I C_I): where the derivative stops and the gain flattens",
    )
    f_low = Parameter(
        "Hz",
        default=Decimal("15.9155") * Hz,
        description="1/(2 pi R_O C_I): where the derivative's gain passes unity",
    )
    a_flat = Parameter("1", default=100 * ratio, description="R_O / R_I, above f_high")
    a_corner = Parameter(
        "1",
        default=Decimal("70.7107") * ratio,
        description="R_O / R_I / sqrt(2): the gain at f_high",
    )

    e_in = Terminal()
    common = Terminal()
    e_out = Terminal()
    r_in = Resistor(resistance=1 * kOhm)
    c_in = Capacitor(capacitance=Decimal("0.1") * uF)
    r_out = Resistor(resistance=100 * kOhm)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.r_in.p1
        self.r_in.p2 >> self.c_in.p1
        self.c_in.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r_out.p1
        self.r_out.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe
        self.amp.non_inverting.signal >> self.ground.node
        self.common.probe >> self.ground.node

    def constraints(self):
        r_i, c_i, r_o = self.r_in.resistance, self.c_in.capacitance, self.r_out.resistance
        require(within(self.f_high, corner(r_i, c_i), 0.00001))
        require(within(self.f_low, corner(r_o, c_i), 0.00001))
        require(equals(self.a_flat, over(r_o, r_i)))
        # At f_high, R_I and C_I's reactance are equal, and |R_I + 1/(j w C_I)|
        # is sqrt(2) R_I, so the gain is the flat gain over sqrt(2).
        require(within(over(self.a_flat, self.a_corner), Decimal("1.41421356") * ratio, 0.000001))


BENCH = Bench(
    page=61,
    title="Differentiators, With \"Stop\"",
    runs=[
        Run(
            "response",
            ACSweep(points=200, start="1", stop="1meg"),
            drive={"e_in": "DC 0 AC 1"},
            measure={
                "f_low": "when vm({e_out.1})=1",
                "gain_100": "find vm({e_out.1}) at=100",
                "f_high": "when vm({e_out.1})=70.7107",
                "gain_f_high": "find vm({e_out.1}) at=1591.55",
                "gain_peak": "max vm({e_out.1})",
                "f_3db_op_amp": "when vm({e_out.1})=70.7107 fall=1",
            },
            claims=[
                Claim("f_low", "f_low", within=0.001, unit="Hz",
                      note="The handbook prints 16 kHz; 1/(2 pi R_O C_I) is 15.9 Hz."),
                Claim("gain_100", 6.2707, within=0.001,
                      note=(
                          "100 Hz: 2 pi f R_O C_I = 6.283, less the first touch of "
                          "R_I, 1/sqrt(1 + (f/f_high)^2)"
                      )),
                Claim("f_high", "f_high", within=0.02, unit="Hz",
                      note=(
                          "The handbook prints 0.6 kHz; 1/(2 pi R_I C_I) is 1.59 "
                          "kHz. 2%: the gain at the corner comes out 0.8% high "
                          "(below), and on a slope of half a decade per decade "
                          "that moves the 3 dB crossing about 1.6% lower."
                      )),
                Claim("gain_f_high", "a_corner", within=0.01,
                      note=(
                          "R_O/R_I over sqrt(2), 3 dB down at the corner. 1%: the "
                          "loop gain there is only about 88, and with the op amp's "
                          "90 degree lag the finite gain lifts |E_O/E_I| by 0.8% "
                          "rather than lowering it."
                      )),
                Claim("gain_peak", "a_flat", within=0.005,
                      note=(
                          "The top of the plateau, R_O/R_I. The op amp, closed for "
                          "a noise gain of 101, rolls off near 100 kHz, only 60 "
                          "times above f_high, so the plateau is a rounded top "
                          "rather than a flat one."
                      )),
            ],
            units={"f_3db_op_amp": "Hz"},
        ),
    ],
)
