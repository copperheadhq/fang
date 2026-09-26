"""The simple meter amplifier, SBOA092B page 79.

    I_meter = E_I / (3 R_I) = E_I / 30 mA

E_I drives R_I into the summing point, and the feedback path from the output
back to it is a bridge: two diodes on the summing-point side, a 4.7 kOhm R_O
on each of the other two sides, and the meter in series with a third R_O
across the middle. Whichever way the input current flows, one diode carries
it, and the meter takes the share that goes round through the middle branch,
always in the same direction. That share is R_O / (3 R_O + R_M), a third when
the meter's own resistance is small, so the meter is a full-wave rectifier's
reading of the input.

The figure draws the diodes too small to read which way they point, and the
meter with no resistance, so `diodes` and `movement` record what was taken.
The bench drives a 100 Hz sine of 1 V peak and reads the meter's average
current against the average of |E_I|.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from decimal import Decimal

from fang.lang import Ohm, Parameter, System, UnitLiteral, kOhm, require
from fang.parts import Resistor
from fang.rationale import Chooses, Cites
from fang.simulation import Transient

from handbook import (
    Bench,
    Claim,
    Ground,
    Meter,
    OpAmp,
    Run,
    SignalDiode,
    Terminal,
    over,
    product,
    ratio,
    total,
    within,
)

#: A transconductance: the meter current per volt in.
uA_per_V = UnitLiteral("uA/V")


class SimpleMeterAmplifier(System):
    """E_I through R_I, and a diode bridge with the meter in it as the feedback."""

    figure = Cites(
        "I_meter = E_I / (3 R_I) = E_I / 30 mA. Linear current meter reads AC "
        "input voltage.",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 79, Simple Meter Amplifier",
    )

    diodes = Chooses(
        "Which way do the two diodes point?",
        selected=(
            "the upper one from the top corner into the summing point, the "
            "lower one from the summing point into the bottom corner"
        ),
        alternatives=[
            {
                "reading": "both pointing away from the summing point, or both toward it",
                "reason": "then one polarity of input current has no path back to "
                "the output and the loop opens for half of every cycle",
            },
            {
                "reading": "the mirror image: upper away from the summing point, lower into it",
                "reason": "that works too and reverses the meter current; the "
                "reading taken makes it flow bottom to top, the way the meter's "
                "arrow points",
            },
        ],
        rationale=(
            "the diode symbols are too small in the figure to read their "
            "direction, so the only readings are the ones that close the loop "
            "for both polarities",
        ),
    )

    movement = Chooses(
        "What is the meter's resistance?",
        selected="100 Ohm",
        alternatives=[
            {
                "option": "a zero-ohm meter",
                "reason": "no movement has none, and the formula's third is the "
                "limit a real one approaches",
            },
            {
                "option": "a 2 kOhm, 50 uA movement",
                "reason": "the meter takes R_O / (3 R_O + R_M) of the current, "
                "which at 2 kOhm is 0.29 rather than a third, 12% low",
            },
        ],
        rationale=(
            "the meter's share is R_O / (3 R_O + R_M); 100 Ohm against 14.1 kOhm "
            "keeps it within 1% of the handbook's third",
        ),
    )

    g_meter = Parameter(
        "uA/V",
        default=Decimal("33.098") * uA_per_V,
        description="average meter current over average |E_I|: R_O / ((3 R_O + R_M) R_I)",
    )
    g_handbook = Parameter(
        "uA/V",
        default=Decimal("33.333") * uA_per_V,
        description="the handbook's 1 / (3 R_I)",
    )

    e_in = Terminal()
    r_in = Resistor(resistance=10 * kOhm)
    amp = OpAmp()
    ground = Ground()

    d_top = SignalDiode()
    d_bottom = SignalDiode()
    r_top = Resistor(resistance=4.7 * kOhm)
    r_bottom = Resistor(resistance=4.7 * kOhm)
    r_middle = Resistor(resistance=4.7 * kOhm)
    meter = Meter(resistance=100 * Ohm)

    def architecture(self):
        self.e_in.probe >> self.r_in.p1
        self.amp.non_inverting.signal >> self.ground.node

        # The summing point is the bridge's left corner.
        self.r_in.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.d_top.p2
        self.d_top.p2 >> self.d_bottom.p1

        # The top corner: the upper diode, the upper R_O, and the meter.
        self.d_top.p1 >> self.r_top.p1
        self.r_top.p1 >> self.meter.p2

        # The bottom corner: the lower diode, the lower R_O, and the middle R_O.
        self.d_bottom.p2 >> self.r_bottom.p1
        self.r_bottom.p1 >> self.r_middle.p1
        self.r_middle.p2 >> self.meter.p1

        # The right corner is the output.
        self.r_top.p2 >> self.r_bottom.p2
        self.r_bottom.p2 >> self.amp.output.signal

    def constraints(self):
        r_o = self.r_top.resistance
        require(
            within(
                self.g_meter,
                over(
                    r_o,
                    product(
                        total(r_o, self.r_bottom.resistance, self.r_middle.resistance,
                              self.meter.resistance),
                        self.r_in.resistance,
                    ),
                ),
                0.0001,
            )
        )
        require(
            within(self.g_handbook, over(1 * ratio, product(3 * ratio, self.r_in.resistance)), 0.0001)
        )
        # The meter's resistance is small enough that the handbook's third holds.
        require(within(self.g_meter, self.g_handbook, 0.01))


BENCH = Bench(
    page=79,
    title="Simple Meter Amplifier",
    runs=[
        Run(
            "sine",
            Transient(stop="60m", step="10u"),
            drive={"e_in": "SIN(0 1 100)"},
            measure={
                "i_avg": "avg i(vm1_sense) from=20m to=60m",
                "e_peak": "max v({e_in.1}) from=20m to=60m",
                "g_meter": "i_avg / (e_peak * 0.6366197723675814)",
                "g_handbook": "i_avg / (e_peak * 0.6366197723675814)",
            },
            claims=[
                Claim("g_meter", "g_meter", within=0.005, unit="A/V"),
                Claim(
                    "g_handbook", "g_handbook", within=0.01, unit="A/V",
                    note="the handbook's E_I / 30 mA, which the 100 Ohm meter "
                    "takes 0.7% less than",
                ),
            ],
            units={"i_avg": "A", "e_peak": "V"},
            note="A 100 Hz sine of 1 V peak, four whole periods averaged. The "
            "average of |E_I| is 2/pi of its peak, so the ratio is the meter's "
            "average current over the input's rectified average. The 0.5% "
            "allowance covers the diode's turn-on at each zero crossing, which "
            "the loop closes over but not instantly.",
        ),
    ],
)
