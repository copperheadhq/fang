"""Direct addition, SBOA092B page 65.

    E_O = E1 + E2,   Z_in = (3/2) R2 = 15 kOhm for each input,   R_O = 2 R_I

A non-inverting adder. E1 and E2 each reach the + input through a 10 kOhm R2,
and a third 10 kOhm R2 runs from that input to ground, so the + input sits at
the average of E1, E2 and ground, (E1 + E2)/3. R1, 10 kOhm from the - input
to ground, and R0, 20 kOhm from the output back to it, make a non-inverting
gain of 1 + R0/R1 = 3, which undoes the third: E_O = E1 + E2. That is why the
page asks for R_O = 2 R_I.

The input impedance is not the summing point's gift here, because the +
input is not a virtual ground. With the other input at ground, a source sees
its own R2 in series with the other two in parallel: 10k + 5k = 15 kOhm, the
page's (3/2) R2. With the other input driven it is something else, and the
bench shows that too: "for each input" holds only one input at a time.

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
    over,
    parallel,
    product,
    ratio,
    total,
)


class DirectAddition(System):
    """E1, E2 each through R2 onto the + input, a third R2 to ground; gain 1 + R0/R1."""

    figure = Cites(
        "E_O = E1 + E2. Z_in = 3/2 R2 = 15 kOhm for each input. R_O = 2 R_I. "
        "Non-inverting output",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 65, Direct Addition",
    )

    a_v = Parameter("1", default=1 * ratio, description="E_O / E_n, the other input grounded")
    noise_gain = Parameter("1", default=3 * ratio, description="1 + R0 / R1")
    z_in = Parameter(
        "Ohm", default=15 * kOhm, description="R2 + R2 || R2, the other input grounded"
    )

    e1 = Terminal()
    e2 = Terminal()
    common = Terminal()
    e_out = Terminal()

    r_1 = Resistor(resistance=10 * kOhm)
    r_0 = Resistor(resistance=20 * kOhm)
    r_2_e1 = Resistor(resistance=10 * kOhm)
    r_2_e2 = Resistor(resistance=10 * kOhm)
    r_2_ground = Resistor(resistance=10 * kOhm)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        # The gain: R1 from the - input to ground, R0 from the output back.
        self.r_1.p1 >> self.ground.node
        self.r_1.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r_0.p1
        self.r_0.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe

        # The adding: E1 and E2 onto the + input, a third R2 to ground.
        self.e1.probe >> self.r_2_e1.p1
        self.e2.probe >> self.r_2_e2.p1
        self.r_2_e1.p2 >> self.amp.non_inverting.signal
        self.r_2_e2.p2 >> self.amp.non_inverting.signal
        self.amp.non_inverting.signal >> self.r_2_ground.p1
        self.r_2_ground.p2 >> self.ground.node
        self.common.probe >> self.ground.node

    def constraints(self):
        r2_e1, r2_e2 = self.r_2_e1.resistance, self.r_2_e2.resistance
        r2_ground = self.r_2_ground.resistance

        # The page's rule, and the gain it gives.
        require(equals(self.r_0.resistance, product(2 * ratio, self.r_1.resistance)))
        require(
            equals(
                self.noise_gain,
                total(1 * ratio, over(self.r_0.resistance, self.r_1.resistance)),
            )
        )

        # Each input divides against the other two resistors in parallel, and
        # the noise gain multiplies it back up.
        for own, others in ((r2_e1, (r2_e2, r2_ground)), (r2_e2, (r2_e1, r2_ground))):
            below = parallel(*others)
            require(equals(self.a_v, over(product(below, self.noise_gain), total(own, below))))
            require(equals(self.z_in, total(own, below)))


def _alone(n: int) -> Run:
    other = 2 if n == 1 else 1
    return Run(
        f"e{n}_alone",
        OperatingPoint(),
        drive={f"e{n}": "DC 1", f"e{other}": "DC 0"},
        measure={
            f"gain_e{n}": f"v({{e_out.1}}) / v({{e{n}.1}})",
            f"z_in_e{n}": f"-v({{e{n}.1}}) / i(vdrive_e{n})",
        },
        claims=[
            Claim(f"gain_e{n}", "a_v", within=0.001),
            Claim(f"z_in_e{n}", "z_in", within=0.001, unit="Ohm"),
        ],
    )


BENCH = Bench(
    page=65,
    title="Direct Addition",
    runs=[
        _alone(1),
        _alone(2),
        Run(
            "both",
            OperatingPoint(),
            drive={"e1": "DC 1.5", "e2": "DC -0.5"},
            measure={
                "e_o": "v({e_out.1})",
                "e_plus": "v({amp.IN+})",
                "z_in_e1": "-v({e1.1}) / i(vdrive_e1)",
            },
            claims=[
                Claim("e_o", 1.0, within=0.001, unit="V", note="1.5 + (-0.5) = 1 V"),
                Claim("e_plus", 1 / 3, within=0.001, unit="V",
                      note="(E1 + E2)/3: the + input at the average of E1, E2 and ground"),
            ],
            units={"z_in_e1": "Ohm"},
            note=(
                "With E2 driven, E1's source no longer sees 15 kOhm: the + input "
                "sits at 1/3 V, so E1 drives (1.5 - 1/3) V across its 10 kOhm and "
                "sees 1.5 V / 116.7 uA = 12.86 kOhm. The page's 15 kOhm is for one "
                "input at a time."
            ),
        ),
    ],
)
