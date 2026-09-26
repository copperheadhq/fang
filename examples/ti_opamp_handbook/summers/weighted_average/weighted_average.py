"""The weighted average, SBOA092B page 66.

    E_O = -(R_O + R_O')(E1/R1 + E2/R2 + E3/R3),   R_O + R_O' = R1 || R2 || R3

A summer whose feedback is 5.1 kOhm in series with a 1 kOhm pot wired as a
rheostat, its wiper tied to the output end. The page's rule sets the pot:
with E1 = E2 = E3, E_O should be the same size as E_I, which asks that the
three weights add to 1, and they do when the feedback equals R1 || R2 || R3.
For 10, 20 and 30 kOhm that is 5.4545 kOhm, so the pot supplies 354.5 Ohm,
a setting of 0.3545 of its travel. `setting` records that as a decision:
the figure draws the pot and leaves where to turn it to the rule.

The weights are then 5.4545 kOhm over each input resistor, 0.5455, 0.2727
and 0.1818, which the page writes over 30 as 16.4, 8.2 and 5.4. The first two
are the exact 16.36 and 8.18 rounded; the third is 5.45 cut short (it rounds
to 5.5), and the three printed numbers add to 30 only because of it. The
program holds the weights the parts give, and the bench measures them.

The page also asks that E_O = E_I when the inputs are equal. The circuit
inverts, as its own E_O formula says, so what the rule gives is E_O = -E_I.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from decimal import Decimal

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
    negative,
    over,
    parallel,
    product,
    ratio,
    total,
    within,
)


class WeightedAverage(System):
    """E1, E2, E3 through 10, 20 and 30 kOhm; 5.1 kOhm and a 1 kOhm rheostat back."""

    figure = Cites(
        "For E1 = E2 = E3, set R_O' so E_O = E_I. Then, R_O + R_O' = R1 || R2 || R3. "
        "E_O = -(R_O + R_O')E1/R1 - (R_O + R_O')E2/R2 - (R_O + R_O')E3/R3 = "
        "-(16.4 E1 + 8.2 E2 + 5.4 E3)/30",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 66, Weighted Average",
    )

    setting = Chooses(
        "Where is R_O' set?",
        selected="0.3545 of its 1 kOhm travel, 354.5 Ohm, so R_O + R_O' = R1 || R2 || R3",
        alternatives=[
            {
                "option": "the pot at its midpoint, 500 Ohm",
                "reason": "5.6 kOhm of feedback makes the weights add to 1.027, and "
                "equal inputs come out 2.7% large",
            },
            {
                "option": "the pot's full 1 kOhm",
                "reason": "6.1 kOhm of feedback makes the weights add to 1.118",
            },
        ],
        rationale=(
            "the figure draws the pot and gives the rule that sets it, not a setting",
            "R1 || R2 || R3 is 5.4545 kOhm, and 5.1 kOhm leaves 354.5 Ohm for the pot",
        ),
    )

    a_1 = Parameter("1", default=Decimal("-0.545455") * ratio, description="-(R_O + R_O')/R1")
    a_2 = Parameter("1", default=Decimal("-0.272727") * ratio, description="-(R_O + R_O')/R2")
    a_3 = Parameter("1", default=Decimal("-0.181818") * ratio, description="-(R_O + R_O')/R3")
    a_equal = Parameter(
        "1", default=-1 * ratio, description="E_O / E_I with all three inputs at E_I"
    )

    e1 = Terminal()
    e2 = Terminal()
    e3 = Terminal()
    common = Terminal()
    e_out = Terminal()

    r_1 = Resistor(resistance=10 * kOhm)
    r_2 = Resistor(resistance=20 * kOhm)
    r_3 = Resistor(resistance=30 * kOhm)
    r_out = Resistor(resistance=Decimal("5.1") * kOhm)
    trim = Potentiometer(resistance=1 * kOhm, setting=Decimal("0.354545") * ratio)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e1.probe >> self.r_1.p1
        self.e2.probe >> self.r_2.p1
        self.e3.probe >> self.r_3.p1
        self.r_1.p2 >> self.amp.inverting.signal
        self.r_2.p2 >> self.amp.inverting.signal
        self.r_3.p2 >> self.amp.inverting.signal

        # R_O, then the pot as a rheostat: its wiper tied to its far end.
        self.amp.inverting.signal >> self.r_out.p1
        self.r_out.p2 >> self.trim.end_a
        self.trim.wiper >> self.trim.end_b
        self.trim.end_b >> self.amp.output.signal

        self.amp.output.signal >> self.e_out.probe
        self.amp.non_inverting.signal >> self.ground.node
        self.common.probe >> self.ground.node

    def constraints(self):
        # The pot contributes the part of its travel between pin 1 and the wiper.
        feedback = total(self.r_out.resistance, product(self.trim.resistance, self.trim.setting))
        inputs = (self.r_1.resistance, self.r_2.resistance, self.r_3.resistance)

        # The page's rule for setting R_O'.
        require(within(feedback, parallel(parallel(inputs[0], inputs[1]), inputs[2]), 0.00001))

        # `within` takes its band as a fraction of the target, so the weights
        # are compared as magnitudes: a negative target would turn the band over.
        for weight, r_n in zip((self.a_1, self.a_2, self.a_3), inputs):
            require(within(negative(weight), over(feedback, r_n), 0.00001))
        require(
            within(
                negative(self.a_equal),
                negative(total(self.a_1, self.a_2, self.a_3)),
                0.00001,
            )
        )


def _alone(n: int, printed: str) -> Run:
    drive = {f"e{k}": ("DC 1" if k == n else "DC 0") for k in range(1, 4)}
    return Run(
        f"e{n}_alone",
        OperatingPoint(),
        drive=drive,
        measure={f"weight_e{n}": f"v({{e_out.1}}) / v({{e{n}.1}})"},
        claims=[Claim(f"weight_e{n}", f"a_{n}", within=0.001, note=printed)],
    )


BENCH = Bench(
    page=66,
    title="Weighted Average",
    runs=[
        _alone(1, "The handbook prints 16.4/30 = 0.5467; 5.4545k/10k is 0.5455 (16.36/30)."),
        _alone(2, "The handbook prints 8.2/30 = 0.2733; 5.4545k/20k is 0.2727 (8.18/30)."),
        _alone(3, (
            "The handbook prints 5.4/30 = 0.18; 5.4545k/30k is 0.1818 (5.45/30, "
            "which rounds to 5.5, not 5.4)."
        )),
        Run(
            "equal_inputs",
            OperatingPoint(),
            drive={"e1": "DC 1", "e2": "DC 1", "e3": "DC 1"},
            measure={"gain": "v({e_out.1}) / v({e1.1})"},
            claims=[
                Claim("gain", "a_equal", within=0.001,
                      note=(
                          "The rule the pot is set by. The handbook asks for "
                          "E_O = E_I; the circuit inverts, so it is E_O = -E_I."
                      )),
            ],
        ),
        Run(
            "weighted",
            OperatingPoint(),
            drive={"e1": "DC 3", "e2": "DC -1.5", "e3": "DC 1.2"},
            measure={"e_o": "v({e_out.1})"},
            claims=[
                Claim("e_o", -1.4455, within=0.001, unit="V",
                      note="-(0.54545 x 3 + 0.27273 x (-1.5) + 0.18182 x 1.2) = -1.4455 V"),
            ],
        ),
    ],
)
