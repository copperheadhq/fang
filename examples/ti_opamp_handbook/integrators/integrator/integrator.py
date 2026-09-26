"""The integrator, SBOA092B page 55.

    E_O = -Z_O/Z_I E_I = -E_I/(R_I C_O p) = -1/(R_I C_O) integral E_I dt

The handbook gets it from the inverting amplifier by putting a capacitor where
R_O was: Z_O = 1/(C_O p), with p the operator d/dt, or j 2 pi f for a sine.
The figure names R_I and C_O and gives them no values, so `values` records the
pair chosen here: 10 kOhm and 0.1 uF, R_I C_O = 1 ms, a rate of -1000 V/s per
volt and a gain of 1 at 159 Hz.

The figure has no reset, and an integrator with nothing across its capacitor
keeps whatever it starts with, so the transient run starts it at zero with an
initial condition (`.ic`) on the output and the summing point. That is the
bench's, not the circuit's.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Hz, Parameter, System, UnitLiteral, kOhm, require, uF
from fang.parts import Capacitor, Resistor
from fang.rationale import Chooses, Cites
from fang.simulation import ACSweep, Transient

from handbook import (
    Bench,
    Claim,
    Ground,
    OpAmp,
    Run,
    Terminal,
    corner,
    equals,
    negative,
    over,
    product,
    ratio,
    within,
)

#: A rate: volts of output per second, for each volt of input.
per_second = UnitLiteral("1/s")


class Integrator(System):
    """E_I through R_I into the summing point, C_O back from the output."""

    figure = Cites(
        "E_O = -Z_O/Z_I E_I = -E_I/(R_I C_O p) = -1/(R_I C_O) integral E_I dt",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 55, Integrators",
    )

    values = Chooses(
        "What are R_I and C_O?",
        selected="10 kOhm and 0.1 uF: R_I C_O = 1 ms, -1000 V/s per volt, unity gain at 159 Hz",
        alternatives=[
            {
                "option": "100 kOhm and 1 uF, as on page 56",
                "reason": "page 56 is its own program; a different pair shows the formula is general",
            },
            {
                "option": "leave them unknown",
                "reason": "a rate nobody can compute is not a claim anything can check",
            },
        ],
        rationale=(
            "the figure names the parts and gives no values",
            "a unity-gain frequency in the audio band is far below the op amp's "
            "10 MHz, so the ideal algebra is what the bench should measure",
        ),
    )

    start = Chooses(
        "Where does the output start?",
        selected="at zero, from an initial condition the transient run sets",
        alternatives=[
            {
                "option": "a reset switch",
                "reason": "the page 55 figure draws none; pages 56 onward add one",
            },
        ],
        rationale=(
            "with nothing across C_O the op amp integrates any offset, so the "
            "starting point has to be said rather than left to the solver",
        ),
    )

    rate = Parameter("1/s", default=-1000 * per_second, description="-1/(R_I C_O)")
    f_unity = Parameter(
        "Hz",
        default=159.15 * Hz,
        description="where |E_O/E_I| = 1/(2 pi f R_I C_O) comes to 1",
    )

    e_in = Terminal()
    e_out = Terminal()
    r_in = Resistor(resistance=10 * kOhm)
    c_out = Capacitor(capacitance=0.1 * uF)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.r_in.p1
        self.r_in.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.c_out.p1
        self.c_out.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe
        self.amp.non_inverting.signal >> self.ground.node

    def constraints(self):
        rc = product(self.r_in.resistance, self.c_out.capacitance)
        require(equals(self.rate, negative(over(1 * ratio, rc))))
        # 1/(2 pi 1 ms) is 159.155 Hz; the parameter is written to five figures.
        require(within(self.f_unity, corner(self.r_in.resistance, self.c_out.capacitance), 0.0001))


BENCH = Bench(
    page=55,
    title="Integrators",
    runs=[
        Run(
            "ramp",
            Transient(stop="10m", step="10u"),
            drive={"e_in": "DC 0.01"},
            cards=[".ic v({amp.OUT})=0 v({amp.IN-})=0"],
            measure={
                "e_1ms": "find v({e_out.1}) at=1m",
                "e_9ms": "find v({e_out.1}) at=9m",
                "rate_per_volt": "(e_9ms - e_1ms) / 8m / 0.01",
            },
            claims=[Claim("rate_per_volt", "rate", within=0.001, unit="/s")],
            units={"e_1ms": "V", "e_9ms": "V"},
            note=(
                "A DC step of 10 mV, the output started at zero by `.ic`. It "
                "ramps at -10 V/s; the slope over 1 ms to 9 ms, divided by E_I, "
                "is the rate."
            ),
        ),
        Run(
            "sine",
            ACSweep(points=20, start="1", stop="100k"),
            drive={"e_in": "DC 0 AC 1"},
            measure={
                "gain_unity": "find vm({e_out.1}) at=159.155",
                "gain_15hz9": "find vm({e_out.1}) at=15.9155",
                "phase_rad": "find vp({e_out.1}) at=159.155",
                "phase_deg": "phase_rad * 180 / pi",
            },
            claims=[
                Claim("gain_unity", 1, within=0.001,
                      note="at f_unity, 1/(2 pi f R_I C_O) is 1"),
                Claim("gain_15hz9", 10, within=0.001,
                      note="a decade lower the gain is ten times higher"),
                Claim("phase_deg", 90, within=0.1, absolute=True,
                      note=(
                          "E_O/E_I = -1/(j 2 pi f R_I C_O) = +j/(2 pi f R_I C_O): the "
                          "integral lags the input by 90 degrees and the inversion "
                          "adds 180, so the output leads by 90"
                      )),
            ],
            units={"phase_rad": ""},
        ),
    ],
)
