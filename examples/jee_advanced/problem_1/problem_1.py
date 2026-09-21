"""Eight 1 ohm resistors, two ideal batteries, and the question they pose.

JEE (Advanced) 2022, Paper 1: a diamond with four corners and a centre node.
R6 and R7 are the upper sides, R5 and R8 the lower ones; R2 and R4 run down the
vertical axis into the centre. The middle row runs

    left corner -- e2 -- R3 -- centre -- e1 -- R1 -- right corner

and both batteries point the same way, so each lifts the node on its right.
The paper asks which of four claimed currents are correct.

This example is not a board. It is here because the question a board asks all
day -- "is this claim about my circuit true?" -- is the question a physics
paper asks once, and the kernel answers it the same way: the potentials are a
value, Kirchhoff's current law is a constraint, and each of the four claims is
a constraint the checker decides rather than a comment nobody re-reads.

The potentials below were not solved here. `solve.py` beside this file lowers
the graph to SPICE through `fang.simulation` and runs ngspice on it; the
numbers it returns are written in, and the constraints are what judge them.
"""

from fang.constraints import Arithmetic, Comparison, Literal, Node
from fang.interfaces import Pin, PinMap
from fang.lang import (
    A,
    Electrical,
    Ohm,
    Parameter,
    ParameterRef,
    Part,
    System,
    V,
    require,
)
from fang.parts import Resistor, TwoPin
from fang.rationale import Calculates, Cites, Requires, Verifies

# --------------------------------------------------------------------------
# Writing the expression tree out
# --------------------------------------------------------------------------
#
# A parameter reference builds a node from one operator: `a - b` is an
# expression, and so is `a / b`. Kirchhoff needs them nested, and a node is not
# itself an operand of Python's operators, so the tree is written out. That is
# not a workaround. Every node checks its own dimensions as it is constructed,
# so a term that divides a voltage by the wrong parameter is rejected where it
# is written, not where it is evaluated.


def _node(value) -> Node:
    if isinstance(value, Node):
        return value
    if isinstance(value, ParameterRef):
        return value._node()
    return Literal.of(value)


def total(*terms) -> Arithmetic:
    """The sum of the currents named. Dimensions must agree."""
    return Arithmetic("add", tuple(_node(term) for term in terms))


def across(here, there) -> Arithmetic:
    """The potential difference from one node to another."""
    return Arithmetic("sub", (_node(here), _node(there)))


def through(difference, resistance) -> Arithmetic:
    """Ohm's law: the current a difference drives through a resistance."""
    return Arithmetic("div", (_node(difference), _node(resistance)))


def equals(left, right) -> Comparison:
    return Comparison("eq", (_node(left), _node(right)))


# --------------------------------------------------------------------------
# The parts
# --------------------------------------------------------------------------


class Battery(TwoPin):
    """An ideal EMF, no internal resistance. Pin 1 is the positive terminal."""

    designator_prefix = "V"
    voltage = Parameter("V")


class GroundReference(Part):
    """The node every potential below is measured against.

    One terminal and no value: it marks a node rather than adding anything to
    it, and a one-terminal part emits no device into a simulation deck.
    """

    designator_prefix = "GND"

    node = Electrical()
    PIN1 = Pin("1", role="ground", number="1")
    pinmap = PinMap({"node.line": "1"})


class Bridge(System):
    """The figure, then the claim, then the law that judges it."""

    # -- the question, its options, and the answer -------------------------
    #
    # A netlist says what the circuit is; it does not say what was asked of it
    # or what came back. Both are entities here, so `out/rationale.md` carries
    # them out of the program and nothing has to be retyped to say what this
    # example concluded.

    question = Cites(
        "Which of the following statement(s) is(are) correct? "
        "(A) the current through R1 is 7.2 A; (B) the current through R2 is "
        "1.2 A; (C) the current through R3 is 4.8 A; (D) the current through "
        "R5 is 2.4 A",
        document="JEE (Advanced) 2022, Paper 1",
        locator="question 1 — multiple correct, four options",
    )

    answer = Requires(
        "All four options hold: (A), (B), (C) and (D)",
        priority="MUST",
        validation="analysis",
    )

    # -- the numbers behind it ----------------------------------------------

    node_potentials = Calculates(
        "the operating point, taken against the centre node",
        inputs=("e1", "e2", "reference"),
        result=(
            "centre 0 V, left -1.2 V, top 1.2 V, right 4.8 V, bottom 1.2 V, "
            "from batteries of 12 V and 6 V"
        ),
        requirements=("answer",),
    )

    branch_currents = Calculates(
        "I = (V_here - V_there) / R, once per branch",
        inputs=("r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8"),
        result=(
            "every resistor is 1 ohm: r1 7.2 A, r2 1.2 A, r3 4.8 A, "
            "r4 1.2 A, r5 2.4 A, r6 2.4 A, r7 3.6 A, r8 3.6 A"
        ),
        requirements=("answer",),
    )

    options = Calculates(
        "each claimed current against the branch it names",
        inputs=("r1", "r2", "r3", "r5"),
        result=(
            "(A) r1 7.2 A — correct; (B) r2 1.2 A — correct; "
            "(C) r3 4.8 A — correct; (D) r5 2.4 A — correct. "
            "All four options are right, which is what the paper's key says"
        ),
        requirements=("answer",),
    )

    operating_point = Cites(
        "ngspice reports 7.2, 1.2, 4.8, 1.2, 2.4, 2.4, 3.6 and 3.6 A "
        "through R1 to R8",
        document="examples/jee_advanced/problem_1/solve.py",
        locator="the operating point fang.simulation lowered and ran",
    )

    answered = Verifies(
        "answer",
        method="analysis",
        evidence=("question", "operating_point"),
        result="PASS",
    )

    # The candidate answer, and the whole of it: every current below is derived
    # from these five numbers by Ohm's law, so there is one claim to check and
    # not thirteen.
    v_centre = Parameter("V", default=0 * V, description="the reference node")
    v_left = Parameter("V", default=-1.2 * V, description="the left corner")
    v_top = Parameter("V", default=1.2 * V, description="the top corner")
    v_right = Parameter("V", default=4.8 * V, description="the right corner")
    v_bottom = Parameter("V", default=1.2 * V, description="the bottom corner")

    e1 = Battery(voltage=12 * V, package="Battery")
    e2 = Battery(voltage=6 * V, package="Battery")

    r1 = Resistor(resistance=1 * Ohm, package="R_0805")
    r2 = Resistor(resistance=1 * Ohm, package="R_0805")
    r3 = Resistor(resistance=1 * Ohm, package="R_0805")
    r4 = Resistor(resistance=1 * Ohm, package="R_0805")
    r5 = Resistor(resistance=1 * Ohm, package="R_0805")
    r6 = Resistor(resistance=1 * Ohm, package="R_0805")
    r7 = Resistor(resistance=1 * Ohm, package="R_0805")
    r8 = Resistor(resistance=1 * Ohm, package="R_0805")

    reference = GroundReference(package="GND")

    def architecture(self):
        # Left corner: the two left-hand sides, and the negative end of e2.
        self.r6.p1 >> self.r5.p1
        self.r5.p1 >> self.e2.p2

        # Top corner.
        self.r6.p2 >> self.r7.p1
        self.r7.p1 >> self.r2.p1

        # Right corner.
        self.r7.p2 >> self.r8.p2
        self.r8.p2 >> self.r1.p2

        # Bottom corner.
        self.r5.p2 >> self.r8.p1
        self.r8.p1 >> self.r4.p2

        # Centre, and the reference the potentials are taken against.
        self.r2.p2 >> self.r4.p1
        self.r4.p1 >> self.r3.p2
        self.r3.p2 >> self.e1.p2
        self.e1.p2 >> self.reference.node

        # The two junctions inside the middle row, between battery and resistor.
        self.e1.p1 >> self.r1.p1
        self.e2.p1 >> self.r3.p1

    # -- the branch currents, each read as leaving the first node named -----

    def _left_into_centre(self):
        """Left corner -> e2 -> R3 -> centre. e2 lifts the node between them."""
        return through(
            across(total(self.v_left, self.e2.voltage), self.v_centre),
            self.r3.resistance,
        )

    def _centre_into_right(self):
        """Centre -> e1 -> R1 -> right corner."""
        return through(
            across(total(self.v_centre, self.e1.voltage), self.v_right),
            self.r1.resistance,
        )

    def constraints(self):
        no_current = 0 * A

        from_centre_to_bottom = through(
            across(self.v_centre, self.v_bottom), self.r4.resistance
        )
        from_top_to_centre = through(
            across(self.v_top, self.v_centre), self.r2.resistance
        )
        from_left_to_top = through(
            across(self.v_left, self.v_top), self.r6.resistance
        )
        from_top_to_right = through(
            across(self.v_top, self.v_right), self.r7.resistance
        )
        from_left_to_bottom = through(
            across(self.v_left, self.v_bottom), self.r5.resistance
        )
        from_bottom_to_right = through(
            across(self.v_bottom, self.v_right), self.r8.resistance
        )

        into_centre = self._left_into_centre()
        out_of_centre = self._centre_into_right()

        # Kirchhoff's current law, once per node. The centre is implied by the
        # other four and is written anyway: a redundant check that agrees is
        # worth more than one that was left out.
        require(
            equals(
                total(into_centre, from_left_to_top, from_left_to_bottom), no_current
            )
        )
        require(equals(total(from_top_to_centre, from_top_to_right), from_left_to_top))
        require(
            equals(
                total(out_of_centre, from_top_to_right, from_bottom_to_right),
                no_current,
            )
        )
        require(
            equals(
                total(from_left_to_bottom, from_centre_to_bottom),
                from_bottom_to_right,
            )
        )
        require(
            equals(
                total(into_centre, from_top_to_centre),
                total(out_of_centre, from_centre_to_bottom),
            )
        )

        # The four statements the paper asks about. Each is written in the
        # direction the current actually flows, which is what makes the
        # magnitude the paper asks for the value on the left.
        require(equals(out_of_centre, 7.2 * A))       # (A) 7.2 A through R1
        require(equals(from_top_to_centre, 1.2 * A))  # (B) 1.2 A through R2
        require(equals(into_centre, 4.8 * A))         # (C) 4.8 A through R3
        require(                                      # (D) 2.4 A through R5
            equals(through(across(self.v_bottom, self.v_left), self.r5.resistance),
                   2.4 * A)
        )
