"""The differential integrator, SBOA092B page 59 (top).

    E_O = -1/(R_I C_O) integral (E1 - E2) dt = 10 integral (E2 - E1) dt

E1 goes through R_I (100 kOhm) to the inverting input, with C_O (1 uF) from
there to the output. E2 goes through a second R_I to the non-inverting input,
with a second C_O from there to ground. The E2 side is an RC low-pass whose
capacitor voltage is (1/(R_I C_O)) integral E2 dt; the E1 side integrates
about that voltage, so the output is 10 integral (E2 - E1) dt.

The handbook's first line reads "(E_I - E_2)", a subscript slip for E_1; its
second line has the sign the figure gives. The figure draws no reset, so the
bench starts all three capacitor nodes at zero with `.ic`. The figure names a
TLC265x, a chopper-stabilized part; the default op amp, with no offset, stands
in for it.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Parameter, System, UnitLiteral, kOhm, require, uF
from fang.parts import Capacitor, Resistor
from fang.rationale import Chooses, Cites
from fang.simulation import Transient

from handbook import (
    Bench,
    Claim,
    Ground,
    OpAmp,
    Run,
    Terminal,
    equals,
    over,
    product,
    ratio,
)

#: A rate: volts of output per second, for each volt of input.
per_second = UnitLiteral("1/s")

#: Both capacitors and the output start at zero; the figure has no reset.
START = ".ic v({amp.OUT})=0 v({amp.IN-})=0 v({amp.IN+})=0"


class DifferentialIntegrator(System):
    """E1 into an integrator's summing point, E2 into an RC on the non-inverting input."""

    figure = Cites(
        "E_O = -1/(R_I C_O) integral (E_I - E_2) dt = 10 integral (E_2 - E_1) dt. "
        "Integrates difference between two signals.",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 59, Differential Integrator",
    )

    start = Chooses(
        "Where does the output start, with no reset drawn?",
        selected="at zero: `.ic` on the output and both op amp inputs",
        alternatives=[
            {
                "option": "add a reset switch",
                "reason": "the figure has none, and a reset for the E2 side would need a second one",
            },
        ],
        rationale=("the starting charge on both capacitors is part of the answer, so it is stated",),
    )

    rate = Parameter(
        "1/s",
        default=10 * per_second,
        description="dE_O/dt for each volt of E2 - E1: 1/(R_I C_O)",
    )

    e1 = Terminal()
    e2 = Terminal()
    e_out = Terminal()
    r_minus = Resistor(resistance=100 * kOhm)
    c_feedback = Capacitor(capacitance=1 * uF)
    r_plus = Resistor(resistance=100 * kOhm)
    c_ground = Capacitor(capacitance=1 * uF)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e1.probe >> self.r_minus.p1
        self.r_minus.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.c_feedback.p1
        self.c_feedback.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe

        self.e2.probe >> self.r_plus.p1
        self.r_plus.p2 >> self.amp.non_inverting.signal
        self.amp.non_inverting.signal >> self.c_ground.p1
        self.c_ground.p2 >> self.ground.node

    def constraints(self):
        # The two sides are matched: each has the same time constant.
        require(
            equals(
                self.rate,
                over(1 * ratio, product(self.r_minus.resistance, self.c_feedback.capacitance)),
            )
        )
        require(
            equals(
                self.rate,
                over(1 * ratio, product(self.r_plus.resistance, self.c_ground.capacitance)),
            )
        )


BENCH = Bench(
    page=59,
    title="Differential Integrator",
    runs=[
        Run(
            "difference",
            Transient(stop="1", step="1m"),
            drive={"e1": "DC 0.1", "e2": "DC 0.3"},
            cards=[START],
            measure={
                "e_early": "find v({e_out.1}) at=0.1",
                "e_late": "find v({e_out.1}) at=1",
                "rate_per_volt": "(e_late - e_early) / 0.9 / 0.2",
            },
            claims=[Claim("rate_per_volt", "rate", within=0.001, unit="/s")],
            units={"e_early": "V", "e_late": "V"},
            note=(
                "E2 - E1 = 0.2 V, so the output rises 2 V/s. The slope over "
                "0.1 s to 1 s, divided by 0.2 V, is the rate."
            ),
        ),
        Run(
            "common_mode",
            Transient(stop="1", step="1m"),
            drive={"e1": "DC 0.5", "e2": "DC 0.5"},
            cards=[START],
            measure={
                "e_late": "find v({e_out.1}) at=1",
                "plus_input": "find v({amp.IN+}) at=1",
            },
            claims=[
                Claim("e_late", 0, within=1e-3, absolute=True, unit="V",
                      note="equal inputs: nothing to integrate, the output stays at zero"),
            ],
            units={"plus_input": "V"},
            note=(
                "Both inputs at 0.5 V. Both op amp inputs charge together toward "
                "0.5 V, and the output does not move."
            ),
        ),
    ],
)
