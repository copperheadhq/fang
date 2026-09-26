"""Common mode rejection by inverting and summing, SBOA092B page 75.

    E_O = -(R_O / R1)(E1 - E2) = 10 (E2 - E1),    R2 + R3 = R1

Two op amps. The bottom one inverts E2 (R4 in, R5 across, both 10 kOhm). The
top one is a summing amplifier: E1 reaches its inverting input through R1,
the inverted E2 reaches the same point through R2 (9.1 kOhm) in series with
R3, a 5 kOhm potentiometer wired as a rheostat, and R0 (100 kOhm) is the
feedback. Its output is

    E_O = -(R0/R1) E1 + (R0/(R2 + R3))(R5/R4) E2

which is zero for E1 = E2 when R2 + R3 = R1 (R5/R4) = R1. R3 is the page's
"common mode adjustment".

As drawn the page cannot be right. R1 is 1 kOhm, so the gain would be
R0/R1 = 100, not the printed 10, and R2 + R3 runs from 9.1 to 14.1 kOhm, so it
can never equal R1: the E2 path is worth at most 100/9.1 = 11 against E1's
100, and the trim cannot null anything. One value fixes both printed
equations at once: R1 = 10 kOhm. Then R0/R1 is 10, as printed, and
R2 + R3 = R1 with R3 at 0.9 kOhm, inside the pot's range. `reading` records
that, and the program is built on it; the figure's "1 kOhm" for R1 is the
erratum. `trim` records where the rheostat is set.
"""

import sys
from decimal import Decimal
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Parameter, System, kOhm, require
from fang.parts import Resistor
from fang.rationale import Chooses, Cites
from fang.simulation import OperatingPoint

from handbook import (
    Bench,
    Claim,
    Ground,
    OpAmp,
    Potentiometer,
    Run,
    Terminal,
    at_least,
    at_most,
    equals,
    minus,
    negative,
    over,
    product,
    ratio,
    total,
)


class CommonModeRejection(System):
    """An inverter on E2, summed with E1 into one inverting amplifier."""

    figure = Cites(
        "E_O = -(R_O/R_1)(E1 - E2) = 10(E2 - E1); R2 + R3 = R1. "
        "R3 - common mode adjustment. Set for zero output when E1 = E2. "
        "(R1 drawn as 1 kOhm, R0 100 kOhm, R2 9.1 kOhm, R3 5 kOhm, R4 and R5 10 kOhm)",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 75, Common Mode Rejection",
    )

    reading = Chooses(
        "Which of the figure's values is misprinted?",
        selected=(
            "R1: it is 10 kOhm, not the 1 kOhm drawn. Then R0/R1 = 10 as printed, "
            "and R2 + R3 = R1 at R3 = 0.9 kOhm, inside the 5 kOhm pot"
        ),
        alternatives=[
            {
                "option": "R1 = 1 kOhm, as drawn",
                "reason": (
                    "the gain is then 100, not the printed 10, and R2 + R3 is at "
                    "least 9.1 kOhm, so it can never equal R1: the E2 path is "
                    "worth at most 11 against E1's 100, and no trim nulls E1 = E2"
                ),
            },
            {
                "option": "R0 = 10 kOhm, with R1 = 1 kOhm",
                "reason": (
                    "gives the printed gain of 10 but leaves R2 + R3 = R1 = 1 kOhm "
                    "out of the pot's reach, so it fixes one printed equation of two"
                ),
            },
            {
                "option": "R2 = 910 Ohm and R3 = 500 Ohm, with R1 = 1 kOhm",
                "reason": (
                    "makes the trim reachable but leaves the gain at 100, and "
                    "needs two values misprinted where the chosen reading needs one"
                ),
            },
        ],
        rationale=(
            "the page prints two equations, a gain of 10 and R2 + R3 = R1, and "
            "the drawn values satisfy neither",
            "R1 = 10 kOhm is the one change that satisfies both, and matches R4 "
            "and R5 beside it",
        ),
    )

    trim = Chooses(
        "Where is the R3 rheostat set?",
        selected=(
            "0.82 of its travel from the summing-point end, which leaves 0.9 kOhm "
            "in circuit and makes R2 + R3 = R1"
        ),
        alternatives=[
            {
                "option": "mid-travel",
                "reason": (
                    "2.5 kOhm in circuit makes R2 + R3 = 11.6 kOhm and leaves 1.38 V "
                    "out for 1 V on both inputs; the bench shows it, untrimmed"
                ),
            },
        ],
        rationale=(
            "the page says to set R3 for zero output when E1 = E2",
            "the wiper is tied to the end at the summing point, so the part left "
            "in circuit is the travel from the wiper to R2",
        ),
    )

    a_e1 = Parameter("1", default=-10 * ratio, description="E_O / E1, with E2 at ground")
    a_e2 = Parameter("1", default=10 * ratio, description="E_O / E2, with E1 at ground")
    a_inv = Parameter("1", default=-1 * ratio, description="the bottom amplifier's gain")

    e1 = Terminal()
    e2 = Terminal()
    common = Terminal()
    e_out = Terminal()

    r1 = Resistor(resistance=10 * kOhm)
    r0 = Resistor(resistance=100 * kOhm)
    r2 = Resistor(resistance=Decimal("9.1") * kOhm)
    r3 = Potentiometer(resistance=5 * kOhm, setting=Decimal("0.82") * ratio)
    r4 = Resistor(resistance=10 * kOhm)
    r5 = Resistor(resistance=10 * kOhm)
    amp_sum = OpAmp()
    amp_invert = OpAmp()
    ground = Ground()

    def architecture(self):
        # The top amplifier: E1 through R1 into the summing point, R0 back.
        self.e1.probe >> self.r1.p1
        self.r1.p2 >> self.amp_sum.inverting.signal
        self.amp_sum.inverting.signal >> self.r0.p1
        self.r0.p2 >> self.amp_sum.output.signal
        self.amp_sum.output.signal >> self.e_out.probe

        # The bottom amplifier: E2 inverted by R4 and R5.
        self.e2.probe >> self.r4.p1
        self.r4.p2 >> self.amp_invert.inverting.signal
        self.amp_invert.inverting.signal >> self.r5.p1
        self.r5.p2 >> self.amp_invert.output.signal

        # The inverted E2 back to the summing point through R2 and the R3
        # rheostat, whose wiper is tied to its summing-point end.
        self.amp_invert.output.signal >> self.r2.p1
        self.r2.p2 >> self.r3.end_b
        self.r3.end_a >> self.amp_sum.inverting.signal
        self.r3.wiper >> self.amp_sum.inverting.signal

        # Both + inputs, and the terminal at the bottom left, on ground.
        self.amp_sum.non_inverting.signal >> self.ground.node
        self.amp_invert.non_inverting.signal >> self.ground.node
        self.common.probe >> self.ground.node

    def constraints(self):
        # What is left of R3 in circuit: the travel from the wiper to R2.
        r3_in_circuit = product(self.r3.resistance, minus(1 * ratio, self.r3.setting))
        e2_path = total(self.r2.resistance, r3_in_circuit)

        require(equals(self.a_inv, negative(over(self.r5.resistance, self.r4.resistance))))
        require(equals(self.a_e1, negative(over(self.r0.resistance, self.r1.resistance))))
        require(
            equals(
                self.a_e2,
                product(over(self.r0.resistance, e2_path), negative(self.a_inv)),
            )
        )

        # The page's trim rule, R2 + R3 = R1, with the inverter's gain written
        # in (it is 1 here); and that the pot can reach it at all, which is
        # what the drawn R1 of 1 kOhm fails.
        require(equals(e2_path, product(self.r1.resistance, negative(self.a_inv))))
        require(at_most(self.r2.resistance, self.r1.resistance))
        require(at_least(total(self.r2.resistance, self.r3.resistance), self.r1.resistance))

        # Common-mode rejection: the two paths are equal and opposite.
        require(equals(self.a_e2, negative(self.a_e1)))


ERRATUM = (
    "on the reading that R1 is 10 kOhm; the figure's 1 kOhm would give "
    "a gain of 100 and no reachable null"
)

BENCH = Bench(
    page=75,
    title="Common Mode Rejection",
    runs=[
        Run(
            "e1_alone",
            OperatingPoint(),
            drive={"e1": "DC 1", "e2": "DC 0"},
            measure={"gain_e1": "v({e_out.1}) / v({e1.1})"},
            claims=[Claim("gain_e1", "a_e1", within=0.001, note=ERRATUM)],
        ),
        Run(
            "e2_alone",
            OperatingPoint(),
            drive={"e1": "DC 0", "e2": "DC 1"},
            measure={
                "gain_e2": "v({e_out.1}) / v({e2.1})",
                "inverted": "v({amp_invert.OUT}) / v({e2.1})",
            },
            claims=[
                Claim("gain_e2", "a_e2", within=0.001,
                      note="R0 / (R2 + 0.9 kOhm of R3), through the inverter"),
                Claim("inverted", "a_inv", within=0.001),
            ],
        ),
        Run(
            "difference",
            OperatingPoint(),
            drive={"e1": "DC 0.4", "e2": "DC 0.6"},
            measure={"e_o": "v({e_out.1})"},
            claims=[Claim("e_o", 2.0, within=0.001, unit="V",
                          note="10 (E2 - E1) = 10 x 0.2 V, as printed")],
        ),
        Run(
            "common_mode_trimmed",
            OperatingPoint(),
            drive={"e1": "DC 1", "e2": "DC 1"},
            measure={"e_o": "v({e_out.1})"},
            claims=[
                Claim(
                    "e_o", 0, within=1e-4, absolute=True, unit="V",
                    note=(
                        "1 V on both inputs with R3 trimmed so R2 + R3 = R1. What "
                        "is left is the two op amps' finite gain"
                    ),
                )
            ],
        ),
        Run(
            "common_mode_untrimmed",
            OperatingPoint(),
            drive={"e1": "DC 1", "e2": "DC 1"},
            settings={"r3": {"setting": 0.5}},
            measure={"e_o": "v({e_out.1})"},
            claims=[
                Claim(
                    "e_o", -10 + 100 / 11.6, within=0.001, unit="V",
                    note=(
                        "R3 at mid-travel: R2 + R3 = 11.6 kOhm, so E_O = "
                        "-10 + 100/11.6 = -1.379 V for 1 V on both inputs. "
                        "This is what the trim is for"
                    ),
                )
            ],
        ),
    ],
)
