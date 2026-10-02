"""The simple integrator, SBOA092B page 56 (top).

    E_O = -1/(R_I C_O) integral E_I dt = -10 integral E_I dt

R_I is 100 kOhm and C_O is 1 uF, so R_I C_O is 0.1 s and the output ramps at
-10 V/s for every volt at the input. The switch across C_O is the reset: the
handbook says to close it to reset to zero.

The figure says nothing about when the switch opens or what E_I is, so the
program had to decide the bench: the switch is closed at t = 0, which holds the
output at zero while the input is already applied, and opens at 10 ms; E_I is a
steady 0.1 V, so the ramp runs at -1 V/s and stays inside the swing for the
whole second the run lasts.
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
    Switch,
    Terminal,
    equals,
    negative,
    over,
    product,
    ratio,
)

#: A rate: volts of output per second, for each volt of input.
per_second = UnitLiteral("1/s")


class SimpleIntegrator(System):
    """E_I through R_I into the summing point, C_O back from the output, a switch across C_O."""

    figure = Cites(
        "E_O = -(1/(R_I C_O)) integral E_I dt = -10 integral E_I dt. "
        "Close switch to reset to zero.",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 56, Simple Integrators",
    )

    bench = Chooses(
        "How is the integrator reset and started?",
        selected=(
            "the switch closed at t = 0 and opened at 10 ms, with a steady 0.1 V "
            "already on E_I, so the ramp starts from zero when the switch opens"
        ),
        alternatives=[
            {
                "option": "no switch, an initial condition on C_O",
                "reason": "the figure draws the switch, and the reset is what it is for",
            },
            {
                "option": "a 1 V input",
                "reason": "at -10 V/s the output would reach the -13.5 V swing in 1.35 s",
            },
        ],
        rationale=(
            "the handbook says only to close the switch to reset to zero",
            "0.1 V gives -1 V/s, a ramp that stays well inside the swing for the run",
        ),
    )

    rate = Parameter(
        "1/s",
        default=-10 * per_second,
        description="dE_O/dt for each volt of E_I: -1/(R_I C_O)",
    )

    e_in = Terminal()
    e_out = Terminal()
    r_in = Resistor(resistance=100 * kOhm)
    c_out = Capacitor(capacitance=1 * uF)
    reset = Switch()
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.r_in.p1
        self.r_in.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.c_out.p1
        self.c_out.p1 >> self.reset.p1
        self.c_out.p2 >> self.amp.output.signal
        self.reset.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe
        self.amp.non_inverting.signal >> self.ground.node

    def constraints(self):
        require(
            equals(
                self.rate,
                negative(over(1 * ratio, product(self.r_in.resistance, self.c_out.capacitance))),
            )
        )


BENCH = Bench(
    page=56,
    title="Simple Integrators",
    runs=[
        Run(
            "ramp",
            Transient(stop="1.1", step="1m"),
            drive={"e_in": "DC 0.1"},
            switches={"reset": "PWL(0 1 10m 1 10.001m 0)"},
            measure={
                "held": "find v({e_out.1}) at=5m",
                "e_early": "find v({e_out.1}) at=0.1",
                "e_late": "find v({e_out.1}) at=1.1",
                "rate_per_volt": "(e_late - e_early) / 1.0 / 0.1",
            },
            claims=[
                Claim("held", 0, within=1e-3, absolute=True, unit="V",
                      note="the switch is closed: the output sits at zero with the input applied"),
                Claim("rate_per_volt", "rate", within=0.001, unit="/s"),
            ],
            units={"e_early": "V", "e_late": "V"},
            note=(
                "E_I is 0.1 V throughout; the reset switch opens at 10 ms. The slope "
                "is taken between 0.1 s and 1.1 s and divided by E_I."
            ),
        ),
    ],
)
