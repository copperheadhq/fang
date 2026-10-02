"""Simple gain control, SBOA092B pages 70 and 71.

    "Wide range gain or attenuation."
    "Unity gain with R centered. The gain is not linear with potentiometer
    setting. Z_in drops as gain is increased."

One 10 kOhm potentiometer does both resistors' work: one end at E_I, the
other at E_O, and the wiper on the inverting input, with the non-inverting
input on ground. With the wiper a fraction k of the travel from the E_I end,
k R is the input resistor and (1 - k) R the feedback, so

    E_O / E_I = -(1 - k) / k        Z_in = k R

which is -1 at k = 1/2, runs towards minus infinity as k falls and towards 0
as k rises, and is not linear in k. The page prints no formula; the program
derives this one from the figure and holds the page's three sentences against
it. The pot is labelled "10 kW" on the page, which is 10 kOhm with the ohm
sign lost to a font.

The setting is the run's: `setting` records the centre as the program's
default, and the bench moves the wiper through five positions.
"""

import sys
from decimal import Decimal
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Parameter, System, kOhm, require
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
    equals,
    minus,
    negative,
    over,
    product,
    ratio,
)


class SimpleGainControl(System):
    """A potentiometer from E_I to E_O with its wiper on the summing point."""

    figure = Cites(
        "Wide range gain or attenuation. Unity gain with R centered. The gain is "
        "not linear with potentiometer setting. Zin drops as gain is increased. "
        "(Pot drawn as 10 kW)",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="pages 70 and 71, Simple Gain Control",
    )

    setting = Chooses(
        "Where is the wiper?",
        selected=(
            "at the centre by default, where the page says the gain is unity; "
            "the bench moves it to 0.1, 0.25, 0.75 and 0.9 of the travel from "
            "the E_I end"
        ),
        alternatives=[
            {
                "option": "one fixed setting only",
                "reason": (
                    "the page's claims are about how gain and Z_in move with the "
                    "setting, which one setting cannot show"
                ),
            },
            {
                "option": "the wiper at either end",
                "reason": (
                    "at the E_I end the gain is unbounded and the op amp saturates; "
                    "at the E_O end the input is shorted to the summing point and "
                    "the gain is 0 with a 10 kOhm load on the output"
                ),
            },
        ],
        rationale=(
            "the pot's travel is its only adjustment, and the page names none",
        ),
    )

    a_v = Parameter("1", default=-1 * ratio, description="E_O / E_I at the default setting")
    z_in = Parameter("Ohm", default=5 * kOhm, description="what E_I sees at the default setting")

    e_in = Terminal()
    e_out = Terminal()
    pot = Potentiometer(resistance=10 * kOhm, setting=Decimal("0.5") * ratio)
    amp = OpAmp()
    ground = Ground()

    def architecture(self):
        self.e_in.probe >> self.pot.end_a
        self.pot.wiper >> self.amp.inverting.signal
        self.pot.end_b >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe
        self.amp.non_inverting.signal >> self.ground.node

    def constraints(self):
        r_input = product(self.pot.resistance, self.pot.setting)
        r_feedback = product(self.pot.resistance, minus(1 * ratio, self.pot.setting))
        require(equals(self.a_v, negative(over(r_feedback, r_input))))
        require(equals(self.z_in, r_input))


def _at(k: float, gain: float, z_in: float, name: str) -> Run:
    return Run(
        name,
        OperatingPoint(),
        drive={"e_in": "DC 0.1"},
        settings={"pot": {"setting": k}},
        measure={
            "gain": "v({e_out.1}) / v({e_in.1})",
            "z_in": "-v({e_in.1}) / i(vdrive_e_in)",
        },
        claims=[
            Claim("gain", gain, within=0.001, note=f"-(1 - {k:g}) / {k:g}"),
            Claim("z_in", z_in, within=0.001, unit="Ohm", note=f"{k:g} x 10 kOhm"),
        ],
    )


BENCH = Bench(
    page=70,
    title="Simple Gain Control",
    runs=[
        _at(0.1, -9.0, 1000.0, "wiper_0_10"),
        _at(0.25, -3.0, 2500.0, "wiper_0_25"),
        Run(
            "wiper_centre",
            OperatingPoint(),
            drive={"e_in": "DC 0.1"},
            measure={
                "gain": "v({e_out.1}) / v({e_in.1})",
                "z_in": "-v({e_in.1}) / i(vdrive_e_in)",
            },
            claims=[
                Claim("gain", "a_v", within=0.001, note="unity gain with R centred"),
                Claim("z_in", "z_in", within=0.001, unit="Ohm"),
            ],
        ),
        _at(0.75, -1 / 3, 7500.0, "wiper_0_75"),
        _at(0.9, -1 / 9, 9000.0, "wiper_0_90"),
    ],
)
