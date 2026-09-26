"""The inverting buffer with adjustable gain, SBOA092B page 50.

    E_O / E_I = -(R_O + (1 - s) R_2) / (R_I + s R_2)

An inverter of gain -1, with a 100 Ohm potentiometer between R_I and R_O and
its wiper on the - input. Where the wiper sits decides how much of the pot is
on the input side and how much on the feedback side, so the gain can be
trimmed a little either way of -1, which is what the text says it is for:
making up for the tolerance of two 10 kOhm resistors.

The handbook prints no formula. The one above is the drawing's, with s the
wiper's position from the R_I end. At the centre both sides are 10.05 kOhm
and the gain is exactly -1; at the ends it is -10100/10000 = -1.01 and
-10000/10100 = -0.990, a trim of about +/-1%. The figure leaves the wiper's
position open, so `trim` records the centre as the setting the program
claims, and the bench turns the pot to each end.
"""

import sys
from decimal import Decimal
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Ohm, Parameter, System, kOhm, require
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
    minus,
    negative,
    over,
    product,
    ratio,
    total,
    within,
)


def gain(r_in, r_out, pot, setting):
    """-(R_O + (1 - s) R_2) / (R_I + s R_2), for a wiper at s from the R_I end."""
    return negative(
        over(
            total(r_out, product(minus(1 * ratio, setting), pot)),
            total(r_in, product(setting, pot)),
        )
    )


class InvertingBufferAdjustableGain(System):
    """R_I, the pot, R_O in a row from E_I to E_O; the wiper on the - input."""

    figure = Cites(
        "Potentiometer in feedback allows gain trimming to compensate for "
        "tolerance in resistor values.",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 50, Inverting Buffer Adjustable Gain",
    )

    trim = Chooses(
        "Where is the wiper?",
        selected="at the centre of its travel, where the gain is exactly -1",
        alternatives=[
            {
                "option": "at either end",
                "reason": (
                    "the ends are the trim's limits, not a setting anyone "
                    "would leave it at; the bench runs both to show the range"
                ),
            },
        ],
        rationale=(
            "the figure draws the wiper and gives no setting",
            "with matched 10 kOhm resistors the centre is where the trim lands",
        ),
    )

    a_v = Parameter("1", default=-1 * ratio, description="E_O / E_I at the pot's setting")
    a_v_input_end = Parameter(
        "1", default=Decimal("-1.01") * ratio, description="the wiper at the R_I end"
    )
    a_v_output_end = Parameter(
        "1", default=Decimal("-0.990099") * ratio, description="the wiper at the R_O end"
    )

    e_in = Terminal()
    e_out = Terminal()
    e_in_return = Terminal()
    e_out_return = Terminal()
    r_in = Resistor(resistance=10 * kOhm)
    pot = Potentiometer(resistance=100 * Ohm, setting=Decimal("0.5") * ratio)
    r_out = Resistor(resistance=10 * kOhm)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.r_in.p1
        self.r_in.p2 >> self.pot.end_a
        self.pot.wiper >> self.amp.inverting.signal
        self.pot.end_b >> self.r_out.p1
        self.r_out.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe
        self.amp.non_inverting.signal >> self.ground.node
        self.e_in_return.probe >> self.ground.node
        self.e_out_return.probe >> self.ground.node

    def constraints(self):
        r_in, r_out, pot = self.r_in.resistance, self.r_out.resistance, self.pot.resistance
        require(equals(self.a_v, gain(r_in, r_out, pot, self.pot.setting)))
        require(equals(self.a_v_input_end, gain(r_in, r_out, pot, 0 * ratio)))
        # -10000/10100 does not end; six figures of it. `within` takes its
        # band as a fraction of the target, so it is written on the magnitudes.
        require(
            within(
                negative(self.a_v_output_end),
                negative(gain(r_in, r_out, pot, 1 * ratio)),
                1e-6,
            )
        )


BENCH = Bench(
    page=50,
    title="Inverting Buffer Adjustable Gain",
    runs=[
        Run(
            "centre",
            OperatingPoint(),
            drive={"e_in": "DC 1"},
            measure={"gain": "v({e_out.1}) / v({e_in.1})"},
            claims=[Claim("gain", "a_v", within=0.0001)],
        ),
        Run(
            "wiper_at_input_end",
            OperatingPoint(),
            drive={"e_in": "DC 1"},
            settings={"pot": {"setting": 0}},
            measure={"gain": "v({e_out.1}) / v({e_in.1})"},
            claims=[Claim("gain", "a_v_input_end", within=0.0001)],
            note="All 100 Ohm on the feedback side: the most gain the trim gives.",
        ),
        Run(
            "wiper_at_output_end",
            OperatingPoint(),
            drive={"e_in": "DC 1"},
            settings={"pot": {"setting": 1}},
            measure={"gain": "v({e_out.1}) / v({e_in.1})"},
            claims=[Claim("gain", "a_v_output_end", within=0.0001)],
            note="All 100 Ohm on the input side: the least.",
        ),
    ],
)
