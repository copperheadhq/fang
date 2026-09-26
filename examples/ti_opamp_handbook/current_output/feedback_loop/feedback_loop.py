"""The feedback-loop current source, SBOA092B page 79.

    I = E_I / R_1 = E_I mA,    Z_in = R_1 = 1 kOhm

The load sits where the feedback resistor of an inverting amplifier would, so
the current through R_1 is the current through the load, whatever the load
is. The figure draws R_L between two terminals and gives it no value: it is
the thing being driven, not part of the circuit. The program makes it a
`Load` whose resistance a run can set, because a claim that the current does
not depend on R_L means nothing until R_L has been moved.

The bench drives E_I with 1 V and reads the load current for 100 Ohm, 1 kOhm
and 10 kOhm, then asks for 20 kOhm, which needs -20 V at the output: the op
amp stops at -13.5 V and the current falls short, which is where the claim
ends.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Parameter, System, UnitLiteral, kOhm, require
from fang.parts import Resistor, TwoPin
from fang.rationale import Chooses, Cites
from fang.simulation import OperatingPoint

from handbook import Bench, Claim, Ground, OpAmp, Run, Terminal, equals, over, ratio

#: A transconductance: the current out per volt in.
mA_per_V = UnitLiteral("mA/V")


class Load(TwoPin):
    """What the current is delivered into: a resistance a run may change.

    SPICE knows a resistor, but the bench only rewrites a part it writes
    itself, so the load writes its own card, and a zero-volt source after it
    so a measurement reads the load current as `i(v<ref>_sense)`.
    """

    designator_prefix = "RL"
    resistance = Parameter("Ohm")

    def spice(self, ref, node, value):
        return (
            [
                f"R{ref} {node('1')} sense_{ref} {value('resistance'):.6g}",
                f"V{ref}_SENSE sense_{ref} {node('2')} DC 0",
            ],
            {},
        )

    def describe(self, value) -> str:
        return f"load of {value('resistance'):.6g} Ohm, with its current sensed"


class FeedbackLoop(System):
    """E_I through R_1 into the summing point, the load from there to the output."""

    figure = Cites(
        "I = E_I / R_I = E_I mA; Z_in = R_I = 1 kOhm",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 79, Feedback Loop",
    )

    load = Chooses(
        "What is R_L?",
        selected="1 kOhm by default, and 100 Ohm, 10 kOhm and 20 kOhm in the runs",
        alternatives=[
            {
                "option": "one fixed load",
                "reason": "the claim is that the current does not depend on R_L, "
                "which one value cannot show",
            },
        ],
        rationale=(
            "the figure draws R_L between two terminals with no value: it is "
            "the thing driven, not part of the source",
            "10 kOhm at 1 mA puts the output at -10 V, inside the swing; 20 kOhm "
            "asks for -20 V and shows where the claim stops",
        ),
    )

    i_per_volt = Parameter("A/V", default=1 * mA_per_V, description="I / E_I")
    z_in = Parameter("Ohm", default=1 * kOhm, description="what E_I sees")

    e_in = Terminal()
    e_out = Terminal()
    r1 = Resistor(resistance=1 * kOhm)
    r_load = Load(resistance=1 * kOhm)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.r1.p1
        self.r1.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r_load.p1
        self.r_load.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe
        self.amp.non_inverting.signal >> self.ground.node

    def constraints(self):
        require(equals(self.i_per_volt, over(1 * ratio, self.r1.resistance)))
        require(equals(self.z_in, self.r1.resistance))


def _load(resistance: float) -> Run:
    """One operating point with the load set to a resistance."""
    return Run(
        f"load_{resistance:g}_ohm",
        OperatingPoint(),
        drive={"e_in": "DC 1"},
        settings={"r_load": {"resistance": resistance}},
        measure={
            "i_per_volt": "i(vrl1_sense) / v({e_in.1})",
            "z_in": "v({e_in.1}) / (-i(vdrive_e_in))",
            "e_out": "v({e_out.1})",
        },
        claims=[
            Claim("i_per_volt", "i_per_volt", within=0.001, unit="A/V"),
            Claim("z_in", "z_in", within=0.001, unit="Ohm"),
        ],
        units={"e_out": "V"},
    )


BENCH = Bench(
    page=79,
    title="Feedback Loop",
    runs=[
        _load(100),
        _load(1000),
        _load(10000),
        Run(
            "load_20000_ohm",
            OperatingPoint(),
            drive={"e_in": "DC 1"},
            settings={"r_load": {"resistance": 20000}},
            measure={
                "i_per_volt": "i(vrl1_sense) / v({e_in.1})",
                "e_out": "v({e_out.1})",
            },
            claims=[
                Claim(
                    "e_out", -13.5, within=0.01, unit="V",
                    note="20 kOhm at 1 mA needs -20 V; the output stops at the "
                    "-13.5 V swing, and the current falls to 14.5 V / 21 kOhm",
                ),
            ],
            units={"i_per_volt": "A/V"},
            note="Past the swing: the claim I = E_I / R_1 holds only while "
            "E_I R_L / R_1 fits inside the output swing.",
        ),
    ],
)
