"""The peak follower, SBOA092B page 87.

    E_O = E_I maximum

E_I charges a 1 uF capacitor through a diode, and a voltage follower reads
the capacitor without loading it. The diode lets the capacitor charge up to
the highest E_I it has seen and stops it discharging when E_I falls, so the
capacitor, and the output, remember the peak. A switch across the capacitor
clears it.

The page says the output is E_I's maximum. It is one diode drop below it: the
diode is outside the loop, and its forward voltage at the current that last
charged the capacitor is subtracted from the peak and never given back. That
drop is not a fixed number. It is the voltage at which the diode's current
has fallen to what the capacitor still asks for, so a slow input leaves less
of it than a fast one. The program says so in `drop`, and the bench measures
it for a 1 ms pulse and for a sine.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Parameter, System, V, require, uF
from fang.parts import Capacitor
from fang.rationale import Chooses, Cites
from fang.simulation import Transient

from handbook import (
    Bench,
    Claim,
    Ground,
    OpAmp,
    Run,
    SignalDiode,
    Switch,
    Terminal,
    equals,
    minus,
)


class PeakFollower(System):
    """E_I through a diode onto a capacitor, a follower reading it, a switch to clear it."""

    figure = Cites(
        "Peak value memory. Use low leakage capacitor. E_O = E_I maximum. "
        "Common mode input voltage must be observed",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 87, Peak Follower",
    )

    drop = Chooses(
        "What forward drop does the held value lose to the diode?",
        selected="0.5 V, the 1N4148's drop at the tens of microamps still charging the capacitor when the peak ends, claimed to 0.1 V",
        alternatives=[
            {
                "option": "none, as the page's E_O = E_I maximum says",
                "reason": "the diode is outside the loop; its drop is in the held value, and the bench measures it",
            },
            {
                "option": "0.7 V, the textbook silicon drop",
                "reason": "that is the drop at milliamps; the charging current has died to tens of microamps by the time the peak passes",
            },
        ],
        rationale=(
            "the handbook draws a plain diode and names no part; the bench uses the 1N4148 it names on page 47",
            "the drop depends on how the input approaches its peak, so the claim is a band, not a number",
        ),
    )

    e_peak = Parameter("V", default=4 * V, description="the peak the bench applies")
    v_drop = Parameter("V", default=0.5 * V, description="the diode's forward drop when charging stops")
    e_held = Parameter("V", default=3.5 * V, description="what the output holds: the peak less the drop")

    e_in = Terminal()
    e_out = Terminal()
    diode = SignalDiode()
    c_hold = Capacitor(capacitance=1 * uF)
    reset = Switch()
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.diode.p1
        self.diode.p2 >> self.c_hold.p1
        self.c_hold.p1 >> self.reset.p1
        self.c_hold.p1 >> self.amp.non_inverting.signal
        self.c_hold.p2 >> self.ground.node
        self.reset.p2 >> self.ground.node
        self.amp.inverting.signal >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe

    def constraints(self):
        require(equals(self.e_held, minus(self.e_peak, self.v_drop)))


BENCH = Bench(
    page=87,
    title="Peak Follower",
    runs=[
        Run(
            "pulse",
            Transient(stop="10m", step="1u"),
            drive={"e_in": "PULSE(0 4 1m 1u 1u 1m 20m)"},
            switches={"reset": "PWL(0 0 7m 0 7.001m 1)"},
            measure={
                "held": "find v({e_out.1}) at=5m",
                "held_later": "find v({e_out.1}) at=6.9m",
                "cleared": "find v({e_out.1}) at=9m",
            },
            claims=[
                Claim(
                    "held",
                    "e_held",
                    within=0.1,
                    absolute=True,
                    unit="V",
                    note=(
                        "3 ms after a 4 V, 1 ms pulse: 0.44 V under the peak, the drop "
                        "at the 45 uA the capacitor still took when the pulse ended. "
                        "The page's E_O = E_I maximum would be 4 V"
                    ),
                ),
                Claim(
                    "held_later",
                    "e_held",
                    within=0.1,
                    absolute=True,
                    unit="V",
                    note="still there 1.9 ms later: the model's capacitor does not leak",
                ),
                Claim(
                    "cleared",
                    0,
                    within=0.001,
                    absolute=True,
                    unit="V",
                    note="the reset switch closed at 7 ms",
                ),
            ],
            note=(
                "E_I pulses to 4 V from 1 ms to 2 ms and falls back to 0. The "
                "reset switch closes at 7 ms."
            ),
        ),
        Run(
            "sine",
            Transient(stop="10m", step="1u"),
            drive={"e_in": "SIN(0 4 1k)"},
            measure={
                "held": "find v({e_out.1}) at=9.5m",
                "input_peak": "max v({e_in.1}) from=0 to=10m",
            },
            claims=[
                Claim(
                    "held",
                    "e_held",
                    within=0.1,
                    absolute=True,
                    unit="V",
                    note=(
                        "after ten cycles of a 4 V, 1 kHz sine: 0.48 V under the peak. "
                        "Each cycle tops the capacitor up in a short burst near the "
                        "crest, which leaves a little more drop than the pulse did"
                    ),
                ),
            ],
            units={"input_peak": "V"},
        ),
    ],
)
