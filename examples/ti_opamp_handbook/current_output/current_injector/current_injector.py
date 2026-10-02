"""The current injector, SBOA092B page 80: a Howland current source.

    I = -E_I / R_L = -E_I mA,    R1 / R2 = R0 / R3

E_I drives R1 into the - input and R0 closes the loop from the output; the
output also drives R3 onto the + input, where R2 returns to ground and the
load R_L takes the rest to ground. With the + input at V_P, the - input's
node gives the output as V_P - R0 (E_I - V_P) / R1, and the current R3
delivers into the + node, less what R2 takes, is

    I = -R0 E_I / (R1 R3) + V_P (R0 / (R1 R3) - 1 / R2)

The ratio condition R1 / R2 = R0 / R3 makes the bracket zero, so

    I = -R0 E_I / (R1 R3) = -E_I / R2

which does not depend on V_P, and so does not depend on R_L: that is what
makes it a current source. The page prints -E_I / R_L, which would make the
current depend on the one thing a current source is built not to depend on.
With every resistor 1 kOhm, R2, R3 and the printed R_L-free value all give
-1 mA per volt, so the number the page prints is right and its formula is
not.

The load is the thing driven, and the program makes it a `Load` a run can
change, then moves it across a decade and a half to show the current stays.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Parameter, System, UnitLiteral, kOhm, require
from fang.parts import Resistor, TwoPin
from fang.rationale import Chooses, Cites
from fang.simulation import OperatingPoint

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
)

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


class CurrentInjector(System):
    """A difference amplifier whose + input node is the output, into a grounded load."""

    figure = Cites(
        "I = -E_I / R_L = -E_I mA; R1 / R2 = R0 / R3. Single terminal current "
        "available to ground. Observe common mode voltage limit.",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 80, Current Injector",
    )

    load = Chooses(
        "What is R_L?",
        selected="1 kOhm by default, and 100 Ohm and 4.7 kOhm in the runs",
        alternatives=[
            {
                "option": "one fixed load",
                "reason": "the claim is that the current does not depend on R_L, "
                "which one value cannot show",
            },
            {
                "option": "10 kOhm",
                "reason": "at 1 mA the + input would sit at -10 V and the output "
                "at -21 V, past the swing: the common-mode limit the page warns of",
            },
        ],
        rationale=(
            "the figure draws R_L between two terminals with no value",
            "at 4.7 kOhm the + input is at -4.7 V and the output at -10.4 V, "
            "inside the swing",
        ),
    )

    i_per_volt = Parameter(
        "mA/V", default=-1 * mA_per_V, description="I / E_I: -R0 / (R1 R3), or -1 / R2"
    )

    e_in = Terminal()
    r1 = Resistor(resistance=1 * kOhm)
    r0 = Resistor(resistance=1 * kOhm)
    r2 = Resistor(resistance=1 * kOhm)
    r3 = Resistor(resistance=1 * kOhm)
    r_load = Load(resistance=1 * kOhm)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.r1.p1
        self.r1.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r0.p1
        self.r0.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.r3.p1
        self.r3.p2 >> self.amp.non_inverting.signal
        self.amp.non_inverting.signal >> self.r2.p1
        self.r2.p2 >> self.ground.node
        self.amp.non_inverting.signal >> self.r_load.p1
        self.r_load.p2 >> self.ground.node

    def constraints(self):
        # The page's own condition, which is what makes the current independent
        # of the load.
        require(
            equals(
                over(self.r1.resistance, self.r2.resistance),
                over(self.r0.resistance, self.r3.resistance),
            )
        )
        require(
            equals(
                self.i_per_volt,
                negative(
                    over(self.r0.resistance, product(self.r1.resistance, self.r3.resistance))
                ),
            )
        )


ERRATUM = (
    "The page prints I = -E_I / R_L. For the drawn circuit with R1/R2 = R0/R3 "
    "it is -R0 E_I / (R1 R3), or -E_I / R2, whatever R_L is; with 1 kOhm "
    "throughout both are the -E_I mA the page prints."
)


def _load(resistance: float, note: str = "") -> Run:
    """One operating point with the load set to a resistance."""
    return Run(
        f"load_{resistance:g}_ohm",
        OperatingPoint(),
        drive={"e_in": "DC 1"},
        settings={"r_load": {"resistance": resistance}},
        measure={
            "i_per_volt": "i(vrl1_sense) / v({e_in.1})",
            "common_mode": "v({amp.IN+})",
            "e_out": "v({amp.OUT})",
        },
        claims=[Claim("i_per_volt", "i_per_volt", within=0.001, unit="A/V", note=note)],
        units={"common_mode": "V", "e_out": "V"},
    )


BENCH = Bench(
    page=80,
    title="Current Injector",
    runs=[_load(100), _load(1000, note=ERRATUM), _load(4700)],
)
