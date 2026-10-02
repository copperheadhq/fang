"""The time delay, SBOA092B page 90: a timer that pulls in a relay.

    Delay = R_I C_O / (2 K),   K the setting of R_7, 0 < K < 1

The least clean figure in the handbook, so the reading is recorded in full as a
decision (`reading`). As read here:

- R_7 (10 kOhm) is across the supply, and its wiper feeds R_1 (100 kOhm, the
  R_I of the formula) into the op amp's - input. The + input is on ground.
- C_0 (10 uF, the C_O) runs from the - input to a node T, not to the output.
  T goes to ground through R_5 (10 kOhm), and is reached from a node S by a
  diode pointing into T.
- S is pulled up to the supply by R_6 (10 kOhm), and the switch connects S to
  the op amp output.
- The output goes to the supply through R_3 (4.7 kOhm) and R_4 (10 kOhm) in
  series, and a diode from the - input points into their junction. That is a
  clamp: it catches the output about 8 V below ground.
- The relay coil (1 kOhm, 6 V) goes from ground through a diode into S, so it
  conducts only when S is pulled below ground.

With the switch open (reset), R_6 and R_5 hold T at half the supply less a
diode drop, the op amp sits on its clamp with its - input at ground, and C_0
charges to about 7.2 V. Closing the switch hands S to the op amp: it rises to
a diode above T and C_0 becomes an integrator's capacitor, and T ramps down at
K E / (R_1 C_0) volts a second. When the ramp can no longer supply R_5, the
diode into T lets go, the loop opens, the output falls to its clamp, S follows
it below ground, and the coil pulls in. From half the supply at K E / (R_1
C_0) is R_1 C_0 / (2 K): the page's formula.

It leaves out the diode drop at the start, the ramp stopping at R_5 K E / R_1
rather than at zero, and the wiper's own resistance, which together make the
delay a few percent short. The program claims the page's formula at K = 0.1
with that stated.
"""

import sys
from decimal import Decimal
from pathlib import Path

# The handbook's shared parts and bench live in the folder above the sections.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fang.lang import Ohm, Parameter, System, V, kOhm, require, s, uF
from fang.parts import Capacitor, Resistor
from fang.rationale import Calculates, Chooses, Cites
from fang.simulation import Transient

from handbook import (
    Bench,
    Cell,
    Claim,
    Ground,
    Meter,
    OpAmp,
    Potentiometer,
    Run,
    SignalDiode,
    Switch,
    equals,
    over,
    product,
    ratio,
)


class TimeDelayRelay(System):
    """A reset integrator that ramps down from half the supply, and a relay at the end."""

    figure = Cites(
        "Delay = R_I C_O / (2 K_I), where K is setting of R_I, 0 < K < 1. "
        "Time operated relay. Open switch to reset, close to begin timing.",
        document="SBOA092B, Handbook of Operational Amplifier Applications",
        locator="page 90, Time Delay",
    )

    reading = Chooses(
        "How is the figure wired?",
        selected=(
            "C_0 from the - input to the R_5 node T, not to the output; a diode "
            "from S into T; R_6 from the supply to S; the switch from S to the "
            "output; R_4 and R_3 from the supply to the output, with a diode from "
            "the - input into their junction; the coil from ground through a "
            "diode into S"
        ),
        alternatives=[
            {
                "reading": "C_0 returns to the op amp output",
                "reason": (
                    "the wire from C_0's + plate hops over the R_3 lead and the "
                    "vertical from T hops over the output wire: neither joins"
                ),
            },
            {
                "reading": "the diode at the coil reversed, pointing from S into the coil",
                "reason": (
                    "the triangle points up, bar above; reversed, R_6 could put at "
                    "most 15 V / 11 kOhm, 1.3 mA, through a 6 V, 1 kOhm coil, which "
                    "never pulls it in"
                ),
            },
            {
                "reading": "the upper diode points from the R_3/R_4 junction into the - input",
                "reason": (
                    "its triangle points right, away from the - input; that way it "
                    "would clamp the output high, where the timing ramp needs it"
                ),
            },
        ],
        rationale=(
            "this reading times, and gives the page's formula: T starts at half "
            "the supply and ramps down at K E / (R_1 C_0)",
            "the relay sees the op amp's clamped low output, about -7.9 V less a "
            "diode, which is enough for a 6 V coil; the diode keeps the positive "
            "output off it while timing",
        ),
    )

    supply = Chooses(
        "What is +Supply?",
        selected="15 V",
        alternatives=[
            {
                "option": "12 V",
                "reason": "nothing on the page asks for it; the handbook's op amps run on 15 V",
            },
        ],
        rationale=("the formula does not depend on it: E cancels between start and slope",),
    )

    relay = Chooses(
        "How is the relay modelled, and when does it pull in?",
        selected=(
            "its coil as a 1 kOhm meter, whose current is the reading; pull-in "
            "taken at 4.5 mA, 75% of the 6 mA a 6 V, 1 kOhm coil draws"
        ),
        alternatives=[
            {
                "option": "a coil with inductance and a contact that switches",
                "reason": (
                    "the delay is set by the timer, not the relay; a coil's own "
                    "milliseconds are beside a delay of seconds"
                ),
            },
        ],
        rationale=(
            "75% of rated voltage is the usual must-operate figure for a small relay",
            "the coil sees about 7 V once the output clamps, well past it",
        ),
    )

    setting = Chooses(
        "Where is R_7 set?",
        selected="K = 0.1, for a page delay of 5 s, and a second run at K = 0.5",
        alternatives=[
            {
                "option": "K near 1",
                "reason": "the ramp ends at R_5 K E / R_1, 1.5 V at K = 1, a fifth of the start",
            },
        ],
        rationale=(
            "the formula's approximations cost least at small K: the ramp's end "
            "point and the wiper's resistance both scale with K",
        ),
    )

    shortfall = Calculates(
        "Delay = C_0 (T_0 - R_5 I) / I, with I = K E / (R_1 + R_7 K (1 - K)) "
        "and T_0 = (E - V_D) R_5 / (R_5 + R_6)",
        inputs=("r_1", "c_0", "r_5", "r_7", "supply_cell"),
        result=(
            "T resets to 7.2 V, E/2 less half a diode drop. At K = 0.1 the ramp "
            "runs at 1.487 V/s down to 0.149 V: 4.75 s, 5% short of the page's "
            "5 s. At K = 0.5 it runs at 7.32 V/s down to 0.73 V: 0.886 s against 1 s"
        ),
    )

    delay = Parameter("s", default=5 * s, description="R_1 C_0 / (2 K)")

    supply_cell = Cell(voltage=15 * V)
    r_7 = Potentiometer(resistance=10 * kOhm, setting=Decimal("0.1") * ratio)
    r_1 = Resistor(resistance=100 * kOhm)
    c_0 = Capacitor(capacitance=10 * uF)
    amp = OpAmp()
    d_clamp = SignalDiode()
    r_4 = Resistor(resistance=10 * kOhm)
    r_3 = Resistor(resistance=4.7 * kOhm)
    r_5 = Resistor(resistance=10 * kOhm)
    d_ramp = SignalDiode()
    r_6 = Resistor(resistance=10 * kOhm)
    start = Switch()
    d_coil = SignalDiode()
    coil = Meter(resistance=1000 * Ohm)
    ground = Ground()

    def architecture(self):
        self.supply_cell.p2 >> self.ground.node

        # The reference: R_7 across the supply, its wiper through R_1.
        self.r_7.end_a >> self.ground.node
        self.r_7.end_b >> self.supply_cell.p1
        self.r_7.wiper >> self.r_1.p1
        self.r_1.p2 >> self.amp.inverting.signal
        self.amp.non_inverting.signal >> self.ground.node

        # C_0 from the - input to T, and T to ground through R_5.
        self.amp.inverting.signal >> self.c_0.p1
        self.c_0.p2 >> self.r_5.p1
        self.r_5.p2 >> self.ground.node

        # The clamp: R_4 and R_3 from the supply to the output, the diode into
        # their junction from the - input.
        self.supply_cell.p1 >> self.r_4.p1
        self.r_4.p2 >> self.r_3.p1
        self.r_3.p2 >> self.amp.output.signal
        self.amp.inverting.signal >> self.d_clamp.p1
        self.d_clamp.p2 >> self.r_4.p2

        # S: R_6 from the supply, the diode into T, the switch to the output.
        self.supply_cell.p1 >> self.r_6.p1
        self.r_6.p2 >> self.d_ramp.p1
        self.d_ramp.p2 >> self.c_0.p2
        self.r_6.p2 >> self.start.p1
        self.start.p2 >> self.amp.output.signal

        # The relay coil, from ground through its diode into S.
        self.coil.p1 >> self.ground.node
        self.coil.p2 >> self.d_coil.p1
        self.d_coil.p2 >> self.r_6.p2

    def constraints(self):
        require(
            equals(
                self.delay,
                over(
                    product(self.r_1.resistance, self.c_0.capacitance),
                    product(2 * ratio, self.r_7.setting),
                ),
            )
        )
        # The reset level is half the supply only while R_6 and R_5 are equal.
        require(equals(self.r_6.resistance, self.r_5.resistance))


def _timing(name: str, setting: str, stop: str, claims, note: str) -> Run:
    held_off = Claim(
        "coil_peak_early", 0, within=1e-3, absolute=True, unit="A",
        note="closing the switch does not itself pull the relay in: the "
        "output leaves its clamp as the switch closes",
    )
    return Run(
        name,
        Transient(stop=stop, step="1m"),
        settings={"r_7": {"setting": float(Decimal(setting))}},
        switches={"start": "PWL(0 0 0.1 0 0.1001 1)"},
        measure={
            "t_reset": "find v({c_0.2}) at=0.09",
            "coil_reset": "find i(vm1_sense) at=0.09",
            "coil_peak_early": "max i(vm1_sense) from=0.1 to=0.15",
            "t_pull_in": "when i(vm1_sense)=4.5m rise=1",
            "delay_measured": "t_pull_in - 0.1",
            "coil_on": "find i(vm1_sense) at=" + stop,
        },
        claims=[*claims, held_off],
        units={
            "t_reset": "V",
            "coil_reset": "A",
            "coil_peak_early": "A",
            "t_pull_in": "s",
            "delay_measured": "s",
            "coil_on": "A",
        },
        note=note,
    )


BENCH = Bench(
    page=90,
    title="Time Delay",
    runs=[
        _timing(
            "k_tenth",
            "0.1",
            "6",
            [
                Claim("delay_measured", "delay", within=0.07, unit="s",
                      note="the page's R_1 C_0 / (2K) is 5 s. The circuit is 5% "
                      "short of it, as the start-up diode drop, the ramp ending at "
                      "R_5 K E / R_1 and the wiper's 0.9 kOhm predict (4.75 s)"),
                Claim("coil_reset", 0, within=1e-5, absolute=True, unit="A",
                      note="reset: the coil's diode is reverse biased by S at "
                      "7.8 V, and nothing flows"),
            ],
            "The switch is open (reset) until 0.1 s and closed after. R_7 at K = "
            "0.1. Pull-in is the coil current crossing 4.5 mA, and the delay is "
            "counted from the switch closing.",
        ),
        _timing(
            "k_half",
            "0.5",
            "1.5",
            [
                Claim("delay_measured", 0.886, within=0.02, unit="s",
                      note="against the program's own estimate (`shortfall`), not "
                      "the page's 1 s: the ramp's end at R_5 K E / R_1 and the "
                      "wiper's 2.5 kOhm cost 11% here"),
            ],
            "R_7 at K = 0.5, where the page's formula gives 1 s.",
        ),
    ],
)
