"""The integrator with zero control and regeneration, SBOA092B page 57.

    E_O = -1/(R1 C_O) integral E_I dt = -10 integral E_I dt, held without decay

The page follows "Regeneration may be used to increase open loop DC gain to
infinity" on page 56, and prints no formula, only a procedure. The drawing,
read wire by wire (`reading`):

    the integrator   E_I, R1 100 kOhm, into the - input; C_O 1 uF from there
                     to the output, with the reset switch across it
    zero control     the + terminal through R9 10 kOhm and the - terminal
                     through R10 10 kOhm to the two ends of R8 (10 kOhm); the
                     wiper feeds R6 1 MOhm to the - input and R7 1 MOhm to the
                     + input
    regeneration     R3 10 MOhm from the output to a node X; R2 100 kOhm from
                     X to the + input; R4 1 kOhm and the rheostat R5 (2 kOhm,
                     wiper tied to its grounded end) from X to ground

So a fraction k of the output, about (R4 + R5)/R3 times R7/(R2 + R7), is fed
back to the + input: positive feedback. An op amp with open-loop gain A holds
its - input at E_O (k - 1/A), and with the input open that voltage leaks
charge off C_O through R6, so the output decays with a time constant near
R6 C_O / (1/A - k). Without regeneration it is A R6 C_O; regeneration shrinks
the denominator and the hold lengthens, until k passes 1/A and the output
grows instead: the handbook's step 3.

The feedback fraction runs from 0.9e-4 to 2.7e-4 over R5's travel, so the
network is sized for an op amp of 70 to 80 dB, not the bench's default 120 dB
(`op_amp`). The program gives the op amp an open-loop gain of 5000, for which
the balance falls at 60% of R5's travel, near the centre the procedure starts
from.

What the program claims: the integration rate, -10 V/s per volt; the hold
time constant with regeneration taken out, A R6 C_O; and the longer one with
R5 at a quarter of its travel. It does not claim an infinite hold: that is a
knife-edge setting, and the runs show the two sides of it instead.
"""

import sys
from decimal import Decimal
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import MOhm, Parameter, System, UnitLiteral, kOhm, require, s, uF
from fang.parts import Capacitor, Resistor
from fang.rationale import Calculates, Chooses, Cites
from fang.simulation import Transient

from handbook import (
    Bench,
    Claim,
    Ground,
    OpAmp,
    Potentiometer,
    Run,
    Switch,
    Terminal,
    equals,
    minus,
    negative,
    over,
    product,
    ratio,
    total,
    within,
)

#: A rate: volts of output per second, for each volt of input.
per_second = UnitLiteral("1/s")

#: The reset: closed at t = 0, open from 10 ms.
RESET = "PWL(0 1 10m 1 10.001m 0)"
#: The + and - terminals of the zero control, read as the +/-15 V rails.
RAILS = {"rail_plus": "DC 15", "rail_minus": "DC -15"}

#: Step 2 of the procedure: apply an input, let the integrator run up, then
#: open-circuit the input. A 1 V source reaches E_I through a switch the bench
#: adds, closed until 0.51 s: 0.5 s at -10 V/s leaves the output near -5 V.
#: HB_SWITCH is the reset switch's model, already in the deck.
RUN_UP_AND_OPEN = [
    "VSIG sig 0 DC 1",
    "SSIG sig {e_in.1} sig_ctl 0 HB_SWITCH",
    "VSIG_CTL sig_ctl 0 PWL(0 1 510m 1 510.1m 0)",
]

#: Read the output 100 s apart once the input is open; the decay (or growth)
#: is exponential, so its time constant is -(t2 - t1)/ln(E2/E1).
HOLD_MEASURE = {
    "e_1s": "find v({e_out.1}) at=1",
    "e_101s": "find v({e_out.1}) at=101",
    "tau": "-100 / ln(e_101s / e_1s)",
}


class RegenerativeIntegrator(System):
    """An integrator with a zero control on both inputs and positive feedback to the + input."""

    figure = Cites(
        "Regeneration may be used to increase open loop DC gain to infinity. "
        "If integrator output decays toward zero, increase regeneration by "
        "increasing R5. If output continues to grow, decrease regeneration.",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="pages 56-57, Simple Integrators (regeneration)",
    )

    reading = Chooses(
        "Where do R2, R3, R4, R5, R6 and R7 connect?",
        selected=(
            "R6 from the R8 wiper to the - input and R7 from the wiper to the + "
            "input; R3 from the output to node X, R2 from X to the + input, and "
            "R4 plus the rheostat R5 from X to ground"
        ),
        alternatives=[
            {
                "reading": "R2 and R3 in series from the - input to the output",
                "reason": (
                    "the vertical wire at the left end of R2 comes down from the + "
                    "input's junction dot, and a resistive path across C_O would "
                    "make the regeneration negative feedback that shortens the hold"
                ),
            },
            {
                "reading": "R6 and R7 in series, the wiper feeding only their junction",
                "reason": "the two resistors end on separate dots, one on each op amp input",
            },
        ],
        rationale=(
            "the handbook's procedure only makes sense with positive feedback: "
            "more R5 must mean more regeneration, and (R4 + R5)/R3 rises with R5",
        ),
    )

    op_amp = Chooses(
        "What open-loop gain does the op amp have?",
        selected="5000 (74 dB)",
        alternatives=[
            {
                "option": "the bench default, 1e6",
                "reason": (
                    "the smallest feedback fraction the network can set, with R5 at "
                    "zero, is 0.9e-4, ninety times 1/A: the output runs away at every "
                    "setting and the regeneration control does nothing useful"
                ),
            },
            {
                "option": "1e4",
                "reason": "the balance would fall at 10% of R5's travel, not near the centre the procedure starts from",
            },
        ],
        rationale=(
            "the network brackets 1/A for A between about 3700 and 11000, so it was "
            "sized for an op amp of that era's gain",
            "with 5000, k = 1/A at R5 = 1.2 kOhm, 60% of its travel",
        ),
    )

    settings = Chooses(
        "Where are R8 and R5 set?",
        selected="R8 centred (the op amp is given no offset, so zero is the centre); R5 at a quarter of its travel",
        alternatives=[
            {
                "option": "R5 at the balance, 60%",
                "reason": "the hold there is as long as the setting is exact, which is no number to claim",
            },
        ],
        rationale=("a quarter of the travel is regeneration short of balance: a longer hold, still decaying",),
    )

    hold_estimate = Calculates(
        "tau = R6 C_O (1 - k) / (1/A - k), k = (R4 + x R5)/(R3 + R4 + x R5) R7/(R2 + R7)",
        inputs=("r2", "r3", "r4", "r5", "r6", "r7", "c_o", "amp"),
        result=(
            "k = 0 without regeneration: A R6 C_O = 5000 s. With R5 at a quarter "
            "(500 Ohm), k = 1.364e-4 and tau = 15,700 s, about three times longer. "
            "The zero control's 7.5 kOhm source resistance and R7's pull on the "
            "wiper are left out; the simulation puts tau 2.3% lower"
        ),
    )

    rate = Parameter("1/s", default=-10 * per_second, description="-1/(R1 C_O)")
    hold_open = Parameter(
        "s",
        default=5000 * s,
        description="the output's decay time constant with the input open and no regeneration: A R6 C_O",
    )
    k_quarter = Parameter(
        "1",
        default=Decimal("1.3635e-4") * ratio,
        description="the fraction of E_O fed back to the + input with R5 at a quarter",
    )
    hold_quarter = Parameter(
        "s",
        default=15710 * s,
        description="the decay time constant with R5 at a quarter of its travel",
    )

    e_in = Terminal()
    e_out = Terminal()
    rail_plus = Terminal()
    rail_minus = Terminal()
    r1 = Resistor(resistance=100 * kOhm)
    c_o = Capacitor(capacitance=1 * uF)
    reset = Switch()
    # Zero control.
    r9 = Resistor(resistance=10 * kOhm)
    r8 = Potentiometer(resistance=10 * kOhm, setting=Decimal("0.5") * ratio)
    r10 = Resistor(resistance=10 * kOhm)
    r6 = Resistor(resistance=1 * MOhm)
    r7 = Resistor(resistance=1 * MOhm)
    # Regeneration.
    r2 = Resistor(resistance=100 * kOhm)
    r3 = Resistor(resistance=10 * MOhm)
    r4 = Resistor(resistance=1 * kOhm)
    r5 = Potentiometer(resistance=2 * kOhm, setting=Decimal("0.25") * ratio)
    amp = OpAmp(open_loop_gain=5000 * ratio)
    ground = Ground()

    def architecture(self):
        # The integrator and its reset.
        self.e_in.probe >> self.r1.p1
        self.r1.p2 >> self.amp.inverting.signal
        self.amp.inverting.signal >> self.c_o.p1
        self.c_o.p1 >> self.reset.p1
        self.c_o.p2 >> self.amp.output.signal
        self.reset.p2 >> self.amp.output.signal
        self.amp.output.signal >> self.e_out.probe
        # Zero control: rail, R9, R8, R10, rail; the wiper to both inputs.
        self.rail_plus.probe >> self.r9.p1
        self.r9.p2 >> self.r8.end_a
        self.r8.end_b >> self.r10.p2
        self.r10.p1 >> self.rail_minus.probe
        self.r8.wiper >> self.r6.p1
        self.r8.wiper >> self.r7.p1
        self.r6.p2 >> self.amp.inverting.signal
        self.r7.p2 >> self.amp.non_inverting.signal
        # Regeneration: output, R3, node X, R2 to the + input; R4 and R5 to ground.
        self.amp.output.signal >> self.r3.p2
        self.r3.p1 >> self.r2.p2
        self.r2.p1 >> self.amp.non_inverting.signal
        self.r3.p1 >> self.r4.p1
        self.r4.p2 >> self.r5.end_a
        self.r5.wiper >> self.r5.end_b
        self.r5.end_b >> self.ground.node

    def constraints(self):
        require(
            equals(self.rate, negative(over(1 * ratio, product(self.r1.resistance, self.c_o.capacitance))))
        )
        gain = self.amp.open_loop_gain
        require(equals(self.hold_open, product(gain, self.r6.resistance, self.c_o.capacitance)))

        shunt = total(self.r4.resistance, product(self.r5.resistance, self.r5.setting))
        k = product(
            over(shunt, total(self.r3.resistance, shunt)),
            over(self.r7.resistance, total(self.r2.resistance, self.r7.resistance)),
        )
        require(within(self.k_quarter, k, 0.0005))
        require(
            within(
                self.hold_quarter,
                over(
                    product(self.r6.resistance, self.c_o.capacitance, minus(1 * ratio, self.k_quarter)),
                    minus(over(1 * ratio, gain), self.k_quarter),
                ),
                0.001,
            )
        )


BENCH = Bench(
    page=57,
    title="Integrator with zero control and regeneration",
    runs=[
        Run(
            "rate",
            Transient(stop="1.1", step="1m"),
            drive={"e_in": "DC 0.1", **RAILS},
            switches={"reset": RESET},
            measure={
                "e_early": "find v({e_out.1}) at=0.1",
                "e_late": "find v({e_out.1}) at=1.1",
                "rate_per_volt": "(e_late - e_early) / 1.0 / 0.1",
            },
            claims=[Claim("rate_per_volt", "rate", within=0.001, unit="/s")],
            units={"e_early": "V", "e_late": "V"},
            note="0.1 V on E_I with R5 at a quarter; the reset switch opens at 10 ms.",
        ),
        Run(
            "hold_without_regeneration",
            Transient(stop="101", step="10m"),
            drive=RAILS,
            switches={"reset": RESET},
            cards=RUN_UP_AND_OPEN + ["RNOREGEN {r3.1} 0 1m"],
            measure=HOLD_MEASURE,
            claims=[
                Claim("tau", "hold_open", within=0.03, unit="s",
                      note=(
                          "3%: A R6 C_O leaves out the zero control's source resistance "
                          "and the path through R7 and R2 to the + input"
                      )),
            ],
            units={"e_1s": "V", "e_101s": "V"},
            note=(
                "Regeneration taken out: node X tied to ground by a card the bench "
                "adds, so the + input sees none of the output. The input runs the "
                "output up to about -5 V and is opened at 0.51 s; the output then "
                "leaks through R6 with the time constant A R6 C_O."
            ),
        ),
        Run(
            "hold_with_regeneration",
            Transient(stop="101", step="10m"),
            drive=RAILS,
            switches={"reset": RESET},
            cards=RUN_UP_AND_OPEN,
            measure=HOLD_MEASURE,
            claims=[
                Claim("tau", "hold_quarter", within=0.03, unit="s",
                      note="3%, for the same simplifications as the run above"),
            ],
            units={"e_1s": "V", "e_101s": "V"},
            note=(
                "The circuit as drawn, R5 at a quarter of its travel: the same run "
                "up and the same open input, and a hold three times longer."
            ),
        ),
        Run(
            "too_much_regeneration",
            Transient(stop="101", step="10m"),
            drive=RAILS,
            switches={"reset": RESET},
            settings={"r5": {"setting": 1.0}},
            cards=RUN_UP_AND_OPEN,
            measure=HOLD_MEASURE,
            units={"e_1s": "V", "e_101s": "V", "tau": "s"},
            note=(
                "R5 at the top of its travel: k = 2.7e-4 is past 1/A = 2e-4, so the "
                "output grows (a negative time constant), the handbook's cue to "
                "decrease regeneration. Not a claim: it shows the other side of the balance."
            ),
        ),
    ],
)
