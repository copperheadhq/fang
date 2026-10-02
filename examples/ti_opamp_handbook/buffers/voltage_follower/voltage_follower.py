"""The voltage follower, SBOA092B page 49.

    E_O = E_I

The output is wired straight back to the inverting input and the signal goes
in at the non-inverting one, so the loop holds the two inputs together and the
output repeats the input. The handbook reaches it by letting the open-loop
gain go to infinity; with a finite gain A the follower gives A / (1 + A),
which for the bench's 120 dB op amp is 1 less a part in 10^6.

There are no resistors and so nothing to choose. The bench drives E_I at 1 V
and at 10 V (a follower's gain is 1 everywhere inside the swing), and sweeps
the frequency to show where the claim stops: a follower's noise gain is 1, so
its bandwidth is the op amp's gain-bandwidth.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Parameter, System, require
from fang.rationale import Cites
from fang.simulation import ACSweep, OperatingPoint

from handbook import Bench, Claim, Ground, OpAmp, Run, Terminal, equals, ratio


class VoltageFollower(System):
    """E_I on the + input, the output wired back to the - input."""

    figure = Cites(
        "E_O = E_I",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 49, The Voltage Follower",
    )

    a_v = Parameter("1", default=1 * ratio, description="E_O / E_I")

    e_in = Terminal()
    e_out = Terminal()
    # The figure's lower pair of terminals, both on the grounded return.
    e_in_return = Terminal()
    e_out_return = Terminal()
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.amp.non_inverting.signal
        self.amp.output.signal >> self.amp.inverting.signal
        self.amp.output.signal >> self.e_out.probe
        # The figure's lower wire: the return both sides share.
        self.e_in_return.probe >> self.ground.node
        self.e_out_return.probe >> self.ground.node

    def constraints(self):
        # No resistor sets the gain: the whole output is fed back, so the
        # fraction returned is 1 and the gain is its reciprocal.
        require(equals(self.a_v, 1 * ratio))


BENCH = Bench(
    page=49,
    title="The Voltage Follower",
    runs=[
        Run(
            "gain",
            OperatingPoint(),
            drive={"e_in": "DC 1"},
            measure={"gain": "v({e_out.1}) / v({e_in.1})"},
            claims=[Claim("gain", "a_v", within=0.001)],
        ),
        Run(
            "large_signal",
            OperatingPoint(),
            drive={"e_in": "DC 10"},
            measure={"gain": "v({e_out.1}) / v({e_in.1})"},
            claims=[Claim("gain", "a_v", within=0.001)],
            note="10 V in, still inside the 13.5 V swing: the gain is the same.",
        ),
        Run(
            "bandwidth",
            ACSweep(points=20, start="10", stop="100meg"),
            drive={"e_in": "DC 0 AC 1"},
            measure={
                "gain_1k": "find vm({e_out.1}) at=1k",
                "f_3db": "when vdb({e_out.1})=-3 fall=1",
            },
            claims=[Claim("gain_1k", "a_v", within=0.001)],
            units={"f_3db": "Hz"},
            note=(
                "The -3 dB point is not a handbook claim: a follower's noise "
                "gain is 1, so it is the op amp's own 10 MHz gain-bandwidth."
            ),
        ),
    ],
)
