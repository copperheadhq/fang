"""The linear current source, SBOA092B page 81.

    When R_L << R2,   I_L / E_I = R2 / (R1 R3) = 1 mA / Volt

Two op amps. The first sums E_I through R1 and the load's voltage through
the upper R2, both 100 kOhm, against R0 (100 kOhm, with C_O across it). The
second inverts the first's output through a second R0 and R2, so its output
is R2 E_I / R1 + V_L, and R3 turns the difference between that and V_L into
a current, R2 E_I / (R1 R3), whatever V_L is. The upper R2 takes V_L / R2 of
it back, which is the error "R_L << R2" waves away: with 100 Ohm of load it
is 0.1%.

Table 2 scales the current by R3 alone: 1 kOhm for 1 mA per volt, 100 Ohm
for 10, 10 Ohm for 100. The program makes R3 a part a run can change, and
the bench runs all three rows.

The figure gives C_O no value and R_L none either; `c_o` and `load` record
what was taken.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Ohm, Parameter, System, UnitLiteral, kOhm, pF, require
from fang.parts import Capacitor, Resistor, TwoPin
from fang.rationale import Chooses, Cites
from fang.simulation import OperatingPoint, Transient

from handbook import Bench, Claim, Ground, OpAmp, Run, Terminal, equals, over, product

#: A transconductance: the current out per volt in.
mA_per_V = UnitLiteral("mA/V")


class SettableResistor(TwoPin):
    """A resistor a run may change: the load, or Table 2's scaling resistor.

    SPICE knows a resistor, but the bench only rewrites a part it writes
    itself, so this one writes its own card, and a zero-volt source after it
    so a measurement reads its current as `i(v<ref>_sense)`.
    """

    designator_prefix = "RS"
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
        return f"{value('resistance'):.6g} Ohm, with its current sensed"


class LinearCurrentSource(System):
    """A summing inverter, an inverter after it, and R3 into the load."""

    figure = Cites(
        "When R_L << R2, I_L / E_I = R2 / (R1 R3) = 1 mA / Volt. C_O added for "
        "high frequency stability. Change R3 for current scaling: 1 kOhm, "
        "1 mA / Volt; 100 Ohm, 10 mA / Volt; 10 Ohm, 100 mA / Volt.",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 81, Linear Current Source, and Table 2",
    )

    c_o_value = Chooses(
        "What is C_O?",
        selected="100 pF, across the first amplifier's R0",
        alternatives=[
            {
                "option": "leave it out",
                "reason": "the page says it is there for stability; the d.c. "
                "claims do not depend on it, but the drawn circuit has it",
            },
        ],
        rationale=(
            "the figure draws C_O across R0 and gives no value",
            "100 pF against 100 kOhm rolls the first stage off at 16 kHz, far "
            "above anything the d.c. runs ask of it",
        ),
    )

    load = Chooses(
        "What is R_L?",
        selected="100 Ohm",
        alternatives=[
            {
                "option": "10 kOhm",
                "reason": "the upper R2 would then take 10% of the current, "
                "where the formula assumes R_L << R2",
            },
        ],
        rationale=(
            "the current falls short by R_L / R2, 0.1% at 100 Ohm",
            "at 10 mA per volt the load sits at 1 V, and the second output at 2 V",
        ),
    )

    i_per_volt = Parameter(
        "mA/V", default=1 * mA_per_V, description="I_L / E_I: R2 / (R1 R3)"
    )

    e_in = Terminal()
    r1 = Resistor(resistance=100 * kOhm)
    r0_first = Resistor(resistance=100 * kOhm)
    c_o = Capacitor(capacitance=100 * pF)
    r0_second = Resistor(resistance=100 * kOhm)
    r2_second = Resistor(resistance=100 * kOhm)
    r2_upper = Resistor(resistance=100 * kOhm)
    r3 = SettableResistor(resistance=1 * kOhm)
    r_load = SettableResistor(resistance=100 * Ohm)
    first = OpAmp()
    second = OpAmp()
    ground = Ground()

    def architecture(self):
        # The first amplifier sums E_I and the load voltage.
        self.e_in.probe >> self.r1.p1
        self.r1.p2 >> self.first.inverting.signal
        self.first.inverting.signal >> self.r0_first.p1
        self.r0_first.p1 >> self.c_o.p1
        self.r0_first.p1 >> self.r2_upper.p1
        self.r0_first.p2 >> self.first.output.signal
        self.c_o.p2 >> self.first.output.signal
        self.first.non_inverting.signal >> self.ground.node

        # The second inverts it.
        self.first.output.signal >> self.r0_second.p1
        self.r0_second.p2 >> self.second.inverting.signal
        self.second.inverting.signal >> self.r2_second.p1
        self.r2_second.p2 >> self.second.output.signal
        self.second.non_inverting.signal >> self.ground.node

        # R3 into the load, and the upper R2 back from it.
        self.second.output.signal >> self.r3.p1
        self.r3.p2 >> self.r_load.p1
        self.r_load.p1 >> self.r2_upper.p2
        self.r_load.p2 >> self.ground.node

    def constraints(self):
        require(
            equals(
                self.i_per_volt,
                over(self.r2_upper.resistance, product(self.r1.resistance, self.r3.resistance)),
            )
        )
        # The cancellation of V_L needs the second stage's gain to be the
        # first stage's R0 over the upper R2.
        require(
            equals(
                over(self.r2_second.resistance, self.r0_second.resistance),
                over(self.r2_upper.resistance, self.r0_first.resistance),
            )
        )


SHORT = "Low by R_L / R2, 0.1% for 100 Ohm: the current the upper R2 takes back."


def _row(r3: float, gain: float, drive: float, note: str = "") -> Run:
    """One row of Table 2: R3 set, and the load current per volt measured."""
    claim = (
        Claim("i_per_volt", "i_per_volt", within=0.002, unit="A/V", note=SHORT)
        if r3 == 1000
        else Claim("i_per_volt", gain, within=0.002, unit="A/V",
                   note=f"Table 2: R3 = {r3:g} Ohm gives {gain * 1000:g} mA / Volt. {SHORT}")
    )
    return Run(
        f"r3_{r3:g}_ohm",
        OperatingPoint(),
        drive={"e_in": f"DC {drive:g}"},
        settings={"r3": {"resistance": r3}},
        measure={
            "i_per_volt": "i(vrs2_sense) / v({e_in.1})",
            "v_load": "v({r_load.1})",
            "second_out": "v({second.OUT})",
        },
        claims=[claim],
        units={"v_load": "V", "second_out": "V"},
        note=note,
    )


BENCH = Bench(
    page=81,
    title="Linear Current Source",
    runs=[
        _row(1000, 0.001, 1),
        _row(100, 0.01, 1),
        _row(10, 0.1, 0.1, note="E_I is 100 mV here, so the load current is 10 mA "
             "rather than 100."),
        Run(
            "step",
            Transient(stop="1m", step="0.5u"),
            drive={"e_in": "PULSE(0 1 10u 1u 1u 2m 4m)"},
            measure={
                "i_settled": "find i(vrs2_sense) at=500u",
                "i_peak": "max i(vrs2_sense) from=0 to=500u",
            },
            claims=[
                Claim("i_settled", 0.000999, within=0.002, unit="A",
                      note="1 mA per volt, less the 0.1% the upper R2 takes"),
                Claim("i_peak", 0.000999, within=0.01, unit="A",
                      note="no overshoot worth the name: the loop through the "
                      "upper R2 settles with C_O in place"),
            ],
            note="A 1 V step into E_I, to see the two loops settle rather than ring.",
        ),
    ],
)
