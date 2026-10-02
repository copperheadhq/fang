"""The precision rectifier, SBOA092B page 88 (top).

    E_O peak = -(R_O / R_I) E_I peak = -5 E_I peak

An inverting amplifier with R_I 2 kOhm in and two feedback paths, each an
R_O of 10 kOhm behind a diode, so the op amp closes its loop through one path
on each half of the input. The output terminal is taken from the upper path
only, between its R_O and its diode.

The figure is small and the diodes are the whole circuit, so the program
records its reading as a decision (`reading`): the upper diode points from the
op amp output up to E_O, the lower one from the lower R_O up to the op amp
output. Read that way, a positive E_I drives the output low, the lower diode
closes the loop, and E_O sits on the virtual ground through its R_O at zero.
A negative E_I drives the output high, the upper diode closes the loop through
the upper R_O, and E_O = -5 E_I, a positive hump five times the negative half
of the input. That is the half-wave the page sketches, and the diode drops sit
inside the loop, so they do not show at E_O.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Parameter, System, kOhm, require
from fang.parts import Resistor
from fang.rationale import Chooses, Cites
from fang.simulation import DCSweep, Transient

from handbook import (
    Bench,
    Claim,
    Ground,
    OpAmp,
    Run,
    SignalDiode,
    Terminal,
    equals,
    negative,
    over,
    ratio,
)


class PrecisionRectifier(System):
    """E_I through R_I into the summing point, two diode-steered R_O paths back."""

    figure = Cites(
        "E_O peak = -(R_O/R_I) E_I peak = -5 E_I peak. Half wave with "
        "amplification if desired. Placing rectifiers in feedback loop "
        "decreases non-linearity to very small value.",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 88, Precision Rectifier",
    )

    reading = Chooses(
        "Which way do the two diodes point?",
        selected=(
            "both point up the page: the upper from the op amp output to the E_O "
            "node, the lower from the lower R_O to the op amp output"
        ),
        alternatives=[
            {
                "reading": "both reversed",
                "reason": (
                    "the triangles point up with the bar above them; reversed, E_O "
                    "would be a negative hump for a positive E_I, not the positive "
                    "hump the page sketches"
                ),
            },
        ],
        rationale=(
            "under this reading only one path conducts at a time, which is what "
            "makes the other half of the output zero",
            "E_O is a positive hump, -5 times the negative half of E_I, as the "
            "sketch under the figure draws it",
        ),
    )

    bench = Chooses(
        "What drives E_I?",
        selected="a DC sweep from -2 V to 2 V, and a 1 V peak, 1 kHz sine",
        alternatives=[
            {
                "option": "a 2 V peak sine",
                "reason": "5 x 2 V is 10 V, near enough the swing to muddy the peak",
            },
        ],
        rationale=(
            "the sweep gives the two slopes exactly; the sine shows the half-wave",
        ),
    )

    a_v = Parameter(
        "1",
        default=-5 * ratio,
        description="E_O / E_I on the half that conducts (E_I negative)",
    )

    e_in = Terminal()
    e_out = Terminal()
    r_in = Resistor(resistance=2 * kOhm)
    r_out = Resistor(resistance=10 * kOhm)
    r_out_lower = Resistor(resistance=10 * kOhm)
    d_out = SignalDiode()
    d_clamp = SignalDiode()
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.r_in.p1
        self.r_in.p2 >> self.amp.inverting.signal
        self.amp.non_inverting.signal >> self.ground.node

        # The upper path: R_O to the E_O node, the diode up to it from the output.
        self.amp.inverting.signal >> self.r_out.p1
        self.r_out.p2 >> self.e_out.probe
        self.d_out.p2 >> self.e_out.probe
        self.d_out.p1 >> self.amp.output.signal

        # The lower path: R_O, and the diode up from it into the output.
        self.amp.inverting.signal >> self.r_out_lower.p1
        self.r_out_lower.p2 >> self.d_clamp.p1
        self.d_clamp.p2 >> self.amp.output.signal

    def constraints(self):
        require(equals(self.a_v, negative(over(self.r_out.resistance, self.r_in.resistance))))


BENCH = Bench(
    page=88,
    title="Precision Rectifier",
    runs=[
        Run(
            "transfer",
            DCSweep(source="VDRIVE_e_in", start="-2", stop="2", step="0.01"),
            drive={"e_in": "DC 0"},
            measure={
                "e_at_minus_1": "find v({e_out.1}) at=-1",
                "e_at_plus_1": "find v({e_out.1}) at=1",
                "gain_negative": "e_at_minus_1 / -1",
            },
            claims=[
                Claim("gain_negative", "a_v", within=0.001),
                Claim("e_at_plus_1", 0, within=1e-3, absolute=True, unit="V",
                      note="the other half: the upper diode is off and E_O rests "
                      "on the virtual ground through R_O"),
            ],
            units={"e_at_minus_1": "V"},
        ),
        Run(
            "half_wave",
            Transient(stop="3m", step="1u"),
            drive={"e_in": "SIN(0 1 1k)"},
            measure={
                "e_peak": "max v({e_out.1}) from=1m to=3m",
                "e_off": "find v({e_out.1}) at=2.25m",
                "e_glitch": "min v({e_out.1}) from=1m to=3m",
            },
            claims=[
                Claim("e_peak", 5, within=0.002, unit="V",
                      note="-5 times the -1 V peak of E_I"),
                Claim("e_off", 0, within=1e-3, absolute=True, unit="V",
                      note="at the positive peak of E_I: E_O stays at zero, "
                      "without a diode drop"),
            ],
            units={"e_glitch": "V"},
            note=(
                "E_I is a 1 V peak, 1 kHz sine; the last two cycles are measured. "
                "The one excursion below zero is a spike of a few microseconds as "
                "E_I crosses zero going positive, while the op amp output swings "
                "across the two diode drops and the upper diode recovers. It is "
                "reported, not claimed."
            ),
        ),
    ],
)
