"""An a.c.-coupled non-inverting amplifier, and the two numbers asked of it.

The question is the one every textbook asks about this figure: "what is the
input impedance, and what is Av?" Both answers are midband answers, and that
is the whole of the problem -- neither number is a property of the resistors
alone. They are properties of which resistors return to an a.c. ground, and
which nodes are a.c. grounds is set by the four capacitors.

The figure, node by node:

    the input    a .1 uF from the source onto the + input
    the bias     220 k from the + input back to a bias node, 100 k beside it,
                 and at that node 220 k to ground with .5 uF across it
    the gain     30 k from the output to the - input, 2 k from there to
                 ground through 1 uF
    the output   .2 uF into a 12 k load

Like the two `jee_advanced` examples beside it, this is not a board. It is
here because the answer depends on a reading of the schematic, and a reading
is a decision: `reading` below records which one was taken and what it
rejected, so the two numbers can be read back to their premise instead of
being believed.

The claims are `z_in` and `a_v`. The four checks under them are what earns
them: each capacitor's reactance at the bottom of the claimed band, against
the resistance it sits beside. Move a capacitor by a decade and the answers do
not quietly stay true -- a check fails and says which one.

Both claims are limits, and neither was solved here. `solve.py` beside this
file lowers the graph to SPICE through `fang.simulation` and sweeps it in
ngspice, which is what a claim about a band asks for; the run agrees with both
numbers and shows how fast they are approached.
"""

from fang.constraints import Arithmetic, Comparison, Literal, Node
from fang.interfaces import AnalogIn, AnalogOut, Pin, PinMap
from fang.lang import (
    Electrical,
    Parameter,
    ParameterRef,
    Part,
    System,
    UnitLiteral,
    kHz,
    kOhm,
    require,
    uF,
)
from fang.parts import Capacitor, Resistor, TestPoint
from fang.rationale import Calculates, Chooses, Cites, Requires, Verifies

#: A dimensionless literal, so a gain is a quantity like every other number.
ratio = UnitLiteral("1")

#: Written out to the precision a Decimal keeps, because the constraints are
#: evaluated in decimal and a binary float never reaches a quantity.
TWO_PI = ratio("6.283185307179586")


# --------------------------------------------------------------------------
# Writing the expression tree out
# --------------------------------------------------------------------------
#
# A parameter reference builds a node from one operator, and a node is not
# itself an operand of Python's operators, so anything nested is written out.
# That is not a workaround. Every node checks its own dimensions as it is
# constructed, so 1 / (2*pi*f*C) is an impedance where it is written or it is
# rejected there -- the reciprocal of a frequency times a capacitance is an
# ohm, and nothing downstream has to re-check that.


def _node(value) -> Node:
    if isinstance(value, Node):
        return value
    if isinstance(value, ParameterRef):
        return value._node()
    return Literal.of(value)


def total(*terms) -> Arithmetic:
    """The sum of the terms named. Dimensions must agree."""
    return Arithmetic("add", tuple(_node(term) for term in terms))


def product(*terms) -> Arithmetic:
    """The product of the terms named."""
    return Arithmetic("mul", tuple(_node(term) for term in terms))


def over(numerator, denominator) -> Arithmetic:
    return Arithmetic("div", (_node(numerator), _node(denominator)))


def parallel(one, other) -> Arithmetic:
    """Two impedances side by side: the product over the sum."""
    return over(product(one, other), total(one, other))


def reactance(capacitance, frequency) -> Arithmetic:
    """1 / (2*pi*f*C): what a capacitor is worth, in ohms, at one frequency."""
    return over(1 * ratio, product(TWO_PI, frequency, capacitance))


def equals(left, right) -> Comparison:
    return Comparison("eq", (_node(left), _node(right)))


def at_most(left, right) -> Comparison:
    return Comparison("le", (_node(left), _node(right)))


def a_tenth_of(value) -> Arithmetic:
    """The margin that makes "a short" and "an open" worth saying."""
    return over(value, 10 * ratio)


# --------------------------------------------------------------------------
# The parts
# --------------------------------------------------------------------------


class OpAmp(Part):
    """An ideal op amp: two analog inputs, one analog output, no rails.

    The figure draws no supplies, so the part has none. The pin numbers are the
    single-op-amp 8-pin pinout an engineer expects -- 2, 3 and 6 -- and the
    package is the one a real part would arrive in, but nothing here claims a
    vendor: no part has been selected, and inventing one would be exactly the
    unearned certainty the kernel exists to prevent.
    """

    designator_prefix = "U"

    inverting = AnalogIn()
    non_inverting = AnalogIn()
    output = AnalogOut()

    IN_MINUS = Pin("IN-", role="analog", number="2")
    IN_PLUS = Pin("IN+", role="analog", number="3")
    OUT = Pin("OUT", role="analog", number="6")

    pinmap = PinMap(
        {
            "inverting.signal": "IN-",
            "non_inverting.signal": "IN+",
            "output.signal": "OUT",
        }
    )


class GroundReference(Part):
    """The node every claim below is measured against.

    One terminal and no value: it marks a node rather than adding anything to
    it.
    """

    designator_prefix = "GND"

    node = Electrical()
    PIN1 = Pin("1", role="ground", number="1")
    pinmap = PinMap({"node.line": "1"})


class NonInvertingAmp(System):
    """The figure, then the two claims, then what makes them true."""

    # -- the question, the reading it needed, and the answer ----------------

    question = Cites(
        "What is the input impedance in Figure 4.44? What is Av?",
        document="problem set, question 40",
        locator="figure 4.44 -- the circuit as drawn, no frequency given",
    )

    reading = Chooses(
        "Where does the upper 220 k return to?",
        selected=(
            "to the bias node, beside the 100 k, so both land on the + input "
            "at one end and on the .5 uF's node at the other"
        ),
        alternatives=[
            {
                "reading": "to the op amp output, as a bootstrap",
                "reason": (
                    "the figure's top wire comes down to the left of the "
                    "symbol, onto the + input, not to the output on its right"
                ),
            },
            {
                "reading": "to a supply rail, making the two 220 k a divider",
                "reason": (
                    "no rail is drawn anywhere in the figure, and the lower "
                    "220 k already returns the + input's bias current to "
                    "ground on its own"
                ),
            },
        ],
        rationale=(
            "under this reading both the 220 k and the 100 k run from the "
            "input node to a node the .5 uF holds at a.c. ground, which puts "
            "them in parallel across the input",
            "the answer is a reading of the drawing before it is arithmetic, "
            "so the reading is recorded rather than assumed",
        ),
    )

    answer = Requires(
        "The input impedance is 68.75 kOhm and Av is 16, non-inverting",
        priority="MUST",
        validation="analysis",
    )

    # -- the numbers behind it ----------------------------------------------

    input_impedance = Calculates(
        "Zin = 220k || 100k, both returning to the a.c. ground the .5 uF makes",
        inputs=("r_bias_upper", "r_series", "c_bias"),
        result=(
            "68.75 kOhm. The lower 220 k does not appear: the .5 uF is across "
            "it, and the op amp's own + input draws nothing"
        ),
        requirements=("answer",),
    )

    voltage_gain = Calculates(
        "Av = 1 + Rf/Rg, with the 1 uF shorting the 2 k leg to ground",
        inputs=("r_feedback", "r_gain", "c_gain"),
        result=(
            "1 + 30k/2k = 16, or +24 dB, non-inverting. At d.c. the 1 uF is an "
            "open and the stage falls to unity gain, which is what keeps the "
            "output offset small. The 12 k load does not enter it"
        ),
        requirements=("answer",),
    )

    corner_frequencies = Calculates(
        "f = 1 / (2*pi*R*C), once per capacitor",
        inputs=("c_in", "c_bias", "c_gain", "c_out"),
        result=(
            "23.1 Hz at the input, 1.4 Hz at the bias node, 79.6 Hz at the "
            "gain leg, 66.3 Hz into the load. The 1 uF against 2 k is the "
            "highest of the four, so the midband both answers are claimed "
            "over starts about a decade above it"
        ),
        requirements=("answer",),
    )

    answered = Verifies(
        "answer",
        method="analysis",
        evidence=("question",),
        result="PASS",
    )

    # -- the claims, and the band they are claimed over ---------------------

    z_in = Parameter(
        "Ohm",
        default=68.75 * kOhm,
        description="what the source sees, looking in through the .1 uF",
    )
    a_v = Parameter(
        "1",
        default=16 * ratio,
        description="the midband voltage gain, output over input",
    )
    midband = Parameter(
        "Hz",
        default=1 * kHz,
        description="the bottom of the band both answers are claimed over",
    )

    # -- the figure ---------------------------------------------------------

    source = TestPoint(package="TestPoint_Pad_D1.0mm")
    c_in = Capacitor(capacitance=0.1 * uF, package="C_0805")

    # The two resistors that meet at the + input and leave together. Their far
    # end is the bias node, which the .5 uF holds at a.c. ground.
    r_bias_upper = Resistor(resistance=220 * kOhm, package="R_0805")
    r_series = Resistor(resistance=100 * kOhm, package="R_0805")

    # The bias node itself: the d.c. return for the + input, bypassed.
    r_bias_lower = Resistor(resistance=220 * kOhm, package="R_0805")
    c_bias = Capacitor(capacitance=0.5 * uF, package="C_0805")

    # The feedback network, and the leg that sets the gain above 1.
    r_feedback = Resistor(resistance=30 * kOhm, package="R_0805")
    r_gain = Resistor(resistance=2 * kOhm, package="R_0805")
    c_gain = Capacitor(capacitance=1 * uF, package="C_0805")

    # The output, and what it drives.
    c_out = Capacitor(capacitance=0.2 * uF, package="C_0805")
    r_load = Resistor(resistance=12 * kOhm, package="R_0805")

    amp = OpAmp(package="SOIC-8")
    reference = GroundReference(package="GND")

    def architecture(self):
        # The input node: the coupling capacitor lands on the + input, and the
        # two bias resistors leave from there.
        self.source.probe >> self.c_in.p1
        self.c_in.p2 >> self.amp.non_inverting.signal
        self.amp.non_inverting.signal >> self.r_bias_upper.p1
        self.r_bias_upper.p1 >> self.r_series.p1

        # The bias node: both of them arrive, the 220 k goes on to ground, and
        # the .5 uF is across it.
        self.r_bias_upper.p2 >> self.r_series.p2
        self.r_series.p2 >> self.r_bias_lower.p1
        self.r_bias_lower.p1 >> self.c_bias.p1

        # The - input: the feedback resistor and the gain leg.
        self.amp.inverting.signal >> self.r_feedback.p1
        self.r_feedback.p1 >> self.r_gain.p1
        self.r_gain.p2 >> self.c_gain.p1

        # The output node, and the load beyond the coupling capacitor.
        self.amp.output.signal >> self.r_feedback.p2
        self.r_feedback.p2 >> self.c_out.p1
        self.c_out.p2 >> self.r_load.p1

        # Ground, and the reference every claim is measured against.
        self.r_bias_lower.p2 >> self.c_bias.p2
        self.c_bias.p2 >> self.c_gain.p2
        self.c_gain.p2 >> self.r_load.p2
        self.r_load.p2 >> self.reference.node

    def constraints(self):
        # The first answer. Both resistors run from the input node to a node
        # the .5 uF holds at a.c. ground, so they are in parallel across it,
        # and the op amp's own + input draws nothing worth subtracting.
        require(
            equals(
                self.z_in,
                parallel(self.r_bias_upper.resistance, self.r_series.resistance),
            )
        )

        # The second. The 1 uF puts the bottom of the 2 k on a.c. ground, which
        # is what makes the gain 1 + Rf/Rg rather than 1.
        require(
            equals(
                self.a_v,
                total(
                    1 * ratio,
                    over(self.r_feedback.resistance, self.r_gain.resistance),
                ),
            )
        )

        # And what earns both: at the bottom of the claimed band, every
        # capacitor is worth at most a tenth of the resistance beside it, which
        # is what "treat it as a short" means when it is written down rather
        # than assumed. The gain leg is the tightest of the four.
        require(
            at_most(
                reactance(self.c_in.capacitance, self.midband),
                a_tenth_of(self.z_in),
            )
        )
        require(
            at_most(
                reactance(self.c_bias.capacitance, self.midband),
                a_tenth_of(self.r_bias_lower.resistance),
            )
        )
        require(
            at_most(
                reactance(self.c_gain.capacitance, self.midband),
                a_tenth_of(self.r_gain.resistance),
            )
        )
        require(
            at_most(
                reactance(self.c_out.capacitance, self.midband),
                a_tenth_of(self.r_load.resistance),
            )
        )
