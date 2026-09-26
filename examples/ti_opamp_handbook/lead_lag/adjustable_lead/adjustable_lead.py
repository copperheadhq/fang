"""The adjustable lead, SBOA092B page 85.

    printed:   E_O = -[(D - D^2) R C P] E_I
    drawn:     E_O = -[1 + (D - D^2) R C P] E_I

The adjustable lag's input network moved into the feedback path: R = 10 kOhm
in, and a 10 kOhm potentiometer from the summing point to the output with its
wiper through C = 10 uF to ground. Solving the wiper node, the feedback is a
T whose transfer impedance is R [1 + (D - D^2) R C P], so the stage is a
zero at 1/((D - D^2) R C) on top of a DC gain of -1.

The printed form drops the 1. Without it the circuit would be a pure
differentiator with no DC gain at all, and the drawing plainly passes DC: C
is open there and the whole pot is in the loop, 10 kOhm against 10 kOhm.
`setting` records that the claims are held at D = 1/2, where the lead is
largest, the zero at 40 rad/s.
"""

import sys
from decimal import Decimal
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Hz, Parameter, System, kOhm, require, uF
from fang.parts import Capacitor, Resistor
from fang.rationale import Chooses, Cites
from fang.simulation import ACSweep, OperatingPoint

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


class AdjustableLead(System):
    """E_I through R into the summing point, the pot back from the output with its wiper to ground through C."""

    figure = Cites(
        "E_O = -[(D - D^2) R C P] E_I; putting input network from adjustable "
        "lag circuit in feedback path gives lead element",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 85, Adjustable Lead",
    )

    setting = Chooses(
        "Where is the wiper when the claims are held?",
        selected="D = 1/2, where D - D^2 is largest: a zero at 40 rad/s, 6.37 Hz",
        alternatives=[
            {
                "option": "D = 0.1",
                "reason": "less lead, the zero at 111 rad/s; the page's companion lag is quoted at D = 1/2",
            },
        ],
        rationale=(
            "the page gives no setting for the lead; the lag beside it is quoted at D = 1/2",
            "at the center the zero sits lowest, so the lead is widest",
        ),
    )

    a_v = Parameter("1", default=-1 * ratio, description="E_O / E_I at DC, the 1 the printed form drops")
    f_z = Parameter("Hz", default=6.3662 * Hz, description="the zero at D = 1/2")

    e_in = Terminal()
    e_out = Terminal()
    r_in = Resistor(resistance=10 * kOhm)
    pot = Potentiometer(resistance=10 * kOhm, setting=Decimal("0.5") * ratio)
    c = Capacitor(capacitance=10 * uF)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.r_in.p1
        self.r_in.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.pot.end_a
        self.pot.end_b >> self.amp.output.signal
        self.pot.wiper >> self.c.p1
        self.c.p2 >> self.ground.node
        self.amp.output.signal >> self.e_out.probe
        self.amp.non_inverting.signal >> self.ground.node

    def constraints(self):
        # At DC C is open and the whole pot is the feedback resistor.
        require(equals(self.a_v, negative(over(self.pot.resistance, self.r_in.resistance))))
        # The zero: (D - D^2) R C.
        lead = product(minus(self.pot.setting, product(self.pot.setting, self.pot.setting)), self.pot.resistance)
        require(within(self.f_z, corner(lead, self.c.capacitance), 0.0001))


BENCH = Bench(
    page=85,
    title="Adjustable Lead",
    runs=[
        Run(
            "dc_gain",
            OperatingPoint(),
            drive={"e_in": "DC 1"},
            measure={"gain": "v({e_out.1}) / v({e_in.1})"},
            claims=[
                Claim(
                    "gain",
                    "a_v",
                    within=0.001,
                    note="the printed -[(D - D^2) R C P] E_I would give 0 here; the drawn circuit gives -1",
                )
            ],
        ),
        Run(
            "lead",
            ACSweep(points=200, start="100m", stop="1k"),
            drive={"e_in": "DC 0 AC 1"},
            measure={
                "f_3db": "when vdb({e_out.1})=3.0103 rise=1",
                "gain_z": "find vm({e_out.1}) at=6.3662",
                "phase_z": "find vp({e_out.1}) at=6.3662",
                "gain_10z": "find vm({e_out.1}) at=63.662",
            },
            claims=[
                Claim("f_3db", "f_z", within=0.005, unit="Hz", note="where the gain has risen 3 dB above unity"),
                Claim("gain_z", 1.41421, within=0.005, note="|1 + j| at the zero; without the 1 it would be 1"),
                Claim(
                    "phase_z",
                    -2.35619,
                    within=0.005,
                    note="radians: -135 degrees, the inversion less the zero's 45",
                ),
                Claim(
                    "gain_10z",
                    10.0499,
                    within=0.005,
                    note="|1 + 10 j| a decade above the zero; the op amp's 10 MHz is far off",
                ),
            ],
            note="D = 1/2. The rise flattens only where the op amp runs out of loop gain, far above this sweep.",
        ),
    ],
)
