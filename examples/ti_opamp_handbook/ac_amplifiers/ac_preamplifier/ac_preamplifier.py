"""The a.c. preamplifier, SBOA092B page 78.

    E_O / E_I = (R_0 + R_1) / R_1 = 500
    f_-3dB = 1 / (2 pi R_1 C_1) = 1.6 Hz,   R_1 C_1 = R_2 C_2

The double-rolloff amplifier of page 77 built for a large gain. E_I reaches
the + input through C_2 (1 uF); R_2 (100 kOhm) returns it to the junction at
the foot of C_1 (1000 uF), which runs up to the - input. From that junction
R_1 (200 Ohm) goes to ground, and beside it R_3 (2.2 kOhm) in series with
R_4, a 10 kOhm rheostat (its wiper tied to its grounded end): the "fine gain
adjust". R_0 (100 kOhm) closes the loop and C_3 (10 uF) couples the output
out. In the midband C_1 is a short, and what the - input sees to ground is
R_1 in parallel with R_3 + R_4, so

    E_O / E_I = 1 + R_0 / (R_1 || (R_3 + R_4))

which runs from 509 (R_4 at its full 10 kOhm) to 546 (R_4 at zero). The
printed 500 is (R_0 + R_1) / R_1 = 501 with R_3 and R_4 left out; no setting
of R_4 reaches it. The printed corner is off too: 1/(2 pi 200 1000u) is
0.80 Hz, not 1.6, and 1.6 Hz is 1/(2 pi R_2 C_2) instead. The rule R_1 C_1 =
R_2 C_2 is not met: 0.2 s against 0.1 s, so the response peaks 3.4 dB above
the midband near 1.3 Hz before it falls away at 40 dB a decade.

The program keeps the drawn values, sets R_4 to full travel (`trim`), and
gives C_3 a load to drive (`load`), because the figure draws none and an
output coupling capacitor into nothing has no d.c. path.
"""

import sys
from decimal import Decimal
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Hz, Ohm, Parameter, System, kOhm, require, s, uF
from fang.parts import Capacitor, Resistor
from fang.rationale import Chooses, Cites
from fang.simulation import ACSweep, OperatingPoint

from handbook import (
    Bench,
    Claim,
    Ground,
    OpAmp,
    Potentiometer,
    Run,
    Terminal,
    at_least,
    corner,
    equals,
    over,
    parallel,
    product,
    ratio,
    total,
    within,
)


class AcPreamplifier(System):
    """A bootstrapped double-rolloff stage at a gain of 500, with a trim and an output capacitor."""

    figure = Cites(
        "Completely developed AC amplifier with high Z_in and double rolloff "
        "rate and gain trim. E_O / E_I = (R_0 + R_1) / R_1 = 500. R4 - Fine "
        "gain adjust. Low Frequency rolloff begins f_-3dB = 1 / (2 pi R_1 C_1) "
        "= 1.6 Hz. R_1 C_1 = R_2 C_2",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 78, AC Preamplifier",
    )

    trim = Chooses(
        "Where is R_4 set?",
        selected="full travel, 10 kOhm in series with R_3, for a gain of 509, the nearest the trim comes to the printed 500",
        alternatives=[
            {
                "option": "the setting that gives 500",
                "reason": "there is none: R_3 + R_4 in parallel with R_1 can only lower 200 Ohm, and raise the gain above 501",
            },
            {
                "option": "leave R_3 and R_4 out, as the printed formula does",
                "reason": "the figure draws them, and a trim that is not there trims nothing",
            },
        ],
        rationale=(
            "R_4 is drawn as a rheostat: its wiper runs to the grounded end",
            "the page gives no setting",
        ),
    )

    load = Chooses(
        "What does C_3 drive?",
        selected="100 kOhm to ground, the input of a following stage; its corner with C_3 is 0.16 Hz",
        alternatives=[
            {
                "option": "nothing",
                "reason": "the output node would have no d.c. path, and the simulator cannot solve it",
            },
            {
                "option": "10 kOhm",
                "reason": "its 1.6 Hz corner with C_3 would sit on top of the stage's own and be mistaken for it",
            },
        ],
        rationale=("the figure draws no load",),
    )

    a_v = Parameter("1", default=Decimal("509.2") * ratio, description="E_O / E_I in the midband, R_4 at full travel")
    a_v_max = Parameter("1", default=Decimal("546.5") * ratio, description="the same with R_4 at zero")
    f_low = Parameter("Hz", default=Decimal("0.8") * Hz, description="1 / (2 pi R_1 C_1), computed")
    t_1 = Parameter("s", default=Decimal("0.2") * s, description="R_1 C_1")
    t_2 = Parameter("s", default=Decimal("0.1") * s, description="R_2 C_2")

    e_in = Terminal()
    e_out = Terminal()
    c_2 = Capacitor(capacitance=1 * uF)
    r_2 = Resistor(resistance=100 * kOhm)
    c_1 = Capacitor(capacitance=1000 * uF)
    r_1 = Resistor(resistance=200 * Ohm)
    r_3 = Resistor(resistance=Decimal("2.2") * kOhm)
    r_4 = Potentiometer(resistance=10 * kOhm, setting=Decimal("1") * ratio)
    r_0 = Resistor(resistance=100 * kOhm)
    c_3 = Capacitor(capacitance=10 * uF)
    r_load = Resistor(resistance=100 * kOhm)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.c_2.p1
        self.c_2.p2 >> self.amp.non_inverting.signal
        self.amp.non_inverting.signal >> self.r_2.p1

        self.amp.inverting.signal >> self.c_1.p1
        self.amp.inverting.signal >> self.r_0.p1
        self.r_0.p2 >> self.amp.output.signal

        # The junction at the foot of C_1: R_2's return, R_1, and the trim.
        self.c_1.p2 >> self.r_1.p1
        self.r_2.p2 >> self.r_1.p1
        self.r_1.p1 >> self.r_3.p1
        self.r_3.p2 >> self.r_4.end_a
        self.r_4.wiper >> self.ground.node
        self.r_4.end_b >> self.ground.node
        self.r_1.p2 >> self.ground.node

        # The output, through C_3.
        self.amp.output.signal >> self.c_3.p1
        self.c_3.p2 >> self.e_out.probe
        self.e_out.probe >> self.r_load.p1
        self.r_load.p2 >> self.ground.node

    def constraints(self):
        trim = product(self.r_4.setting, self.r_4.resistance)
        foot = parallel(self.r_1.resistance, total(self.r_3.resistance, trim))
        require(within(self.a_v, total(1 * ratio, over(self.r_0.resistance, foot)), 0.001))
        # R_4 at zero leaves R_3 alone beside R_1.
        require(
            within(
                self.a_v_max,
                total(1 * ratio, over(self.r_0.resistance, parallel(self.r_1.resistance, self.r_3.resistance))),
                0.001,
            )
        )
        # The printed 1.6 Hz is twice this.
        require(within(self.f_low, corner(self.r_1.resistance, self.c_1.capacitance), 0.01))
        # And the printed rule does not hold: R_1 C_1 is twice R_2 C_2.
        require(equals(self.t_1, product(self.r_1.resistance, self.c_1.capacitance)))
        require(equals(self.t_2, product(self.r_2.resistance, self.c_2.capacitance)))
        require(at_least(self.t_1, product(self.t_2, 2 * ratio)))


BENCH = Bench(
    page=78,
    title="AC Preamplifier",
    runs=[
        Run(
            "response",
            ACSweep(points=200, start="0.001", stop="10meg"),
            drive={"e_in": "DC 0 AC 1"},
            measure={
                "gain_100": "find vm({e_out.1}) at=100",
                "f_3db": "when vdb({e_out.1})=51.1087 cross=1",
                "peak": "max vm({e_out.1}) from=0.01 to=10",
                "g_01": "find vm({amp.OUT}) at=0.1",
                "g_03": "find vm({amp.OUT}) at=0.3",
                "slope": "20 * log10(g_03 / g_01) / log10(3)",
                "p_re": "find vr({amp.IN+}) at=100",
                "p_im": "find vi({amp.IN+}) at=100",
                "j_re": "find vr({r_1.1}) at=100",
                "j_im": "find vi({r_1.1}) at=100",
                "z_in_100": "100k / sqrt((p_re - j_re)^2 + (p_im - j_im)^2)",
                "f_upper": "when vdb({e_out.1})=51.1087 cross=2",
            },
            claims=[
                Claim(
                    "gain_100",
                    "a_v",
                    within=0.001,
                    note=(
                        "1 + 100k / (200 || 12.2k), read at 100 Hz, clear of "
                        "the low corners and of the op amp's 20 kHz. The "
                        "handbook prints 500; (R_0 + R_1) / R_1 is 501, and "
                        "with the trim beside R_1 the gain is 509 to 546"
                    ),
                ),
                Claim(
                    "f_3db",
                    "f_low",
                    within=0.02,
                    unit="Hz",
                    note=(
                        "the handbook prints 1.6 Hz; 1/(2 pi R_1 C_1) is 0.80 Hz. "
                        "The circuit, with its double pole and C_3 into 100 k, "
                        "is 3 dB down at 0.81 Hz, hence 2%"
                    ),
                ),
                Claim(
                    "peak",
                    757.7,
                    within=0.005,
                    note=(
                        "3.45 dB above the midband near 1.3 Hz, from the transfer "
                        "function with R_1 C_1 = 0.2 s and R_2 C_2 = 0.1 s; the "
                        "page's rule R_1 C_1 = R_2 C_2 would bring it down to 1.2 dB"
                    ),
                ),
                Claim(
                    "slope",
                    40,
                    within=1.5,
                    absolute=True,
                    note="dB per decade at the op amp's output between 0.1 Hz and 0.3 Hz: the double rolloff",
                ),
            ],
            units={"f_upper": "Hz", "z_in_100": "Ohm"},
            note=(
                "E_O is 3 dB down from 509.2 at 51.11 dB. z_in_100 is E_I over "
                "the current in R_2 at 100 Hz, the bootstrapped input "
                "impedance the page calls high Z_in; it is not a numeric claim of "
                "the handbook."
            ),
        ),
        Run(
            "trim_at_zero",
            ACSweep(points=10, start="10", stop="1k"),
            drive={"e_in": "DC 0 AC 1"},
            settings={"r_4": {"setting": 0}},
            measure={"gain_100": "find vm({e_out.1}) at=100"},
            claims=[Claim("gain_100", "a_v_max", within=0.001, note="1 + 100k / (200 || 2.2k)")],
        ),
        Run(
            "dc",
            OperatingPoint(),
            drive={"e_in": "DC 1"},
            measure={"e_amp": "v({amp.OUT})", "e_out": "v({e_out.1})"},
            claims=[
                Claim(
                    "e_amp",
                    0,
                    within=1e-6,
                    absolute=True,
                    unit="V",
                    note="C_2 blocks the 1 V, and C_1 leaves the stage a follower of its grounded + input",
                )
            ],
            units={"e_out": "V"},
        ),
    ],
)
