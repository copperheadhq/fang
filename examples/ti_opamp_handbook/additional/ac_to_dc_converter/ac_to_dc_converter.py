"""The AC to DC converter, SBOA092B page 88 (bottom).

    E_O average = 0.9 E_I rms,   E_I = 6 mV to 6 V rms at 10 to 1000 Hz

Two stages. The first is a precision half-wave rectifier: E_I through R_1 into
the summing point, R_2 back from a diode that conducts when the output falls,
R_4 back through a diode that conducts when it rises. The half-wave E_H is
taken at the R_2 end, so E_H = -E_I while E_I is positive and zero otherwise.

The second stage is a summer with a filter across it: E_I through R_3
(10 kOhm) and E_H through R_6 (5 kOhm) into the summing point, R_7 (10 kOhm)
and the rheostat R_8 (2 kOhm) back from the output, and C (100 uF) across both.
E_H counts twice as much as E_I, so the current into the summing point is
-|E_I| / R_3 on both halves, and the output is the full-wave rectified input,
times (R_7 + R_8') / R_3, averaged by the filter.

The average of a full-wave rectified sine is 2 sqrt(2) / pi = 0.9003 times its
rms, so a gain of exactly 1 is what the page's 0.9 asks for. R_8 trims the
gain up from there to cover the resistors' tolerances; with the drawn values
exact, the program sets it to zero (`trim`).
"""

import sys
from decimal import Decimal
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Parameter, System, kOhm, require, uF
from fang.parts import Capacitor, Resistor
from fang.rationale import Calculates, Chooses, Cites
from fang.simulation import Transient

from handbook import (
    Bench,
    Claim,
    Ground,
    OpAmp,
    Potentiometer,
    Run,
    SignalDiode,
    Terminal,
    equals,
    over,
    product,
    ratio,
    total,
    within,
)

#: The mean of a full-wave rectified sine over its rms: 2 sqrt(2) / pi.
SINE_AVERAGE_OVER_RMS = ratio("0.9003163161571062")


class AcToDcConverter(System):
    """A precision half-wave, and a filtered summer that adds it twice to E_I."""

    figure = Cites(
        "E_O average = 0.9 E_I rms. E_I = 6 mV to 6 V rms @ 10 to 1000 Hz. "
        "Precision conversion for measurement or control. Full wave rectifier "
        "with a smoothing filter.",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 88, AC to DC Converter",
    )

    reading = Chooses(
        "How is the figure wired?",
        selected=(
            "R_3 runs from E_I to the second summing point; R_1 from E_I to the "
            "first; R_2 from the first summing point to a node whose diode points "
            "down into the first op amp's output, and R_6 from that node to the "
            "second summing point; R_4 returns through a diode pointing left, "
            "from the output; R_7 and R_8 in series, with C across them, from the "
            "second summing point to E_O"
        ),
        alternatives=[
            {
                "reading": "E_H taken at the R_4 end",
                "reason": (
                    "R_6 leaves from the junction of R_2 and the downward diode; "
                    "R_4's diode joins the output below it"
                ),
            },
        ],
        rationale=(
            "under this reading E_H is -E_I for E_I > 0, and R_6 = R_3 / 2 makes "
            "the sum -|E_I| / R_3 on both halves: a full wave, as the page says",
        ),
    )

    trim = Chooses(
        "Where is the rheostat R_8 set?",
        selected="at zero, so the feedback is R_7 alone and the gain is exactly 1",
        alternatives=[
            {
                "option": "mid-travel, 1 kOhm",
                "reason": (
                    "a gain of 1.1, which reads 0.99 E_I rms: 10% high with "
                    "the drawn resistors exact"
                ),
            },
        ],
        rationale=(
            "the full-wave average is already 0.9003 of the rms at unity gain",
            "R_8 only adds to R_7, so it is there to trim up for resistors that "
            "come out low; the simulated ones do not",
        ),
    )

    bench = Chooses(
        "How long does the filter take, and what is E_I?",
        selected=(
            "a 100 Hz sine at 6 V rms and at 6 mV rms, each run for 10 s, with "
            "the average taken over the last second"
        ),
        alternatives=[
            {
                "option": "an initial condition on C at the expected output",
                "reason": "it would assume the answer the run is there to check",
            },
            {
                "option": "1 kHz",
                "reason": "ten times as many cycles to step through for the same settling",
            },
        ],
        rationale=(
            "C against R_7 is 1 s; after 9 s the start-up error is e^-9, about 0.01%",
            "100 Hz is inside the page's 10 to 1000 Hz, and the ripple at 200 Hz "
            "through a 1 s filter is a few tenths of a millivolt per volt",
        ),
    )

    average = Calculates(
        "E_O average / E_I rms = (2 sqrt(2) / pi) (R_7 + R_8') / R_3",
        inputs=("r_3", "r_7", "r_8"),
        result="0.9003 with R_8 at zero, which the page prints as 0.9",
    )

    k_avg = Parameter(
        "1",
        default=Decimal("0.9") * ratio,
        description="E_O average / E_I rms",
    )
    gain = Parameter(
        "1",
        default=1 * ratio,
        description="(R_7 + R_8') / R_3: the full-wave gain before the filter",
    )

    e_in = Terminal()
    e_out = Terminal()
    r_1 = Resistor(resistance=10 * kOhm)
    r_2 = Resistor(resistance=10 * kOhm)
    r_4 = Resistor(resistance=10 * kOhm)
    d_half = SignalDiode()
    d_return = SignalDiode()
    amp_1 = OpAmp()
    r_3 = Resistor(resistance=10 * kOhm)
    r_6 = Resistor(resistance=5 * kOhm)
    r_7 = Resistor(resistance=10 * kOhm)
    r_8 = Potentiometer(resistance=2 * kOhm, setting=0 * ratio)
    c = Capacitor(capacitance=100 * uF)
    amp_2 = OpAmp()
    ground = Ground()

    def architecture(self):
        # The half-wave stage.
        self.e_in.probe >> self.r_1.p1
        self.r_1.p2 >> self.amp_1.inverting.signal
        self.amp_1.non_inverting.signal >> self.ground.node
        self.amp_1.inverting.signal >> self.r_2.p1
        self.r_2.p2 >> self.d_half.p1
        self.d_half.p2 >> self.amp_1.output.signal
        self.amp_1.inverting.signal >> self.r_4.p1
        self.r_4.p2 >> self.d_return.p2
        self.d_return.p1 >> self.amp_1.output.signal

        # The summer and its filter.
        self.e_in.probe >> self.r_3.p1
        self.r_3.p2 >> self.amp_2.inverting.signal
        self.r_2.p2 >> self.r_6.p1
        self.r_6.p2 >> self.amp_2.inverting.signal
        self.amp_2.inverting.signal >> self.r_7.p1
        self.r_7.p2 >> self.r_8.end_a
        self.r_8.wiper >> self.r_8.end_b
        self.r_8.end_b >> self.amp_2.output.signal
        self.amp_2.inverting.signal >> self.c.p1
        self.c.p2 >> self.amp_2.output.signal
        self.amp_2.output.signal >> self.e_out.probe
        self.amp_2.non_inverting.signal >> self.ground.node

    def constraints(self):
        # Full wave: the half-wave's weight through R_6 is twice E_I's through R_3.
        require(
            equals(
                over(self.r_2.resistance, product(self.r_1.resistance, self.r_6.resistance)),
                over(2 * ratio, self.r_3.resistance),
            )
        )
        require(
            equals(
                self.gain,
                over(
                    total(self.r_7.resistance, product(self.r_8.resistance, self.r_8.setting)),
                    self.r_3.resistance,
                ),
            )
        )
        # The page rounds 0.9003 to 0.9.
        require(within(self.k_avg, product(SINE_AVERAGE_OVER_RMS, self.gain), 0.001))


def _run(name: str, rms: str, peak: str, within: float, why: str, note: str) -> Run:
    return Run(
        name,
        Transient(stop="10", step="50u"),
        drive={"e_in": f"SIN(0 {peak} 100)"},
        measure={
            "e_average": "avg v({e_out.1}) from=9 to=10",
            "ripple": "pp v({e_out.1}) from=9 to=10",
            "k_measured": f"e_average / {rms}",
        },
        claims=[
            Claim("k_measured", "k_avg", within=within, note=why),
        ],
        units={"e_average": "V", "ripple": "V"},
        note=note,
    )


BENCH = Bench(
    page=88,
    title="AC to DC Converter",
    runs=[
        _run(
            "six_volts", "6", "8.485281", 0.001,
            "the page's 0.9; the circuit gives 0.9003 at unity gain, and what is "
            "left of the filter's start-up after 9 s is e^-9, a hundredth of a percent",
            "E_I is 6 V rms (8.485 V peak) at 100 Hz, the top of the page's range. "
            "The average is taken over the last second of ten.",
        ),
        _run(
            "six_millivolts", "6m", "8.485281m", 0.01,
            "1% here: at 8.5 mV peak the signal current through R_1 is under 1 uA, "
            "and the 1N4148 model's 2.5 nA of saturation current through the diode "
            "that should be off, with the 4 pF junction charge moved at each zero "
            "crossing, takes a few tenths of a percent of it",
            "E_I is 6 mV rms at 100 Hz, the bottom of the page's range, where a "
            "diode drop outside the loop would swallow the signal whole. The "
            "average is taken over the last second of ten.",
        ),
    ],
)
