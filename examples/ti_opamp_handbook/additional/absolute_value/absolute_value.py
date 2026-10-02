"""The absolute value circuit, SBOA092B page 87.

    +E_I follower circuit
    -E_I inverter circuit
    E_O = |E_I|

Two equal resistors make the op amp an inverter of E_I, and two diodes
decide what the + input sees. The stage's output is 2 V+ - E_I: with the
+ input at E_I it is E_I (the "follower"), with the + input at ground it is
-E_I (the "inverter"). The diodes both have their cathodes on the + input,
one with its anode on E_I and the other on ground, so the + input takes
whichever of E_I and 0 is higher: E_I when it is positive, 0 when it is
negative. The output is |E_I|.

The figure as printed does not wire it that way. It lands the source, the
two cathodes and the - input on one node and the + input on ground, which
leaves the left resistor and the upper diode in a closed loop of their own
and holds the - input at E_I with nothing for the output to control.
`reading` records the circuit simulated here: the diodes and resistors the
figure draws, with their orientations, with the source on the upper diode's
anode and the left resistor, and the cathodes' node on the + input.

Neither diode carries more than the other's leakage, because the + input
draws nothing, so the error is not a full forward drop. It is the drop at a
few nanoamps, about 30 mV, and the output carries it twice. It is not a
precision circuit: the diodes are outside the loop, and a real op amp's
input bias current, which the model here does not have, would move the
+ input by more than that.
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
    minus,
    negative,
    over,
    ratio,
    total,
)


class AbsoluteValue(System):
    """E_I through R into the summing point, R back; the + input picks E_I or ground through two diodes."""

    figure = Cites(
        "+E_I follower circuit, -E_I inverter circuit, E_O = |E_I|; full wave "
        "rectification. Reverse diodes to give E_O = -|E_I|",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 87, Absolute Value",
    )

    reading = Chooses(
        "The figure puts E_I, both cathodes and the - input on one node. How is it wired?",
        selected=(
            "E_I on the upper diode's anode and the left R; both cathodes on the "
            "+ input; the lower diode's anode on ground; the - input between the two Rs"
        ),
        alternatives=[
            {
                "reading": "as printed",
                "reason": (
                    "the left R and the upper diode close on themselves, the - input "
                    "is held at E_I by the source and the + input at ground, and the "
                    "output has nothing to control; it saturates"
                ),
            },
            {
                "reading": "as printed, less the wire from E_I to the - input",
                "reason": (
                    "the upper diode then passes only negative E_I into the inverter "
                    "and the lower diode shorts the source there: a half-wave "
                    "rectifier, not |E_I|"
                ),
            },
        ],
        rationale=(
            "it keeps every part the figure draws, and the orientation of both diodes",
            "it is a follower for +E_I and an inverter for -E_I, as the page says",
            "reversing both diodes makes the + input take the lower of E_I and 0, "
            "which gives -|E_I|, the page's last sentence",
        ),
    )

    a_follow = Parameter("1", default=1 * ratio, description="E_O / E_I for positive E_I, 2 - R/R")
    a_invert = Parameter("1", default=-1 * ratio, description="E_O / E_I for negative E_I, -R/R")

    e_in = Terminal()
    e_out = Terminal()
    r_in = Resistor(resistance=10 * kOhm)
    r_out = Resistor(resistance=10 * kOhm)
    d_in = SignalDiode()
    d_ground = SignalDiode()
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.r_in.p1
        self.e_in.probe >> self.d_in.p1
        self.d_in.p2 >> self.amp.non_inverting.signal
        self.d_ground.p2 >> self.amp.non_inverting.signal
        self.d_ground.p1 >> self.ground.node
        self.r_in.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r_out.p1
        self.r_out.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe

    def constraints(self):
        gain = over(self.r_out.resistance, self.r_in.resistance)
        # + input at E_I: E_I (1 + R/R) - E_I (R/R).
        require(equals(self.a_follow, minus(total(1 * ratio, gain), gain)))
        # + input at ground: the inverting amplifier.
        require(equals(self.a_invert, negative(gain)))


BENCH = Bench(
    page=87,
    title="Absolute Value",
    runs=[
        Run(
            "transfer",
            DCSweep(source="VDRIVE_e_in", start="-6", stop="6", step="0.01"),
            drive={"e_in": "DC 0"},
            measure={
                "out_n5": "find v({e_out.1}) at=-5",
                "out_n1": "find v({e_out.1}) at=-1",
                "out_0": "find v({e_out.1}) at=0",
                "out_p1": "find v({e_out.1}) at=1",
                "out_p5": "find v({e_out.1}) at=5",
                "vplus_p5": "find v({amp.IN+}) at=5",
                "gain_p5": "out_p5 / 5",
                "gain_n5": "out_n5 / -5",
                "vplus_n5": "find v({amp.IN+}) at=-5",
            },
            claims=[
                Claim("out_n5", 5, within=0.1, absolute=True, unit="V", note="-5 V in, inverted"),
                Claim("out_n1", 1, within=0.1, absolute=True, unit="V"),
                Claim("out_0", 0, within=0.1, absolute=True, unit="V"),
                Claim("out_p1", 1, within=0.1, absolute=True, unit="V"),
                Claim(
                    "out_p5",
                    5,
                    within=0.1,
                    absolute=True,
                    unit="V",
                    note="+5 V in, followed. Each point is held to 0.1 V, not 0.1%: see the run's note",
                ),
                Claim(
                    "gain_p5",
                    "a_follow",
                    within=0.02,
                    note="E_O / E_I at +5 V: the follower, 1.3% low for the 63 mV",
                ),
                Claim("gain_n5", "a_invert", within=0.02, note="E_O / E_I at -5 V: the inverter"),
            ],
            units={"vplus_p5": "V", "vplus_n5": "V"},
            note=(
                "E_I swept from -5 V to +5 V. The output is |E_I| less about "
                "60 mV: each diode sits at the drop it has at its partner's "
                "leakage, and the output is 2 V+ - E_I, so the error appears "
                "twice."
            ),
        ),
        Run(
            "sine",
            Transient(stop="30m", step="10u"),
            drive={"e_in": "SIN(0 2 100)"},
            measure={
                "peak_pos": "max v({e_out.1}) from=0 to=5m",
                "peak_neg": "max v({e_out.1}) from=5m to=10m",
                "lowest": "min v({e_out.1}) from=0 to=30m",
            },
            claims=[
                Claim("peak_pos", 2, within=0.1, absolute=True, unit="V", note="the positive half, followed"),
                Claim("peak_neg", 2, within=0.1, absolute=True, unit="V", note="the negative half, inverted: full wave"),
            ],
            units={"lowest": "V"},
            note=(
                "A 2 V, 100 Hz sine: both halves come out positive, each peaking "
                "near 2 V. The + input is a node that only leakage drives, so it "
                "lags a fast signal: at 1 kHz the same peaks come out near 1.89 V."
            ),
        ),
    ],
)
