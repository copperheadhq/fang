"""The differentiator, SBOA092B page 61 (and Figure 43 on page 38).

    E_O = -R_O C_I dE_I/dt

C_I carries E_I into the summing point and R_O runs from the output back to
it. The current through C_I is C_I dE_I/dt, and R_O turns it into a voltage,
so the gain rises with frequency, 2 pi f R_O C_I, passing unity where C_I's
reactance equals R_O.

The figure names the two parts and gives them no values, so `values` records
the pair chosen here: 0.1 uF and 100 kOhm, the C_I and R_O of the "with stop"
figure below it on the same page, which puts the unity-gain point at 15.9 Hz,
where Figure 43 draws X_C = R_O.

The page says the circuit is not usable as drawn, and Figure 43 shows why: the
rising gain meets the op amp's falling open-loop gain, and there the loop has
nothing left to damp it. The two lines cross where 2 pi f R_O C_I equals
GBW / f, at f = sqrt(GBW f_1) with f_1 = 1/(2 pi R_O C_I). With the bench's
10 MHz op amp that is 12.6 kHz, and the program claims the peak there. How
tall the peak is depends on the op amp's own pole and is reported as measured.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from decimal import Decimal

from fang.lang import Hz, Parameter, System, kHz, kOhm, ms, require, uF
from fang.parts import Capacitor, Resistor
from fang.rationale import Chooses, Cites
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
    product,
    within,
)


class Differentiator(System):
    """E_I through C_I into the summing point, R_O back from the output."""

    figure = Cites(
        "E_O = -R_O C_I dE_I/dt. The ideal differentiator circuit is not generally "
        "usable in its simple form",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 61, Differentiators",
    )

    values = Chooses(
        "What are C_I and R_O?",
        selected="0.1 uF and 100 kOhm, a 10 ms time constant",
        alternatives=[
            {
                "option": "leave them unknown",
                "reason": "a derivative with no time constant is not a claim anything can check",
            },
            {
                "option": "a shorter time constant, such as 0.1 uF and 10 kOhm",
                "reason": "it moves the peak up to 40 kHz and does not change what the figure shows",
            },
        ],
        rationale=(
            "the figure names C_I and R_O and gives no values",
            "the same page's differentiator with stop uses 0.1 uF and 100 kOhm",
            "Figure 43 draws X_C = R_O near 16 Hz, which 1/(2 pi 100k 0.1u) is",
        ),
    )

    time_constant = Parameter("s", default=10 * ms, description="R_O C_I")
    f_unity = Parameter(
        "Hz", default=Decimal("15.9155") * Hz, description="where 2 pi f R_O C_I = 1"
    )
    f_peak = Parameter(
        "Hz",
        default=Decimal("12.6157") * kHz,
        description="sqrt(GBW f_unity): where the rising gain meets the open-loop roll-off",
    )

    e_in = Terminal()
    common = Terminal()
    e_out = Terminal()
    c_in = Capacitor(capacitance=Decimal("0.1") * uF)
    r_out = Resistor(resistance=100 * kOhm)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.c_in.p1
        self.c_in.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r_out.p1
        self.r_out.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe
        self.amp.non_inverting.signal >> self.ground.node
        self.common.probe >> self.ground.node

    def constraints(self):
        r_o, c_i = self.r_out.resistance, self.c_in.capacitance
        require(equals(self.time_constant, product(r_o, c_i)))
        require(within(self.f_unity, corner(r_o, c_i), 0.00001))
        # Written squared, since the expression tree has no square root:
        # f_peak^2 = GBW f_unity.
        require(
            within(
                product(self.f_peak, self.f_peak),
                product(self.amp.gain_bandwidth, self.f_unity),
                0.0001,
            )
        )


BENCH = Bench(
    page=61,
    title="Differentiators",
    runs=[
        Run(
            "derivative",
            ACSweep(points=100, start="1", stop="1k"),
            drive={"e_in": "DC 0 AC 1"},
            measure={
                "f_unity": "when vm({e_out.1})=1",
                "gain_100": "find vm({e_out.1}) at=100",
                "phase_100": "find vp({e_out.1}) at=100",
            },
            claims=[
                Claim("f_unity", "f_unity", within=0.001, unit="Hz"),
                Claim("gain_100", 6.2832, within=0.001,
                      note="2 pi x 100 Hz x 10 ms: the gain of a derivative rises with f"),
                Claim("phase_100", -1.5708, within=0.001,
                      note="-pi/2 radians: -j 2 pi f R_O C_I, a derivative inverted"),
            ],
            note=(
                "Well below the peak the circuit is what the page says: a gain of "
                "2 pi f R_O C_I, 90 degrees behind the inversion."
            ),
        ),
        Run(
            "peak",
            ACSweep(variation="lin", points=2401, start="12k", stop="13.2k"),
            drive={"e_in": "DC 0 AC 1"},
            measure={
                "f_peak": "when vi({e_out.1})=0",
                "gain_peak": "max vm({e_out.1})",
                "gain_peak_db": "max vdb({e_out.1})",
            },
            claims=[
                Claim("f_peak", "f_peak", within=0.001, unit="Hz",
                      note=(
                          "Where the output's imaginary part changes sign, which for "
                          "a resonance this narrow is the top of the peak."
                      )),
            ],
            units={"gain_peak_db": "dB"},
            note=(
                "The handbook's Figure 43 point. The rising gain meets the 10 MHz "
                "op amp's roll-off at sqrt(GBW f_unity) and the loop is left with "
                "almost no damping, so a gain the page calls 2 pi f R_O C_I (793 "
                "there) peaks hundreds of times higher. The height is the op amp "
                "model's, and is reported, not claimed."
            ),
        ),
    ],
)
