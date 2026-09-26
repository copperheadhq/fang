"""Gain control, SBOA092B page 73.

    E_O / E_I = 1 / k,   k = the fraction of the pot below the wiper

A non-inverting amplifier whose two resistors are the two halves of one
10 kOhm potentiometer: it runs from the output to ground, and the wiper feeds
the - input. The wiper sits at k E_O, the loop holds it at E_I, so the gain
is 1/k, from 1 with the wiper at the output towards infinity as it nears
ground. The page prints no formula; it says the circuit is equivalent to
replacing both resistors of the non-inverting amplifier, and the formula here
is that one with R_O = (1 - k) R and R_I = k R.

The program had to decide which end the pot's setting counts from and where
the claim is held (`setting`). The bench moves the wiper through four
settings, and keeps E_I small enough at the top one that the output stays
inside its swing.
"""

import sys
from decimal import Decimal
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Parameter, System, kOhm, require
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
    over,
    ratio,
)


class GainControl(System):
    """E_I on the + input, the pot from output to ground, its wiper on the - input."""

    figure = Cites(
        "Equivalent to replacing both resistors in the non-inverting amplifier. "
        "Observe common mode voltage limit.",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 73, Gain Control",
    )

    setting = Chooses(
        "Which end does the pot's setting count from, and where is the claim held?",
        selected=(
            "end 1 on ground and end 3 on the output, so the setting is k, the "
            "fraction below the wiper; the claim is held at k = 0.1, a gain of 10"
        ),
        alternatives=[
            {
                "option": "end 1 on the output",
                "reason": "the setting would be 1 - k, and the gain 1 / (1 - setting) reads less directly",
            },
            {
                "option": "hold the claim at mid travel, a gain of 2",
                "reason": "the page's other amplifiers are shown at a gain of 10; mid travel is checked on the bench",
            },
        ],
        rationale=(
            "the figure gives the pot's value and no setting",
            "counting from ground makes the setting the feedback fraction itself",
        ),
    )

    a_v = Parameter("1", default=10 * ratio, description="E_O / E_I at the chosen setting")

    e_in = Terminal()
    e_out = Terminal()
    pot = Potentiometer(resistance=10 * kOhm, setting=Decimal("0.1") * ratio)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.amp.non_inverting.signal
        self.amp.output.signal >> self.pot.end_b
        self.pot.wiper >> self.amp.inverting.signal
        self.pot.end_a >> self.ground.node
        self.amp.output.signal >> self.e_out.probe

    def constraints(self):
        # The wiper divides E_O by k and the loop holds it at E_I.
        require(equals(self.a_v, over(1 * ratio, self.pot.setting)))


def _setting(k: float, drive: float) -> Run:
    return Run(
        f"k_{int(k * 100):03d}",
        OperatingPoint(),
        drive={"e_in": f"DC {drive:g}"},
        settings={"pot": {"setting": k}},
        measure={"gain": "v({e_out.1}) / v({e_in.1})"},
        claims=[Claim("gain", 1 / k, within=0.001, note=f"1 / k = 1 / {k:g}")],
    )


BENCH = Bench(
    page=73,
    title="Gain Control",
    runs=[
        Run(
            "chosen",
            OperatingPoint(),
            drive={"e_in": "DC 1"},
            measure={"gain": "v({e_out.1}) / v({e_in.1})", "e_out": "v({e_out.1})"},
            claims=[Claim("gain", "a_v", within=0.001)],
            units={"e_out": "V"},
        ),
        _setting(1.0, 1.0),
        _setting(0.5, 1.0),
        _setting(0.25, 1.0),
        Run(
            "k_002",
            OperatingPoint(),
            drive={"e_in": "DC 0.2"},
            settings={"pot": {"setting": 0.02}},
            measure={"gain": "v({e_out.1}) / v({e_in.1})"},
            claims=[
                Claim(
                    "gain",
                    50,
                    within=0.001,
                    note="1 / 0.02; E_I is 0.2 V here so that E_O, 10 V, stays inside the swing",
                )
            ],
        ),
    ],
)
