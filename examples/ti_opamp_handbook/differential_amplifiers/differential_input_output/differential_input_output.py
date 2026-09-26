"""The differential input-output amplifier, SBOA092B page 75.

    E_O = (R_O / R_I)(E2 - E1) = 10 (E2 - E1)

The balanced output amplifier of page 69 with values: R_I = 1 kOhm and
R_O = 10 kOhm in both legs. E1 goes through R_I into the inverting input
with R_O to the top output, E2 through R_I into the non-inverting input with
R_O to the bottom output. The page prints no formula, only "for use in
driving floating loads"; the gain is page 69's, with these values 10.

The output is the difference between the two output terminals, and neither of
them is ground, so a load goes across them. The figure draws none, so `load`
records the one the bench puts there for one run: 1 kOhm, across the outputs
and touching nothing else. Where the outputs sit together is set inside the op
amp, as page 69 says, and the model holds that level at ground.
"""

import sys
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
    DifferentialOpAmp,
    Ground,
    Run,
    Terminal,
    equals,
    over,
    ratio,
)


class DifferentialInputOutput(System):
    """Two inverting legs around one op amp with two outputs, R_I 1k and R_O 10k."""

    figure = Cites(
        "For use in driving floating loads. Input may be floating source",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 75, Differential Input-Output",
    )

    gain_rule = Cites(
        "E_O = (R_O/R_I)(E2 - E1)",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 69, The Differential (Balanced) Output Amplifier",
    )

    load = Chooses(
        "What load does the bench put across the outputs?",
        selected="1 kOhm, across the two output terminals and nowhere near ground, in one run",
        alternatives=[
            {
                "option": "no load at all",
                "reason": (
                    "the page's point is a floating load, and a run with one "
                    "shows the difference does not need a ground to be measured"
                ),
            },
            {
                "option": "a load from each output to ground",
                "reason": "that is two grounded loads, not the floating one the page names",
            },
        ],
        rationale=(
            "the figure draws no load",
            "the bench's outputs are ideal, so the load shows only that nothing "
            "needs a ground, not how a real part's outputs sag under it",
        ),
    )

    a_d = Parameter("1", default=10 * ratio, description="E_O / (E2 - E1)")

    e1 = Terminal()
    e2 = Terminal()
    e_o = Terminal()
    e_p = Terminal()
    common = Terminal()
    r_in_top = Resistor(resistance=1 * kOhm)
    r_out_top = Resistor(resistance=10 * kOhm)
    r_in_bottom = Resistor(resistance=1 * kOhm)
    r_out_bottom = Resistor(resistance=10 * kOhm)
    amp = DifferentialOpAmp()
    ground = Ground()
    def architecture(self):
        # The top leg: E1 into the - input, R_O to the output that falls when
        # that input rises.
        self.e1.probe >> self.r_in_top.p1
        self.r_in_top.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.r_out_top.p1
        self.r_out_top.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_o.probe

        # The bottom leg: E2 into the + input, R_O to the other output.
        self.e2.probe >> self.r_in_bottom.p1
        self.r_in_bottom.p2 >> self.amp.non_inverting.signal
        self.amp.non_inverting.signal >> self.r_out_bottom.p1
        self.r_out_bottom.p2 >> self.amp.output_minus.signal
        self.amp.output_minus.signal >> self.e_p.probe

        # Nothing in the figure touches ground but the grounded terminal
        # between E1 and E2: the op amp's common level is its own.
        self.common.probe >> self.ground.node

    def constraints(self):
        require(equals(self.r_in_top.resistance, self.r_in_bottom.resistance))
        require(equals(self.r_out_top.resistance, self.r_out_bottom.resistance))
        require(equals(self.a_d, over(self.r_out_top.resistance, self.r_in_top.resistance)))


BENCH = Bench(
    page=75,
    title="Differential Input-Output",
    runs=[
        Run(
            "difference",
            OperatingPoint(),
            drive={"e1": "DC 0.1", "e2": "DC 0.4"},
            measure={
                "gain": "(v({e_o.1}) - v({e_p.1})) / (v({e2.1}) - v({e1.1}))",
                "e_p": "v({e_p.1})",
            },
            claims=[Claim("gain", "a_d", within=0.001)],
            units={"e_p": "V"},
            note=(
                "E_O is the top output less the bottom one. Where the bottom "
                "output sits is set inside the op amp; this model centres the "
                "pair on ground, so it is -E_O/2 here and not a handbook claim."
            ),
        ),
        Run(
            "floating_load",
            OperatingPoint(),
            drive={"e1": "DC 0.1", "e2": "DC 0.4"},
            measure={
                "e_o": "v({e_o.1}) - v({e_p.1})",
                "i_load": "(v({e_o.1}) - v({e_p.1})) / 1000",
            },
            cards=["RLOAD {e_o.1} {e_p.1} 1k"],
            claims=[
                Claim("e_o", 3.0, within=0.001, unit="V",
                      note="10 x 0.3 V, with 1 kOhm across the outputs and no ground on it"),
            ],
            units={"i_load": "A"},
            note=(
                "The load (see `load`) is a card, since the figure draws none. "
                "The model's outputs are ideal, so the load cannot pull them; "
                "a real part's output resistance would."
            ),
        ),
        Run(
            "common_mode",
            OperatingPoint(),
            drive={"e1": "DC 1", "e2": "DC 1"},
            measure={"e_o": "v({e_o.1}) - v({e_p.1})"},
            claims=[Claim("e_o", 0, within=1e-4, absolute=True, unit="V",
                          note="1 V on both inputs gives no difference out")],
        ),
    ],
)
