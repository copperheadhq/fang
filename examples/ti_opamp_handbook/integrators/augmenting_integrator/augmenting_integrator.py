"""The augmenting integrator, SBOA092B pages 59 and 60.

    E_O = -(R_O/R_I) E_I - 1/(C_O R_I) integral E_I dt

R_I is 10 kOhm; the feedback is R_O (100 kOhm) in series with C_O (10 uF).
The current E_I/R_I flows through both, so the output is the drop across R_O,
-(R_O/R_I) E_I, plus the charge on C_O, -1/(C_O R_I) integral E_I dt: the input
and its integral, summed.

The handbook evaluates this as "-10 E_I - integral E_I dt". The first term is
right, R_O/R_I = 10. The second is not: C_O R_I is 10 uF times 10 kOhm, 0.1 s,
so the integral is multiplied by 10, not 1. The program holds the rate to the
parts, -10 per second, and the simulation agrees with it.

The bench applies a 0.1 V step at 10 ms to an integrator at rest, so both
terms can be read off one waveform: the jump is the proportional part, the
slope after it the integral.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Parameter, System, UnitLiteral, kOhm, require, uF
from fang.parts import Capacitor, Resistor
from fang.rationale import Calculates, Chooses, Cites
from fang.simulation import Transient

from handbook import (
    Bench,
    Claim,
    Ground,
    OpAmp,
    Run,
    Terminal,
    equals,
    negative,
    over,
    product,
    ratio,
)

#: A rate: volts of output per second, for each volt of input.
per_second = UnitLiteral("1/s")


class AugmentingIntegrator(System):
    """E_I through R_I into the summing point; R_O and C_O in series back from the output."""

    figure = Cites(
        "E_O = -(R_O E_I)/R_I - 1/(C_O R_I) integral E_I dt = -10 E_I - integral E_I dt. "
        "Sums the input signal and its time integral.",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="pages 59-60, Augmenting Integrator",
    )

    integral_term = Calculates(
        "1/(C_O R_I) = 1/(10 uF x 10 kOhm)",
        inputs=("c_out", "r_in"),
        result=(
            "10 per second. The handbook's second line prints the integral with "
            "a coefficient of 1, which would need C_O R_I = 1 s (100 uF, or R_I "
            "= 100 kOhm, which would also change the first term to -1)"
        ),
    )

    bench = Chooses(
        "What input shows both terms?",
        selected="a 0.1 V step at 10 ms, from rest",
        alternatives=[
            {
                "option": "a sine",
                "reason": "the two terms add in quadrature and have to be separated again",
            },
        ],
        rationale=(
            "a step makes the proportional term a jump and the integral a ramp, "
            "each read directly",
        ),
    )

    gain = Parameter("1", default=-10 * ratio, description="-R_O/R_I, the proportional term")
    rate = Parameter("1/s", default=-10 * per_second, description="-1/(C_O R_I), the integral term")

    e_in = Terminal()
    e_out = Terminal()
    r_in = Resistor(resistance=10 * kOhm)
    r_out = Resistor(resistance=100 * kOhm)
    c_out = Capacitor(capacitance=10 * uF)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.r_in.p1
        self.r_in.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r_out.p1
        self.r_out.p2 >> self.c_out.p1
        self.c_out.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe
        self.amp.non_inverting.signal >> self.ground.node

    def constraints(self):
        require(equals(self.gain, negative(over(self.r_out.resistance, self.r_in.resistance))))
        require(
            equals(
                self.rate,
                negative(over(1 * ratio, product(self.c_out.capacitance, self.r_in.resistance))),
            )
        )


BENCH = Bench(
    page=60,
    title="Augmenting Integrator",
    runs=[
        Run(
            "step",
            Transient(stop="1.01", step="1m"),
            drive={"e_in": "PWL(0 0 10m 0 10.001m 0.1)"},
            measure={
                "e_early": "find v({e_out.1}) at=0.11",
                "e_late": "find v({e_out.1}) at=1.01",
                "rate_per_volt": "(e_late - e_early) / 0.9 / 0.1",
                "gain_step": "(e_early - rate_per_volt * 0.1 * 0.1) / 0.1",
            },
            claims=[
                Claim("gain_step", "gain", within=0.001,
                      note="the jump at the step: the ramp extrapolated back to 10 ms, over E_I"),
                Claim("rate_per_volt", "rate", within=0.001, unit="/s",
                      note=(
                          "the handbook prints the integral term as -integral E_I dt, a "
                          "rate of -1/s; 1/(C_O R_I) = 1/(10 uF x 10 kOhm) is 10/s, and "
                          "that is what the circuit does"
                      )),
            ],
            units={"e_early": "V", "e_late": "V"},
            note=(
                "E_I steps from 0 to 0.1 V at 10 ms. The output should jump to "
                "-1 V and fall 1 V/s after it: -10 E_I - 10 integral E_I dt."
            ),
        ),
    ],
)
