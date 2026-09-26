"""The adjustable lag, SBOA092B page 84.

    E_O = -E_I / (1 + (D - D^2) R C P) = -40 E_I / (40 + P)

A 10 kOhm potentiometer runs from E_I to the summing point, and its wiper
goes through C = 10 uF to ground; R_O = 10 kOhm closes the loop. At DC the
capacitor is open, the pot is a plain 10 kOhm in series, and the gain is
-R_O/R = -1 whatever the setting. At frequency the wiper is shunted to ground,
and solving the wiper node gives one pole with time constant (D - D^2) R C,
where D is the setting counted from either end (the product is symmetric).
It is largest at D = 1/2, R C / 4 = 25 ms, the -40/(40 + P) the page prints.

The figure leaves the setting to the reader. `setting` records that the
claims are held at the page's own D = 1/2, and the bench moves the wiper to
D = 0.1 to show the corner move while the DC gain stays put.
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


def lag(setting, resistance):
    """(D - D^2) R: the resistance the capacitor sees, as it sets the pole."""
    return product(minus(setting, product(setting, setting)), resistance)


class AdjustableLag(System):
    """E_I through the pot into the summing point, the wiper to ground through C, R_O across."""

    figure = Cites(
        "E_O = -E_I / (1 + (D - D^2) R C P) = -40 E_I / (40 + P); non-integrating "
        "type, constant inverting unity gain, maximum lag for R centered for D = 1/2",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 84, Adjustable Lag",
    )

    setting = Chooses(
        "Where is the wiper when the claims are held?",
        selected="D = 1/2, the page's own setting, where the lag is largest: 40 rad/s, 6.37 Hz",
        alternatives=[
            {
                "option": "D = 0.1",
                "reason": "checked on the bench as a second point; the page prints its numbers at D = 1/2",
            },
            {
                "option": "D at either end",
                "reason": "D - D^2 is 0 there and the lag vanishes: the circuit is a plain inverter",
            },
        ],
        rationale=(
            "the page prints -40/(40 + P), which is R C / 4 = 25 ms",
            "D - D^2 is symmetric, so which end D counts from does not matter",
        ),
    )

    a_v = Parameter("1", default=-1 * ratio, description="E_O / E_I at DC, any setting")
    f_c = Parameter("Hz", default=6.3662 * Hz, description="the corner at D = 1/2")
    d_other = Parameter("1", default=Decimal("0.1") * ratio, description="the second setting the bench checks")
    f_other = Parameter("Hz", default=17.684 * Hz, description="the corner at D = 0.1")

    e_in = Terminal()
    e_out = Terminal()
    pot = Potentiometer(resistance=10 * kOhm, setting=Decimal("0.5") * ratio)
    c = Capacitor(capacitance=10 * uF)
    r_out = Resistor(resistance=10 * kOhm)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.pot.end_a
        self.pot.end_b >> self.amp.inverting.signal
        self.pot.wiper >> self.c.p1
        self.c.p2 >> self.ground.node
        self.amp.inverting.signal >> self.r_out.p1
        self.r_out.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe
        self.amp.non_inverting.signal >> self.ground.node

    def constraints(self):
        # At DC C is open: the whole pot is in series with E_I.
        require(equals(self.a_v, negative(over(self.r_out.resistance, self.pot.resistance))))
        # The pole, at the drawn setting and at the second one.
        require(within(self.f_c, corner(lag(self.pot.setting, self.pot.resistance), self.c.capacitance), 0.0001))
        require(within(self.f_other, corner(lag(self.d_other, self.pot.resistance), self.c.capacitance), 0.0001))


def _sweep(name, setting, corner_claim, corner_hz, note):
    return Run(
        name,
        ACSweep(points=200, start="100m", stop="1k"),
        drive={"e_in": "DC 0 AC 1"},
        settings={"pot": {"setting": setting}},
        measure={
            "gain_low": "find vm({e_out.1}) at=100m",
            "f_3db": "when vdb({e_out.1})=-3.0103 fall=1",
            "phase_c": f"find vp({{e_out.1}}) at={corner_hz}",
        },
        claims=[
            Claim("gain_low", 1, within=0.001, note="unity, the DC gain's magnitude, well below the corner"),
            Claim("f_3db", corner_claim, within=0.005, unit="Hz"),
            Claim(
                "phase_c",
                2.35619,
                within=0.005,
                note="radians: 135 degrees at the corner, the inversion's 180 less the pole's 45",
            ),
        ],
        units={"f_3db": "Hz"},
        note=note,
    )


BENCH = Bench(
    page=84,
    title="Adjustable Lag",
    runs=[
        Run(
            "dc_gain",
            OperatingPoint(),
            drive={"e_in": "DC 1"},
            measure={"gain": "v({e_out.1}) / v({e_in.1})"},
            claims=[Claim("gain", "a_v", within=0.001)],
        ),
        Run(
            "dc_gain_other",
            OperatingPoint(),
            drive={"e_in": "DC 1"},
            settings={"pot": {"setting": 0.1}},
            measure={"gain": "v({e_out.1}) / v({e_in.1})"},
            claims=[Claim("gain", "a_v", within=0.001, note="the wiper moved, and the DC gain did not")],
        ),
        _sweep(
            "lag_centered",
            0.5,
            "f_c",
            6.3662,
            "D = 1/2: the page's -40/(40 + P), a corner at 40 rad/s.",
        ),
        _sweep(
            "lag_other",
            0.1,
            "f_other",
            17.684,
            "D = 0.1: (D - D^2) R C = 9 ms, a corner at 111 rad/s. Less lag than at the center.",
        ),
    ],
)
