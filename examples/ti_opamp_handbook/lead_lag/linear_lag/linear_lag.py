"""Lag value linear with R setting, SBOA092B page 85.

    E_O = E_I / (1 + D R C P) = 10 E_I / (10 + P)

A voltage follower whose + input sits on an RC low-pass: E_I through a
10 kOhm potentiometer wired as a rheostat, and C = 10 uF to ground. The wiper
is tied to the end at E_I, so the resistance in the path is D R, and the time
constant is D R C, a straight line in the setting. The page's 10/(10 + P) is
D = 1: R C = 0.1 s, a corner at 10 rad/s.

The program had to decide which end of the pot the setting counts from
(`rheostat`), and holds the claims at full travel, where the page's numbers
are. The bench moves the wiper to 1/2 and 1/4 to show the time constant
scale with it. The follower passes DC at unity whatever the setting.
"""

import sys
from decimal import Decimal
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Hz, Parameter, System, kOhm, require, uF
from fang.parts import Capacitor
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
    product,
    ratio,
    within,
)


class LinearLag(System):
    """E_I through a rheostat onto the + input, C to ground there, the output back to the - input."""

    figure = Cites(
        "E_O = E_I / (1 + D R C P) = 10 E_I / (10 + P); non-inverting low distortion",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 85, Lag value linear with R setting",
    )

    rheostat = Chooses(
        "Which end of the pot does the setting count from, and where are the claims held?",
        selected=(
            "end 1 on the + input, wiper and end 3 on E_I, so the path is "
            "setting x 10 kOhm; the claims are held at full travel, the page's 10/(10 + P)"
        ),
        alternatives=[
            {
                "option": "count the setting from the E_I end",
                "reason": "the lag would still be linear but would shrink as D rises, the reverse of D R C",
            },
        ],
        rationale=(
            "the figure ties the wiper to the end at E_I, a rheostat",
            "10/(10 + P) is R C = 0.1 s, all of the pot in the path",
        ),
    )

    a_v = Parameter("1", default=1 * ratio, description="E_O / E_I at DC")
    f_c = Parameter("Hz", default=Decimal("1.59155") * Hz, description="the corner at full travel, 1/(2 pi R C)")
    f_half = Parameter("Hz", default=3.1831 * Hz, description="the corner at D = 1/2")
    f_quarter = Parameter("Hz", default=6.3662 * Hz, description="the corner at D = 1/4")

    e_in = Terminal()
    e_out = Terminal()
    pot = Potentiometer(resistance=10 * kOhm, setting=Decimal("1") * ratio)
    c = Capacitor(capacitance=10 * uF)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.pot.end_b
        self.pot.wiper >> self.pot.end_b
        self.pot.end_a >> self.amp.non_inverting.signal
        self.amp.non_inverting.signal >> self.c.p1
        self.c.p2 >> self.ground.node
        self.amp.inverting.signal >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe

    def constraints(self):
        # A follower: the + input's voltage is the output's, at DC all of E_I.
        require(equals(self.a_v, 1 * ratio))
        # The lag: D R into C.
        path = product(self.pot.setting, self.pot.resistance)
        require(within(self.f_c, corner(path, self.c.capacitance), 0.0001))
        # Linear in D: half the path, twice the corner.
        half = product(Decimal("0.5") * ratio, self.pot.resistance)
        quarter = product(Decimal("0.25") * ratio, self.pot.resistance)
        require(within(self.f_half, corner(half, self.c.capacitance), 0.0001))
        require(within(self.f_quarter, corner(quarter, self.c.capacitance), 0.0001))


def _sweep(name, setting, corner_claim, note):
    return Run(
        name,
        ACSweep(points=200, start="10m", stop="1k"),
        drive={"e_in": "DC 0 AC 1"},
        settings={"pot": {"setting": setting}},
        measure={"f_3db": "when vdb({e_out.1})=-3.0103 fall=1"},
        claims=[Claim("f_3db", corner_claim, within=0.005, unit="Hz")],
        note=note,
    )


BENCH = Bench(
    page=85,
    title="Lag value linear with R setting",
    runs=[
        Run(
            "dc_gain",
            OperatingPoint(),
            drive={"e_in": "DC 1"},
            measure={"gain": "v({e_out.1}) / v({e_in.1})"},
            claims=[Claim("gain", "a_v", within=0.001)],
        ),
        _sweep("full_travel", 1, "f_c", "D = 1: the page's 10/(10 + P), a corner at 10 rad/s."),
        _sweep("half_travel", 0.5, "f_half", "D = 1/2: half the resistance, twice the corner."),
        _sweep("quarter_travel", 0.25, "f_quarter", "D = 1/4: a quarter of it, four times the corner."),
    ],
)
