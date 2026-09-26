"""The Wien bridge oscillator, SBOA092B page 83.

    f_O = 1 / (2 pi R C), 100 to 6000 Hz

R and C in series from the output to the + input, R and C in parallel from
there to ground: at 1 / (2 pi R C) the network passes a third of the output
with no phase shift, so the op amp oscillates there if its gain is exactly
3. The gain is set on the - input: R2 (1.8 kOhm) and the R1 rheostat
(500 Ohm) from the output, R3 (220 Ohm) and the lamp LP1 to ground. Gain 3
needs R3 + R_lamp = (R1 + R2) / 2. A cold lamp is a small resistance, so the
gain starts above 3 and the oscillation grows; the lamp warms, its
resistance rises, and the amplitude stops where it balances.

The handbook has no lamp part, so the program defines one: a GE 1869 is a
10 V, 14 mA bulb, 714 Ohm hot, and `lamp_model` records how the rest was
modelled. The figure draws R and C as ganged variable parts, and `tuning`
records them as two 100 kOhm rheostats and a fixed 15.9 nF, which covers the
page's 100 Hz to 6000 Hz.

The drawn values ask the lamp for (R1 + R2) / 2 - R3, 680 to 930 Ohm, which
a 714 Ohm bulb reaches only near its rating. At that point the lamp carries
14 mA and the output about 39 V rms. On the +/-13.5 V swing the handbook
assumes elsewhere the output clips long before the lamp gets there: the
first run shows that. The runs that show the lamp regulating give the op amp
a +/-60 V swing, which `swing` records.
"""

import sys
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from decimal import Decimal

from fang.lang import Hz, Ohm, Parameter, System, V, kHz, kOhm, mA, ms, nF, require
from fang.parts import Capacitor, Resistor, TwoPin
from fang.rationale import Chooses, Cites
from fang.simulation import Transient

from handbook import (
    Bench,
    Claim,
    Ground,
    OpAmp,
    Potentiometer,
    Run,
    Terminal,
    at_most,
    corner,
    equals,
    minus,
    over,
    product,
    ratio,
    total,
    within,
)


class Lamp(TwoPin):
    """An incandescent lamp as a resistance that rises with its own heating.

    The filament's temperature rise is a first-order lag on the power it
    takes: a thermal node whose voltage is that filtered power, in watts,
    with `time_constant` as its RC. The resistance is linear in it, from
    `cold_resistance` with no power to rated voltage over rated current at
    rated power. The bench writes it as two behavioural sources: the
    filament's current, and the power that heats it.
    """

    designator_prefix = "LP"
    rated_voltage = Parameter("V")
    rated_current = Parameter("A")
    cold_resistance = Parameter("Ohm")
    time_constant = Parameter("s")

    def spice(self, ref, node, value):
        volts, amps = value("rated_voltage"), value("rated_current")
        cold, tau = value("cold_resistance"), value("time_constant")
        slope = (volts / amps - cold) / (volts * amps)
        a, b, th = node("1"), node("2"), f"th_{ref}"
        resistance = f"({cold:.6g} + {slope:.6g} * V({th}))"
        return (
            [
                f"B{ref} {a} {b} I = V({a},{b}) / {resistance}",
                f"B{ref}_HEAT 0 {th} I = V({a},{b}) * V({a},{b}) / {resistance}",
                f"R{ref}_TH {th} 0 1",
                f"C{ref}_TH {th} 0 {tau:.6g}",
            ],
            {},
        )

    def describe(self, value) -> str:
        volts, amps = value("rated_voltage"), value("rated_current")
        return (
            f"lamp: {value('cold_resistance'):.6g} Ohm cold, {volts / amps:.4g} Ohm at "
            f"{volts:.6g} V and {amps * 1000:.6g} mA, heating with a "
            f"{value('time_constant') * 1000:.6g} ms time constant"
        )


class WienBridgeOscillator(System):
    """A Wien network on the + input, and a lamp-stabilised gain of 3 on the - input."""

    figure = Cites(
        "f_O = 1 / (2 pi R C), 100 to 6000 Hz. High purity sine wave generation.",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 83, Wien Bridge Oscillator",
    )

    lamp_model = Chooses(
        "How does the GE 1869 behave?",
        selected=(
            "10 V and 14 mA rated, so 714 Ohm hot; 70 Ohm cold, a tenth of hot; "
            "resistance linear in the power it has taken, filtered with a 50 ms "
            "thermal time constant"
        ),
        alternatives=[
            {
                "option": "a power law in the filament's power",
                "reason": "closer to tungsten over the whole range, but near the "
                "rating, where this circuit runs the lamp, both give the same "
                "resistance, and a power law has no slope at zero to start from",
            },
            {
                "option": "a thermal time constant of a few ms",
                "reason": "the resistance would then follow each cycle, and at "
                "100 Hz that is distortion, where the page claims high purity",
            },
        ],
        rationale=(
            "the handbook names the lamp and no model; its rating is 10 V at 14 mA",
            "tungsten runs about ten to one hot to cold",
            "what the oscillator uses is the lamp's resistance at its operating "
            "point, which is pinned by the gain condition, not by the model",
        ),
    )

    tuning = Chooses(
        "What are R and C?",
        selected=(
            "two 100 kOhm rheostats and two 15.9 nF capacitors; 0.1 of the travel "
            "(10 kOhm) is 1 kHz, all of it 100 Hz, and 1/60 of it 6 kHz"
        ),
        alternatives=[
            {
                "option": "fixed resistors",
                "reason": "the figure draws R and C as variable, and a range of "
                "100 to 6000 Hz is a tuning range",
            },
        ],
        rationale=(
            "one rheostat of 60:1 with a fixed capacitor covers exactly the "
            "range the page prints",
        ),
    )

    gain_trim = Chooses(
        "Where is the R1 rheostat set?",
        selected="50 Ohm in circuit, so the lamp must settle at 705 Ohm",
        alternatives=[
            {
                "option": "half its travel, 250 Ohm",
                "reason": "the lamp would have to reach 805 Ohm, past its 714 "
                "Ohm rating, and burn out before the gain came down to 3",
            },
        ],
        rationale=(
            "gain 3 needs R3 + R_lamp = (R1 + R2) / 2; with R2 at 1.8 kOhm and "
            "R3 at 220 Ohm the lamp needs 680 Ohm even with R1 at zero",
            "50 Ohm is as much of R1 as a 714 Ohm lamp leaves room for",
        ),
    )

    swing = Chooses(
        "What output swing does the op amp have?",
        selected=(
            "+/-13.5 V in the first run, as elsewhere in the handbook; +/-60 V in "
            "the runs that show the lamp regulating"
        ),
        alternatives=[
            {
                "option": "change the resistors so the lamp regulates on +/-15 V supplies",
                "reason": "that is a different circuit from the one drawn",
            },
            {
                "option": "a lamp model that is hot at a lower current",
                "reason": "a GE 1869 is 714 Ohm only at its 14 mA rating; a model "
                "that got there sooner would be a different lamp",
            },
        ],
        rationale=(
            "with a 705 Ohm lamp and 220 Ohm beside it, the - input carries "
            "14 mA and the output 3 x 14 mA x 925 Ohm, 39 V rms",
            "the first run shows what the drawn circuit does on the usual swing, "
            "and the others show what it was drawn to do",
        ),
    )

    f_o = Parameter("Hz", default=1 * kHz, description="1 / (2 pi R C) at the chosen setting")
    f_low = Parameter("Hz", default=100 * Hz, description="1 / (2 pi R C) with all of R")
    lamp_resistance = Parameter(
        "Ohm", default=705 * Ohm, description="where the lamp must settle: (R1 + R2) / 2 - R3"
    )

    e_out = Terminal()
    amp = OpAmp()
    ground = Ground()

    r_series = Potentiometer(resistance=100 * kOhm, setting=Decimal("0.1") * ratio)
    c_series = Capacitor(capacitance=Decimal("15.9") * nF)
    r_shunt = Potentiometer(resistance=100 * kOhm, setting=Decimal("0.1") * ratio)
    c_shunt = Capacitor(capacitance=Decimal("15.9") * nF)

    r1 = Potentiometer(resistance=500 * Ohm, setting=Decimal("0.9") * ratio)
    r2 = Resistor(resistance=Decimal("1.8") * kOhm)
    r3 = Resistor(resistance=220 * Ohm)
    lamp = Lamp(
        rated_voltage=10 * V,
        rated_current=14 * mA,
        cold_resistance=70 * Ohm,
        time_constant=50 * ms,
    )

    def architecture(self):
        # The Wien network: R and C in series from the output, R || C to ground.
        self.amp.output.signal >> self.r_series.end_a
        self.r_series.wiper >> self.r_series.end_b
        self.r_series.end_b >> self.c_series.p1
        self.c_series.p2 >> self.amp.non_inverting.signal
        self.amp.non_inverting.signal >> self.r_shunt.end_a
        self.r_shunt.wiper >> self.r_shunt.end_b
        self.r_shunt.end_b >> self.ground.node
        self.amp.non_inverting.signal >> self.c_shunt.p1
        self.c_shunt.p2 >> self.ground.node

        # The gain: R1 (wiper tied to the output end) and R2 down to the - input.
        self.amp.output.signal >> self.r1.end_a
        self.r1.wiper >> self.r1.end_a
        self.r1.end_b >> self.r2.p1
        self.r2.p2 >> self.amp.inverting.signal

        # R3 and the lamp from the - input to ground.
        self.amp.inverting.signal >> self.r3.p1
        self.r3.p2 >> self.lamp.p1
        self.lamp.p2 >> self.ground.node

        self.amp.output.signal >> self.e_out.probe

    def constraints(self):
        r = product(self.r_series.resistance, self.r_series.setting)
        require(within(self.f_o, corner(r, self.c_series.capacitance), 0.002))
        require(within(self.f_low, corner(self.r_series.resistance, self.c_series.capacitance), 0.002))
        # The two arms are ganged: the same R and the same C.
        require(equals(self.r_shunt.resistance, self.r_series.resistance))
        require(equals(self.r_shunt.setting, self.r_series.setting))
        require(equals(self.c_shunt.capacitance, self.c_series.capacitance))

        # Gain 3: R3 + R_lamp = (R1 + R2) / 2, with R1 in circuit from the wiper down.
        r1 = product(self.r1.resistance, minus(1 * ratio, self.r1.setting))
        require(
            equals(
                self.lamp_resistance,
                minus(over(total(r1, self.r2.resistance), 2 * ratio), self.r3.resistance),
            )
        )
        # And the lamp can get there: no further than its resistance at rating.
        require(
            at_most(
                self.lamp_resistance,
                over(self.lamp.rated_voltage, self.lamp.rated_current),
            )
        )


#: 60 V either side: what the drawn circuit needs for its lamp to regulate.
WIDE = {"output_high": 60, "output_low": -60}

#: The lamp's resistance: the voltage across it over the current through R3.
#: The lamp barely changes within a cycle, so the voltages at the - input and
#: across the lamp are in phase, and the difference of their rms values is the
#: rms across R3.
LAMP = "220 * lamp_rms / (summing_rms - lamp_rms)"


def _regulating(name: str, setting: float, stop: float, step: str, f: float | str,
                note: str) -> Run:
    """A run with the wide swing, at one tuning, measured after the lamp settles."""
    late, later = stop * 0.75, stop * 0.95
    return Run(
        name,
        Transient(stop=f"{stop:g}", step=step),
        settings={"amp": WIDE, "r_series": {"setting": setting},
                  "r_shunt": {"setting": setting}},
        cards=[".ic v({c_series.1})=0.1"],
        measure={
            "t_first": f"when v({{e_out.1}})=0 rise=1 td={later:g}",
            "t_last": f"when v({{e_out.1}})=0 rise=21 td={later:g}",
            "f_o": "20 / (t_last - t_first)",
            "peak_late": f"max v({{e_out.1}}) from={late:g} to={late + stop * 0.05:g}",
            "peak_end": f"max v({{e_out.1}}) from={later:g} to={stop:g}",
            "settled": "peak_end / peak_late",
            "lamp_rms": f"rms v({{lamp.1}}) from={later:g} to={stop:g}",
            "summing_rms": f"rms v({{r3.1}}) from={later:g} to={stop:g}",
            "lamp_resistance": LAMP,
        },
        claims=[
            Claim("f_o", f, within=0.005, unit="Hz",
                  note="0.5% for the op amp's own phase shift, which grows with "
                  "frequency, and for the lamp's small ripple"),
            Claim("settled", 1, within=0.002,
                  note="the peak a fifth of the run apart: the amplitude has stopped moving"),
            Claim("lamp_resistance", "lamp_resistance", within=0.01, unit="Ohm",
                  note="the gain-3 point, read back from the lamp's own voltage and current"),
        ],
        units={"t_first": "s", "t_last": "s", "peak_late": "V", "peak_end": "V",
               "lamp_rms": "V", "summing_rms": "V"},
        note=note,
    )


BENCH = Bench(
    page=83,
    title="Wien Bridge Oscillator",
    runs=[
        Run(
            "as_drawn",
            Transient(stop="0.6", step="5u"),
            cards=[".ic v({c_series.1})=0.1"],
            measure={
                "e_high": "max v({e_out.1}) from=0.5 to=0.6",
                "e_low": "min v({e_out.1}) from=0.5 to=0.6",
                "t_first": "when v({e_out.1})=0 rise=1 td=0.5",
                "t_last": "when v({e_out.1})=0 rise=21 td=0.5",
                "f_o": "20 / (t_last - t_first)",
                "lamp_rms": "rms v({lamp.1}) from=0.5 to=0.6",
                "summing_rms": "rms v({r3.1}) from=0.5 to=0.6",
                "lamp_resistance": LAMP,
            },
            claims=[
                Claim("e_high", 13.5, within=0.01, unit="V",
                      note="the output clips at the swing: the lamp has not warmed "
                      "enough to bring the gain down to 3"),
                Claim("e_low", -13.5, within=0.01, unit="V"),
            ],
            units={"t_first": "s", "t_last": "s", "f_o": "Hz", "lamp_rms": "V",
                   "summing_rms": "V", "lamp_resistance": "Ohm"},
            note="The drawn circuit on the +/-13.5 V swing, tuned for 1 kHz. The "
            "lamp would have to reach 705 Ohm, and a clipped output drives it "
            "nowhere near: the gain stays far above 3, the output is a clipped "
            "wave, and its frequency is well below 1 / (2 pi R C).",
        ),
        _regulating(
            "regulating_1khz", 0.1, 1.2, "5u", "f_o",
            "The same circuit with a +/-60 V swing, R at 10 kOhm. The oscillation "
            "grows from a 0.1 V kick until the lamp warms to the gain-3 point.",
        ),
        _regulating(
            "regulating_6khz", 1 / 60, 1.0, "1u", 1 / (6.283185307179586 * 100e3 / 60 * 15.9e-9),
            "R turned down to 1/60 of its travel, 1.667 kOhm: the top of the "
            "page's range, 1 / (2 pi R C) = 6.006 kHz.",
        ),
    ],
)
