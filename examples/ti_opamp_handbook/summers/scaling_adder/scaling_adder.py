"""The scaling adder, SBOA092B page 64.

    E_O = -(R0/R1 E1 + R0/R2 E2 + R0/R3 E3) = -(100 E1 + 10 E2 + E3)

The adder with its input resistors scaled by decades: 1, 10 and 100 kOhm into
the summing point, 100 kOhm back. Each input's weight is R0 over its own
resistor, so E1 counts a hundred times, E2 ten times and E3 once, and each
source sees only its own resistor, 1, 10 or 100 kOhm.

The page prints the result as -100(100 E1 + 10 E2 + E3). The leading 100 is
not in the figure: R0/R1 is 100, not 10 000. The program holds the weights the
resistors give, -100, -10 and -1, and the bench measures them; `figure`
quotes the printed line and the claim notes say where it is off.

The figure gives every value, so nothing was chosen.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Parameter, System, kOhm, require
from fang.parts import Resistor
from fang.rationale import Cites
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
    ratio,
)


class ScalingAdder(System):
    """E1, E2, E3 through 1, 10 and 100 kOhm into the summing point, 100 kOhm back."""

    figure = Cites(
        "E_O = (R0/R1 E1 + R0/R2 E2 + R0/R3 E3) = -100(100 E1 + 10 E2 + E3). "
        "Z_in = 1 kOhm for E1 = 10 kOhm for E2 = 100 kOhm for E3",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 64, Scaling Adder",
    )

    a_1 = Parameter("1", default=-100 * ratio, description="-R0 / R1")
    a_2 = Parameter("1", default=-10 * ratio, description="-R0 / R2")
    a_3 = Parameter("1", default=-1 * ratio, description="-R0 / R3")
    z_1 = Parameter("Ohm", default=1 * kOhm, description="what E1's source sees")
    z_2 = Parameter("Ohm", default=10 * kOhm, description="what E2's source sees")
    z_3 = Parameter("Ohm", default=100 * kOhm, description="what E3's source sees")

    e1 = Terminal()
    e2 = Terminal()
    e3 = Terminal()
    common = Terminal()
    e_out = Terminal()

    r_1 = Resistor(resistance=1 * kOhm)
    r_2 = Resistor(resistance=10 * kOhm)
    r_3 = Resistor(resistance=100 * kOhm)
    r_0 = Resistor(resistance=100 * kOhm)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e1.probe >> self.r_1.p1
        self.e2.probe >> self.r_2.p1
        self.e3.probe >> self.r_3.p1
        self.r_1.p2 >> self.amp.inverting.signal
        self.r_2.p2 >> self.amp.inverting.signal
        self.r_3.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r_0.p1
        self.r_0.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe
        self.amp.non_inverting.signal >> self.ground.node
        self.common.probe >> self.ground.node

    def constraints(self):
        r_0 = self.r_0.resistance
        for weight, impedance, r_n in (
            (self.a_1, self.z_1, self.r_1),
            (self.a_2, self.z_2, self.r_2),
            (self.a_3, self.z_3, self.r_3),
        ):
            require(equals(weight, negative(over(r_0, r_n.resistance))))
            # The summing point is a virtual ground, so a source sees its resistor.
            require(equals(impedance, r_n.resistance))


_ERRATUM = (
    "The handbook prints -100(100 E1 + 10 E2 + E3); R0/R1 is 100, and there is "
    "no further factor of 100 in the figure."
)


def _alone(n: int) -> Run:
    drive = {f"e{k}": ("DC 0.1" if k == n else "DC 0") for k in range(1, 4)}
    return Run(
        f"e{n}_alone",
        OperatingPoint(),
        drive=drive,
        measure={
            f"gain_e{n}": f"v({{e_out.1}}) / v({{e{n}.1}})",
            f"z_in_e{n}": f"-v({{e{n}.1}}) / i(vdrive_e{n})",
        },
        claims=[
            Claim(f"gain_e{n}", f"a_{n}", within=0.001, note=_ERRATUM if n == 1 else ""),
            Claim(f"z_in_e{n}", f"z_{n}", within=0.001, unit="Ohm"),
        ],
    )


BENCH = Bench(
    page=64,
    title="Scaling Adder",
    runs=[
        _alone(1),
        _alone(2),
        _alone(3),
        Run(
            "all_three",
            OperatingPoint(),
            drive={"e1": "DC 0.01", "e2": "DC 0.1", "e3": "DC 1"},
            measure={"e_o": "v({e_out.1})"},
            claims=[
                Claim("e_o", -3, within=0.001, unit="V",
                      note=(
                          "-(100 x 0.01 + 10 x 0.1 + 1) = -3 V. The printed formula "
                          "would ask for -300 V."
                      )),
            ],
        ),
    ],
)
