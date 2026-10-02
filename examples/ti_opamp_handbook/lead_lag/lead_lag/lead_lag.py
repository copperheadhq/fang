"""The lead-lag network, SBOA092B page 86.

    printed:   E_O = (1 + (D1 - D1^2) R C1 P) / (1 + (D2 - D2^2) R C2 P)
    drawn:     E_O = -(1 + (D1 - D1^2) R C1 P) / (1 + (D2 - D2^2) R C2 P) E_I

The adjustable lag's input network and the adjustable lead's feedback
network in one stage: a 10 kOhm pot from E_I to the summing point with its
wiper through C2 = 10 uF to ground (the pole), and a 10 kOhm pot from the
summing point to the output with its wiper through C1 = 10 uF to ground (the
zero). The input network passes a current E_I / (R (1 + (D2 - D2^2) R C2 P)),
and the feedback T turns it into a voltage -R (1 + (D1 - D1^2) R C1 P) times
it. At DC both capacitors are open and the stage is an inverter of gain -1.

The printed form drops the minus sign, and E_I with it. `settings` records
the two wiper positions the claims are held at: D1 = 1/2 (the zero at
40 rad/s) and D2 = 0.1 (the pole at 111 rad/s), which makes it a lead: the
gain climbs from 1 to (D1 - D1^2) C1 / ((D2 - D2^2) C2) = 2.78.
"""

import math
import sys
from decimal import Decimal
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Hz, Parameter, System, kOhm, require, uF
from fang.rationale import Chooses, Cites
from fang.simulation import ACSweep, OperatingPoint
from fang.parts import Capacitor

from handbook import (
    Bench,
    Claim,
    Ground,
    OpAmp,
    Potentiometer,
    Run,
    Terminal,
    corner,
    equals,
    minus,
    negative,
    over,
    product,
    ratio,
    within,
)


def spread(setting, resistance):
    """(D - D^2) R: what the wiper's capacitor sees."""
    return product(minus(setting, product(setting, setting)), resistance)


class LeadLag(System):
    """The lag's input network, the lead's feedback network, one op amp."""

    figure = Cites(
        "E_O = (1 + (D1 - D1^2) R C1 P) / (1 + (D2 - D2^2) R C2 P); "
        "composite lead and lag network",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 86, Lead-Lag",
    )

    settings = Chooses(
        "Where are the two wipers when the claims are held?",
        selected=(
            "D1 = 1/2 in the feedback (zero at 40 rad/s, 6.37 Hz) and D2 = 0.1 "
            "at the input (pole at 111 rad/s, 17.7 Hz): a lead of up to 28 degrees"
        ),
        alternatives=[
            {
                "option": "both at 1/2",
                "reason": "the zero and the pole cancel and the stage is a plain inverter: nothing to see",
            },
            {
                "option": "D1 = 0.1 and D2 = 1/2",
                "reason": "a lag instead of a lead; equally valid, and the lag has its own page",
            },
        ],
        rationale=(
            "the page gives no settings",
            "distinct zero and pole make the composite shape visible on the bench",
        ),
    )

    a_v = Parameter("1", default=-1 * ratio, description="E_O / E_I at DC, the sign the printed form drops")
    a_hf = Parameter("1", default=2.7778 * ratio, description="|E_O / E_I| well above both corners")
    f_zero = Parameter("Hz", default=6.3662 * Hz, description="the feedback network's zero, D1 = 1/2")
    f_pole = Parameter("Hz", default=17.684 * Hz, description="the input network's pole, D2 = 0.1")

    e_in = Terminal()
    e_out = Terminal()
    pot_in = Potentiometer(resistance=10 * kOhm, setting=Decimal("0.1") * ratio)
    c2 = Capacitor(capacitance=10 * uF)
    pot_fb = Potentiometer(resistance=10 * kOhm, setting=Decimal("0.5") * ratio)
    c1 = Capacitor(capacitance=10 * uF)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.pot_in.end_a
        self.pot_in.end_b >> self.amp.inverting.signal
        self.pot_in.wiper >> self.c2.p1
        self.amp.inverting.signal >> self.pot_fb.end_a
        self.pot_fb.end_b >> self.amp.output.signal
        self.pot_fb.wiper >> self.c1.p1
        self.c1.p2 >> self.ground.node
        self.c2.p2 >> self.ground.node
        self.amp.output.signal >> self.e_out.probe
        self.amp.non_inverting.signal >> self.ground.node

    def constraints(self):
        # At DC both pots are plain resistors, 10k over 10k.
        require(equals(self.a_v, negative(over(self.pot_fb.resistance, self.pot_in.resistance))))
        zero = spread(self.pot_fb.setting, self.pot_fb.resistance)
        pole = spread(self.pot_in.setting, self.pot_in.resistance)
        require(within(self.f_zero, corner(zero, self.c1.capacitance), 0.0001))
        require(within(self.f_pole, corner(pole, self.c2.capacitance), 0.0001))
        # Far above both, the ratio of the two time constants.
        require(
            within(
                self.a_hf,
                over(product(zero, self.c1.capacitance), product(pole, self.c2.capacitance)),
                0.0001,
            )
        )


# What the transfer function gives at the bench's two spot frequencies.
_T1, _T2 = 0.25 * 10e3 * 10e-6, 0.09 * 10e3 * 10e-6
_W100 = 2 * math.pi * 100
GAIN_100 = abs((1 + 1j * _T1 * _W100) / (1 + 1j * _T2 * _W100))
F_PEAK = 1 / (2 * math.pi * math.sqrt(_T1 * _T2))
_W = 2 * math.pi * F_PEAK
PHASE_PEAK = math.atan(_T1 * _W) - math.atan(_T2 * _W) - math.pi  # inverted, as vp reports it


BENCH = Bench(
    page=86,
    title="Lead-Lag",
    runs=[
        Run(
            "dc_gain",
            OperatingPoint(),
            drive={"e_in": "DC 1"},
            measure={"gain": "v({e_out.1}) / v({e_in.1})"},
            claims=[Claim("gain", "a_v", within=0.001, note="inverting: the printed form has no minus sign")],
        ),
        Run(
            "response",
            ACSweep(points=200, start="100m", stop="1k"),
            drive={"e_in": "DC 0 AC 1"},
            measure={
                "gain_low": "find vm({e_out.1}) at=100m",
                "gain_100": "find vm({e_out.1}) at=100",
                "phase_peak": f"find vp({{e_out.1}}) at={F_PEAK:.5g}",
            },
            claims=[
                Claim("gain_low", 1, within=0.001),
                Claim(
                    "gain_100",
                    GAIN_100,
                    within=0.002,
                    note=(
                        "the transfer function at 100 Hz, 2.741, on its way to the "
                        "2.778 (a_hf) it reaches only far above both corners"
                    ),
                ),
                Claim(
                    "phase_peak",
                    PHASE_PEAK,
                    within=0.002,
                    note=(
                        f"radians: at {F_PEAK:.4g} Hz, the geometric mean of the zero and "
                        "the pole, the lead peaks at 28.1 degrees over the inversion's -180"
                    ),
                ),
            ],
            note=(
                "D1 = 1/2, D2 = 0.1. The spot frequencies stay below a few hundred "
                "hertz: above that the wiper capacitor shorts most of the feedback "
                "and the op amp's loop gain, not the network, sets the gain."
            ),
        ),
    ],
)
