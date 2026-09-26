"""The summing integrator, SBOA092B page 58 (top).

    E_O = -1/(RC) integral (E1 + E2 + E3) dt = -10 integral (E1 + E2 + E3) dt

Three 100 kOhm inputs meet at the summing point, C_O is 1 uF, and a switch
across C_O resets it. Each input puts E_n/100k into the summing point and C_O
integrates the sum, so the output ramps at -10 V/s for every volt of
E1 + E2 + E3.

The bench is the program's to choose: the reset switch closed at t = 0 and
opened at 10 ms, and the inputs steady from the start. One run puts 0.1, 0.2
and 0.3 V on the three inputs; a second mixes the signs, 0.5, -0.2 and 0.1 V,
so the claim is about the sum and not about each input on its own.
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

#: The reset: closed at t = 0, open from 10 ms.
RESET = "PWL(0 1 10m 1 10.001m 0)"


class SummingIntegrator(System):
    """Three inputs through 100 kOhm each into one summing point, C_O across the op amp."""

    figure = Cites(
        "E_O = -1/(RC) integral (E1 + E2 + E3) dt = -10 integral (E1 + E2 + E3) dt. "
        "One amplifier replaces separate summer and integrator circuits.",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 58, Summing Integrator",
    )

    bench = Chooses(
        "What goes on the three inputs, and when does the integrator start?",
        selected=(
            "steady inputs whose sum is 0.6 V in one run and 0.4 V (with one "
            "negative input) in another; the reset switch opens at 10 ms"
        ),
        alternatives=[
            {
                "option": "one input at a time",
                "reason": "that checks three integrators, not that the inputs are summed",
            },
        ],
        rationale=(
            "the figure gives the parts and no drive",
            "a mixed-sign run shows the output follows the algebraic sum",
        ),
    )

    rate = Parameter(
        "1/s",
        default=-10 * per_second,
        description="dE_O/dt for each volt of E1 + E2 + E3: -1/(R C_O), the three R equal",
    )

    e1 = Terminal()
    e2 = Terminal()
    e3 = Terminal()
    e_out = Terminal()
    r1 = Resistor(resistance=100 * kOhm)
    r2 = Resistor(resistance=100 * kOhm)
    r3 = Resistor(resistance=100 * kOhm)
    c_out = Capacitor(capacitance=1 * uF)
    reset = Switch()
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e1.probe >> self.r1.p1
        self.e2.probe >> self.r2.p1
        self.e3.probe >> self.r3.p1
        self.r1.p2 >> self.amp.inverting.signal
        self.r2.p2 >> self.amp.inverting.signal
        self.r3.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.c_out.p1
        self.c_out.p1 >> self.reset.p1
        self.c_out.p2 >> self.amp.output.signal
        self.reset.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe
        self.amp.non_inverting.signal >> self.ground.node

    def constraints(self):
        # Each input has its own rate; the claim is that they are the same one.
        for r in (self.r1, self.r2, self.r3):
            require(
                equals(
                    self.rate,
                    negative(over(1 * ratio, product(r.resistance, self.c_out.capacitance))),
                )
            )


def _ramp(name: str, e1: float, e2: float, e3: float, note: str) -> Run:
    total = e1 + e2 + e3
    return Run(
        name,
        Transient(stop="1.1", step="1m"),
        drive={"e1": f"DC {e1}", "e2": f"DC {e2}", "e3": f"DC {e3}"},
        switches={"reset": RESET},
        measure={
            "e_early": "find v({e_out.1}) at=0.1",
            "e_late": "find v({e_out.1}) at=1.1",
            "rate_per_volt": f"(e_late - e_early) / 1.0 / {total:g}",
        },
        claims=[Claim("rate_per_volt", "rate", within=0.001, unit="/s")],
        units={"e_early": "V", "e_late": "V"},
        note=note,
    )


BENCH = Bench(
    page=58,
    title="Summing Integrator",
    runs=[
        _ramp(
            "sum",
            0.1, 0.2, 0.3,
            "E1 + E2 + E3 = 0.6 V, so the output falls 6 V/s once the switch "
            "opens at 10 ms. The slope over 0.1 s to 1.1 s, divided by 0.6 V, is the rate.",
        ),
        _ramp(
            "mixed_signs",
            0.5, -0.2, 0.1,
            "E1 + E2 + E3 = 0.4 V with E2 negative: the output falls 4 V/s, "
            "the rate of the algebraic sum.",
        ),
    ],
)
