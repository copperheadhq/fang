"""Linear gain control, SBOA092B page 71.

    E_O = 0 to -10 E_I
    Z_in = R_I = 10 kOhm

An inverting amplifier whose feedback resistor is a 100 kOhm potentiometer
wired as a rheostat: the wiper is tied to the end at the output, so the
resistance in the loop is the setting times 100 kOhm and the gain is
-10 times the setting, a straight line from 0 to -10. The input resistor is
fixed, so Z_in stays 10 kOhm whatever the setting.

The figure draws the wiper joined to the right-hand end, which is the output.
The program had to decide which end of the travel the setting counts from
(`rheostat`) and which setting the claims are held at (full travel, the
printed -10). The bench then moves the wiper to show the line is straight.
"""

import sys
from decimal import Decimal
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Parameter, System, kOhm, require
from fang.parts import Resistor
from fang.rationale import Chooses, Cites
from fang.simulation import OperatingPoint

from handbook import (
    Bench,
    Claim,
    Ground,
    OpAmp,
    Potentiometer,
    Run,
    Terminal,
    equals,
    negative,
    over,
    product,
    ratio,
)


class LinearGainControl(System):
    """E_I through R_I into the summing point, a rheostat back from the output."""

    figure = Cites(
        "E_O = 0 to -10 E_I, Z_in = R_I = 10 kOhm; variable from 0 to 10",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 71, Linear Gain Control",
    )

    rheostat = Chooses(
        "Which end of the 100 kOhm pot is in the loop, and at what setting are the claims held?",
        selected=(
            "end 1 on the summing point, wiper and end 3 on the output, so the "
            "loop sees setting x 100 kOhm; claims held at full travel, -10"
        ),
        alternatives=[
            {
                "option": "count the setting from the output end",
                "reason": (
                    "the gain would still be linear but would fall as the "
                    "setting rises; counting from the summing point makes the "
                    "setting and the gain magnitude move together"
                ),
            },
            {
                "option": "hold the claims at mid travel",
                "reason": "the printed figure is the end of the range, -10; mid travel is checked on the bench",
            },
        ],
        rationale=(
            "the figure ties the wiper to the end at the output, a rheostat",
            "the page prints the range, 0 to -10, and full travel is its end",
        ),
    )

    a_v = Parameter("1", default=-10 * ratio, description="E_O / E_I at full travel")
    z_in = Parameter("Ohm", default=10 * kOhm, description="what E_I sees")

    e_in = Terminal()
    e_out = Terminal()
    r_in = Resistor(resistance=10 * kOhm)
    r_out = Potentiometer(resistance=100 * kOhm, setting=Decimal("1") * ratio)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.r_in.p1
        self.r_in.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r_out.end_a
        self.r_out.wiper >> self.amp.output.signal
        self.r_out.end_b >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe
        self.amp.non_inverting.signal >> self.ground.node

    def constraints(self):
        # The rheostat puts setting x R_O in the loop, so the gain is linear in it.
        require(
            equals(
                self.a_v,
                negative(
                    over(
                        product(self.r_out.setting, self.r_out.resistance),
                        self.r_in.resistance,
                    )
                ),
            )
        )
        # The summing point is a virtual ground, so E_I sees R_I alone.
        require(equals(self.z_in, self.r_in.resistance))


def _setting(value: float, gain: float) -> Run:
    return Run(
        f"setting_{int(value * 100):03d}",
        OperatingPoint(),
        drive={"e_in": "DC 1"},
        settings={"r_out": {"setting": value}},
        measure={"gain": "v({e_out.1}) / v({e_in.1})"},
        claims=[
            Claim(
                "gain",
                gain,
                within=0.001,
                note=f"-10 x {value}: the rheostat puts {value * 100:g} kOhm in the loop",
            )
        ],
    )


BENCH = Bench(
    page=71,
    title="Linear Gain Control",
    runs=[
        Run(
            "full_travel",
            OperatingPoint(),
            drive={"e_in": "DC 1"},
            measure={
                "gain": "v({e_out.1}) / v({e_in.1})",
                "z_in": "-v({e_in.1}) / i(vdrive_e_in)",
            },
            claims=[
                Claim("gain", "a_v", within=0.001),
                Claim("z_in", "z_in", within=0.001, unit="Ohm"),
            ],
        ),
        _setting(0.75, -7.5),
        _setting(0.5, -5.0),
        _setting(0.25, -2.5),
        Run(
            "setting_000",
            OperatingPoint(),
            drive={"e_in": "DC 1"},
            settings={"r_out": {"setting": 0}},
            measure={
                "e_out": "v({e_out.1})",
                "z_in": "-v({e_in.1}) / i(vdrive_e_in)",
            },
            claims=[
                Claim(
                    "e_out",
                    0,
                    within=1e-6,
                    absolute=True,
                    unit="V",
                    note="the bottom of the range: only the pot's 1 mOhm contact is in the loop",
                ),
                Claim("z_in", "z_in", within=0.001, unit="Ohm"),
            ],
            note="Z_in does not move with the setting, unlike the simple gain control just before it in the handbook.",
        ),
    ],
)
