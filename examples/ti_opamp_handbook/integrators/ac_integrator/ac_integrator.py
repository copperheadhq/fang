"""The AC integrator, SBOA092B page 59 (bottom).

    "Integrates AC component only."

E_I reaches the - input through R_I (100 kOhm), with C_O (0.01 uF) and a reset
switch from there to the output. The odd part of the drawing is the op amp: it
has two outputs, a plain one at the top that is E_O and feeds C_O, and a
bubbled one at the bottom that drives R2 (100 kOhm) to the + input, with C_I
(100 uF) from the + input to ground. The page gives no formula.

The program reads the bubble as an inverted output (`reading`): the op amp is a
differential-output part, and R2 and C_I low-pass -E_O onto the + input, a DC
servo. Then, with tau_1 = R_I C_O = 1 ms and tau_2 = R2 C_I = 10 s,

    E_O/E_I = -(1 + p tau_2) / (1 + 2 p tau_1 + p^2 tau_1 tau_2)

At DC this is -1: a DC input is passed inverted, not integrated, and the output
does not ramp. Well above the corner it is -1/(p tau_1), the integrator,
-1/(2 pi f R_I C_O) in magnitude. The two meet at a resonance at
1/(2 pi sqrt(tau_1 tau_2)) = 1.59 Hz with a Q of sqrt(tau_2/tau_1)/2 = 50,
which is what the drawn values give and which the handbook does not mention: a
DC step makes the output ring at 1.6 Hz for tens of seconds before it settles
at -E_I.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Hz, Parameter, System, kOhm, require, uF
from fang.parts import Capacitor, Resistor
from fang.rationale import Calculates, Chooses, Cites
from fang.simulation import ACSweep, OperatingPoint, Transient

from handbook import (
    TWO_PI,
    Bench,
    Claim,
    DifferentialOpAmp,
    Ground,
    Run,
    Switch,
    Terminal,
    corner,
    over,
    product,
    ratio,
    within,
)


class AcIntegrator(System):
    """An integrator whose + input follows the inverted output, low-passed by R2 and C_I."""

    figure = Cites(
        "Integrates AC component only.",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 59, AC Integrator",
    )

    reading = Chooses(
        "What is the bubbled output at the bottom of the op amp, and what do R2 and C_I do?",
        selected=(
            "an inverted output (the op amp has complementary outputs); R2 and C_I "
            "low-pass -E_O onto the + input, a DC servo that holds the DC gain at -1"
        ),
        alternatives=[
            {
                "reading": "the same output as E_O, drawn twice",
                "reason": (
                    "then R2 and C_I feed +E_O back to the + input, positive feedback "
                    "at DC: the transfer function has a pole at +1/sqrt(tau_1 tau_2) "
                    "and the output runs to a rail"
                ),
            },
            {
                "reading": "R2 and C_I as a bias-current return only, the + input otherwise at ground",
                "reason": (
                    "that is an ordinary integrator, which ramps on a DC input; it "
                    "cannot integrate the AC component only"
                ),
            },
        ],
        rationale=(
            "only the inverted reading makes the stated function true: DC gain -1, "
            "integration above the corner",
            "the handbook uses op amps with two outputs elsewhere (page 69), and a "
            "bubble is the usual mark of the inverting one",
        ),
    )

    response = Calculates(
        "E_O/E_I = -(1 + p R2 C_I) / (1 + 2 p R_I C_O + p^2 R_I C_O R2 C_I)",
        inputs=("r_in", "c_out", "r2", "c_i"),
        result=(
            "-1 at DC; -1/(p R_I C_O) above the corner, unity gain at 159 Hz and "
            "1.59 at 100 Hz; a resonance at 1.59 Hz with Q = 50, whose peak the "
            "AC sweep shows near 5000"
        ),
    )

    f_unity = Parameter(
        "Hz",
        default=159.15 * Hz,
        description="where the integrator's gain 1/(2 pi f R_I C_O) is 1",
    )
    f_corner = Parameter(
        "Hz",
        default=1.5915 * Hz,
        description="1/(2 pi sqrt(R_I C_O R2 C_I)): below it the circuit stops integrating",
    )
    q = Parameter("1", default=50 * ratio, description="sqrt(R2 C_I / (R_I C_O)) / 2, the corner's Q")

    e_in = Terminal()
    e_out = Terminal()
    r_in = Resistor(resistance=100 * kOhm)
    c_out = Capacitor(capacitance=0.01 * uF)
    reset = Switch()
    r2 = Resistor(resistance=100 * kOhm)
    c_i = Capacitor(capacitance=100 * uF)
    amp = DifferentialOpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.r_in.p1
        self.r_in.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.c_out.p1
        self.c_out.p1 >> self.reset.p1
        self.c_out.p2 >> self.amp.output.signal
        self.reset.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe
        # The bubbled output, through R2 to the + input, C_I to ground.
        self.amp.output_minus.signal >> self.r2.p1
        self.r2.p2 >> self.amp.non_inverting.signal
        self.amp.non_inverting.signal >> self.c_i.p1
        self.c_i.p2 >> self.ground.node

    def constraints(self):
        tau_1 = product(self.r_in.resistance, self.c_out.capacitance)
        tau_2 = product(self.r2.resistance, self.c_i.capacitance)
        require(within(self.f_unity, corner(self.r_in.resistance, self.c_out.capacitance), 0.0001))
        # Squared, so no square root is needed: f^2 = 1/((2 pi)^2 tau_1 tau_2).
        require(
            within(
                product(self.f_corner, self.f_corner),
                over(1 * ratio, product(TWO_PI, TWO_PI, tau_1, tau_2)),
                0.0002,
            )
        )
        require(within(product(self.q, self.q), over(tau_2, product(4 * ratio, tau_1)), 0.0001))


BENCH = Bench(
    page=59,
    title="AC Integrator",
    runs=[
        Run(
            "dc",
            OperatingPoint(),
            drive={"e_in": "DC 1"},
            measure={"dc_gain": "v({e_out.1}) / v({e_in.1})", "plus_input": "v({amp.IN+})"},
            claims=[Claim("dc_gain", -1, within=0.001,
                          note="a DC input comes out inverted, not integrated: nothing ramps")],
            units={"plus_input": "V"},
            note="E_I = 1 V DC. C_I has charged to -E_O, and the - input follows it to E_I.",
        ),
        Run(
            "sine",
            ACSweep(points=50, start="1m", stop="100k"),
            drive={"e_in": "DC 0 AC 1"},
            measure={
                "gain_unity": "find vm({e_out.1}) at=159.155",
                "gain_100hz": "find vm({e_out.1}) at=100",
                "phase_rad": "find vp({e_out.1}) at=100",
                "phase_deg": "phase_rad * 180 / pi",
                "gain_1mhz": "find vm({e_out.1}) at=0.001",
                "peak": "max vm({e_out.1})",
                "f_peak": "when vm({e_out.1})=peak",
            },
            claims=[
                Claim("gain_unity", 1, within=0.001, note="1/(2 pi f_unity R_I C_O) = 1"),
                Claim("gain_100hz", 1.5915, within=0.001, note="1/(2 pi 100 Hz x 1 ms)"),
                Claim("phase_deg", 90, within=0.1, absolute=True,
                      note="an inverting integrator: the output leads the input by 90 degrees"),
                Claim("gain_1mhz", 1.002, within=0.001,
                      note="at 1 mHz the circuit is back to its DC gain of 1 (|1 + j 2 pi f tau_2| = 1.002)"),
            ],
            units={"f_peak": "Hz"},
            note=(
                "Above the 1.59 Hz corner the circuit integrates; below it the gain "
                "returns to 1. The peak at the corner is the Q of 50 the drawn values "
                "give; it is not a handbook claim."
            ),
        ),
        Run(
            "ac_on_dc",
            Transient(stop="1.1", step="10u"),
            drive={"e_in": "SIN(0.1 0.1 100 0 0 90)"},
            # The op amp's outputs are ideal sources, so an initial condition on
            # them is ignored; the state to set is the model's internal node, which
            # ngspice names through the instances, XU1 then XHALF.
            cards=[".ic v(xu1.xhalf.n1)=-0.2 v({amp.IN-})=0.1"],
            measure={
                "e_pp": "pp v({e_out.1}) from=1.0 to=1.03",
                "e_avg": "avg v({e_out.1}) from=0.4 to=1.03",
            },
            claims=[
                Claim("e_pp", 0.31831, within=0.01, unit="V",
                      note=(
                          "0.1 V at 100 Hz integrated: 2 x 0.1/(2 pi 100 Hz x 1 ms). 1%: "
                          "the start is close to the steady state, not exactly on it, "
                          "and what is left rings at 1.6 Hz under the 100 Hz wave"
                      )),
                Claim("e_avg", -0.1, within=0.003, absolute=True, unit="V",
                      note="the 0.1 V DC component passes at -1 and does not ramp"),
            ],
            note=(
                "0.1 V DC plus a 0.1 V, 100 Hz cosine. The capacitors start where "
                "the steady state puts them at t = 0 (the `.ic`), so the 1.6 Hz "
                "resonance is barely rung. The swing is read over 1.0 to 1.03 s; the average over 0.4 to 1.03 s, 63 cycles "
                "of the input and one period of that resonance."
            ),
        ),
        Run(
            "dc_step",
            Transient(stop="100", step="1m"),
            drive={"e_in": "PWL(0 0 10m 0 10.001m 0.01)"},
            measure={
                "e_min": "min v({e_out.1}) from=0 to=100",
                "e_max": "max v({e_out.1}) from=0 to=100",
                "e_100s": "find v({e_out.1}) at=100",
            },
            claims=[
                Claim("e_100s", -0.01, within=0.5e-3, absolute=True, unit="V",
                      note=(
                          "an ordinary integrator would be at -1000 V (a rail) by now; "
                          "this one has settled at -E_I"
                      )),
            ],
            units={"e_min": "V", "e_max": "V"},
            note=(
                "A 10 mV DC step at 10 ms, from rest. The output rings at 1.6 Hz "
                "(the Q of 50) and settles at -10 mV with a 10 s time constant; "
                "the swing it reaches first is in e_min and e_max."
            ),
        ),
    ],
)
