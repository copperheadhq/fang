"""The balanced output, SBOA092B page 50.

    E_O+ = -(R_O / R_I) E_I = -E_I,   E_O- = -(R_O / R_I) E_O+ = +E_I

Two unity-gain inverters in cascade. The first's output is the terminal the
figure labels E_O+, and it is the inverted one; the second inverts it again
for E_O-. So E_O+ - E_O- = -2 E_I: a load across the two terminals sees twice
the input, and each output only has to swing as far as the input does.

The text says "by using E_O- terminal as the reference, a p-p swing of 4E_I is
obtainable at E_O+". That is true when E_I means the input's peak: a sine of
peak E_I puts E_O+ at -E_I and E_O- at +E_I, so E_O+ measured against E_O-
goes from -2 E_I to +2 E_I, 4 E_I peak to peak. Measured against ground, E_O+
swings only 2 E_I p-p, the same as the input. The page's "usable swing
greater than the power supply voltage rails" follows: with +/-13.5 V of
swing on each output the difference can span 54 V p-p.

The resistors are all given, so there is nothing to choose. The bench checks
the DC gains, then drives a 1 kHz sine at 1 V peak and at 10 V peak; at 10 V
the difference swings 40 V p-p while neither output leaves the rails.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Parameter, System, kOhm, require
from fang.parts import Resistor
from fang.rationale import Cites
from fang.simulation import OperatingPoint, Transient

from handbook import (
    Bench,
    Claim,
    Ground,
    OpAmp,
    Run,
    Terminal,
    equals,
    minus,
    negative,
    over,
    product,
    ratio,
)


class BalancedOutput(System):
    """An inverter of -1 feeding another; E_O+ between them, E_O- after."""

    figure = Cites(
        "By using E_O- terminal at the reference, a p-p swing of 4E_I is "
        "obtainable at E_O+, i.e. a usable swing greater than the power "
        "supply voltage rails.",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 50, Balanced Output",
    )

    a_plus = Parameter("1", default=-1 * ratio, description="E_O+ / E_I")
    a_minus = Parameter("1", default=1 * ratio, description="E_O- / E_I")
    a_diff = Parameter("1", default=-2 * ratio, description="(E_O+ - E_O-) / E_I")
    pp_per_peak = Parameter(
        "1",
        default=4 * ratio,
        description="p-p swing of E_O+ against E_O-, over the input's peak",
    )

    e_in = Terminal()
    e_in_return = Terminal()
    e_out_plus = Terminal()
    e_out_minus = Terminal()
    e_out_return = Terminal()
    r_in_1 = Resistor(resistance=10 * kOhm)
    r_out_1 = Resistor(resistance=10 * kOhm)
    r_in_2 = Resistor(resistance=10 * kOhm)
    r_out_2 = Resistor(resistance=10 * kOhm)
    amp_1 = OpAmp()
    amp_2 = OpAmp()
    ground = Ground()

    def architecture(self):
        # The first inverter; its output is E_O+.
        self.e_in.probe >> self.r_in_1.p1
        self.r_in_1.p2 >> self.amp_1.inverting.signal
        self.amp_1.inverting.signal >> self.r_out_1.p1
        self.r_out_1.p2 >> self.amp_1.output.signal
        self.amp_1.output.signal >> self.e_out_plus.probe
        # The second, fed from E_O+; its output is E_O-.
        self.amp_1.output.signal >> self.r_in_2.p1
        self.r_in_2.p2 >> self.amp_2.inverting.signal
        self.amp_2.inverting.signal >> self.r_out_2.p1
        self.r_out_2.p2 >> self.amp_2.output.signal
        self.amp_2.output.signal >> self.e_out_minus.probe
        # The bottom wire.
        self.amp_1.non_inverting.signal >> self.ground.node
        self.amp_2.non_inverting.signal >> self.ground.node
        self.e_in_return.probe >> self.ground.node
        self.e_out_return.probe >> self.ground.node

    def constraints(self):
        require(equals(self.a_plus, negative(over(self.r_out_1.resistance, self.r_in_1.resistance))))
        require(
            equals(
                self.a_minus,
                product(negative(over(self.r_out_2.resistance, self.r_in_2.resistance)), self.a_plus),
            )
        )
        require(equals(self.a_diff, minus(self.a_plus, self.a_minus)))
        # A sine of peak E_I takes the difference from -|a_diff| E_I to +|a_diff| E_I.
        require(equals(self.pp_per_peak, product(2 * ratio, minus(self.a_minus, self.a_plus))))


def _sine(peak: str, note: str, expected: float | str) -> Run:
    half = 2 * float(peak)
    return Run(
        f"sine_{peak}v_peak",
        Transient(stop="3m", step="1u"),
        drive={"e_in": f"SIN(0 {peak} 1k)"},
        measure={
            "pp_diff": "pp v(diff_probe) from=1m to=3m",
            "pp_plus": "pp v({e_out_plus.1}) from=1m to=3m",
            "max_plus": "max v({e_out_plus.1}) from=1m to=3m",
            "max_minus": "max v({e_out_minus.1}) from=1m to=3m",
        },
        claims=[
            Claim("pp_diff", expected, within=0.002, unit="V", note=note),
            Claim(
                "pp_plus",
                half,
                within=0.002,
                unit="V",
                note="Against ground, E_O+ swings 2 E_I p-p, no more than the input.",
            ),
        ],
        units={"max_plus": "V", "max_minus": "V"},
        # ngspice's meas reads one vector, so a unit-gain VCVS writes the
        # difference E_O+ - E_O- onto a node of its own. It loads nothing.
        cards=["EDIFF_PROBE diff_probe 0 {e_out_plus.1} {e_out_minus.1} 1"],
    )


BENCH = Bench(
    page=50,
    title="Balanced Output",
    runs=[
        Run(
            "dc_gains",
            OperatingPoint(),
            drive={"e_in": "DC 1"},
            measure={
                "gain_plus": "v({e_out_plus.1}) / v({e_in.1})",
                "gain_minus": "v({e_out_minus.1}) / v({e_in.1})",
                "gain_diff": "(v({e_out_plus.1}) - v({e_out_minus.1})) / v({e_in.1})",
            },
            claims=[
                Claim("gain_plus", "a_plus", within=0.001),
                Claim("gain_minus", "a_minus", within=0.001),
                Claim("gain_diff", "a_diff", within=0.001),
            ],
        ),
        _sine(
            "1",
            "4 E_I p-p for E_I = 1 V peak, so the volts read as pp_per_peak: the "
            "handbook's claim, with E_I read as the peak. Held to 0.2% for the "
            "sampled peaks.",
            "pp_per_peak",
        ),
        _sine(
            "10",
            "40 V p-p across the two outputs while each stays inside +/-13.5 V: "
            "more than the 27 V p-p one output can give. Held to 0.2%.",
            40.0,
        ),
    ],
)
