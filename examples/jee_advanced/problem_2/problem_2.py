"""Ten resistors, one 6.5 V battery, and the single number the paper asks for.

JEE (Advanced) 2015, question 13: "In the following circuit, the current
through the resistor R (= 2 ohm) is I Amperes. The value of I is". The figure
is a square, three spokes meeting at a centre node, two legs down to the bottom
rail, and R in series with the battery feeding the whole thing:

    the square    r_top (1) and r_bottom (10) across, r_left (6) and
                  r_right (2) down the sides
    the spokes    r_top_left_spoke (2), r_top_right_spoke (8) and
                  r_bottom_right_spoke (4), all meeting at the centre
    the legs      r_left_leg (12) and r_right_leg (4), from the two lower
                  corners to the bottom rail
    in series     r (2), between the battery and the top left corner

Like `jee_advanced` beside it, this is not a board. It is here because the
question is the one a board asks all day -- "is this claim about my circuit
true?" -- and the kernel answers it the same way: the potentials are a value,
Kirchhoff's current law is a constraint, and the paper's claim is a constraint
the checker decides rather than a comment nobody re-reads.

Two of the ten resistors turn out to carry nothing at all, and that is the
whole trick of the question. Those two are claimed here as well, because a fact
that explains the answer is worth checking beside it.

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


class Ladder(System):
    """The figure, then the claim, then the law that judges it."""

    # -- the question, and the answer it asks for --------------------------
    #
    # A netlist says what the circuit is; it does not say what was asked of it
    # or what came back. Both are entities here, so `out/rationale.md` carries
    # them out of the program and nothing has to be retyped to say what this
    # example concluded.

    question = Cites(
        "In the following circuit, the current through the resistor "
        "R (= 2 ohm) is I Amperes. The value of I is",
        document="JEE (Advanced) 2015",
        locator="question 13 — an integer answer, no options offered",
    )

    answer = Requires(
        "The current I through R (= 2 ohm) is 1 A",
        priority="MUST",
        validation="analysis",
    )

    # -- the numbers behind it ----------------------------------------------

    node_potentials = Calculates(
        "the operating point, taken against the bottom rail",
        inputs=("battery", "reference"),
        result=(
            "top left 4.5 V, top right 4 V, centre 4 V, "
            "bottom left 3 V, bottom right 3 V, bottom rail 0 V"
        ),
        requirements=("answer",),
    )

    branch_currents = Calculates(
        "I = (V_here - V_there) / R, once per branch",
        inputs=(
            "r",
            "r_top",
            "r_left",
            "r_right",
            "r_bottom",
            "r_top_left_spoke",
            "r_top_right_spoke",
            "r_bottom_right_spoke",
            "r_left_leg",
            "r_right_leg",
        ),
        result=(
            "r (2 ohm) 1 A, r_top (1 ohm) 0.5 A, r_left (6 ohm) 0.25 A, "
            "r_right (2 ohm) 0.5 A, r_bottom (10 ohm) 0 A, "
            "r_top_left_spoke (2 ohm) 0.25 A, r_top_right_spoke (8 ohm) 0 A, "
            "r_bottom_right_spoke (4 ohm) 0.25 A, "
            "r_left_leg (12 ohm) 0.25 A, r_right_leg (4 ohm) 0.75 A"
        ),
        requirements=("answer",),
    )

    balanced_branches = Calculates(
        "a branch between two nodes at equal potential carries no current",
        inputs=("r_bottom", "r_top_right_spoke"),
        result=(
            "r_bottom (10 ohm) bridges 3 V to 3 V and r_top_right_spoke "
            "(8 ohm) bridges 4 V to 4 V, so both carry 0 A and what is left "
            "is series-parallel — which is why I is a whole ampere"
        ),
        requirements=("answer",),
    )

    operating_point = Cites(
        "ngspice reports 1.000000 A through R1, the 2 ohm the question names",
        document="examples/jee_advanced/problem_2/solve.py",
        locator="the operating point fang.simulation lowered and ran",
    )

    answered = Verifies(
        "answer",
        method="analysis",
        evidence=("question", "operating_point"),
        result="PASS",
    )

    # The candidate answer, and the whole of it: every current below is derived
    # from these six numbers by Ohm's law, so there is one claim to check and
    # not ten.
    v_ground = Parameter("V", default=0 * V, description="the bottom rail")
    v_top_left = Parameter("V", default=4.5 * V, description="R's far end")
    v_top_right = Parameter("V", default=4 * V, description="the top right corner")
    v_centre = Parameter("V", default=4 * V, description="where the spokes meet")
    v_bottom_left = Parameter("V", default=3 * V, description="the bottom left corner")
    v_bottom_right = Parameter("V", default=3 * V, description="the bottom right corner")

    battery = Battery(voltage=6.5 * V, package="Battery")

    # The resistor the paper asks about, in series with the battery.
    r = Resistor(resistance=2 * Ohm, package="R_0805")

    # The four sides of the square.
    r_top = Resistor(resistance=1 * Ohm, package="R_0805")
    r_left = Resistor(resistance=6 * Ohm, package="R_0805")
    r_right = Resistor(resistance=2 * Ohm, package="R_0805")
    r_bottom = Resistor(resistance=10 * Ohm, package="R_0805")

    # The three spokes into the centre node.
    r_top_left_spoke = Resistor(resistance=2 * Ohm, package="R_0805")
    r_top_right_spoke = Resistor(resistance=8 * Ohm, package="R_0805")
    r_bottom_right_spoke = Resistor(resistance=4 * Ohm, package="R_0805")

    # The two legs from the lower corners down to the bottom rail.
    r_left_leg = Resistor(resistance=12 * Ohm, package="R_0805")
    r_right_leg = Resistor(resistance=4 * Ohm, package="R_0805")

    reference = GroundReference(package="GND")

    def architecture(self):
        # The battery's positive terminal, and R in series with it.
        self.battery.p1 >> self.r.p1

        # Top left corner: R's far end, two sides of the square, one spoke.
        self.r.p2 >> self.r_top.p1
        self.r_top.p1 >> self.r_left.p1
        self.r_left.p1 >> self.r_top_left_spoke.p1

        # Top right corner.
        self.r_top.p2 >> self.r_right.p1
        self.r_right.p1 >> self.r_top_right_spoke.p1

        # The centre, where the three spokes meet and nothing else does.
        self.r_top_left_spoke.p2 >> self.r_top_right_spoke.p2
        self.r_top_right_spoke.p2 >> self.r_bottom_right_spoke.p1

        # Bottom left corner.
        self.r_left.p2 >> self.r_bottom.p1
        self.r_bottom.p1 >> self.r_left_leg.p1

        # Bottom right corner.
        self.r_right.p2 >> self.r_bottom.p2
        self.r_bottom.p2 >> self.r_bottom_right_spoke.p2
        self.r_bottom_right_spoke.p2 >> self.r_right_leg.p1

        # The bottom rail, and the reference the potentials are taken against.
        self.r_left_leg.p2 >> self.r_right_leg.p2
        self.r_right_leg.p2 >> self.battery.p2
        self.battery.p2 >> self.reference.node

    # -- the branch currents, each read as leaving the first node named -----

    def _through_r(self):
        """Bottom rail -> battery -> R -> top left corner. This is I."""
        return through(
            across(total(self.v_ground, self.battery.voltage), self.v_top_left),
            self.r.resistance,
        )

    def constraints(self):
        no_current = 0 * A

        into_top_left = self._through_r()

        top_left_to_top_right = through(
            across(self.v_top_left, self.v_top_right), self.r_top.resistance
        )
        top_left_to_bottom_left = through(
            across(self.v_top_left, self.v_bottom_left), self.r_left.resistance
        )
        top_left_to_centre = through(
            across(self.v_top_left, self.v_centre),
            self.r_top_left_spoke.resistance,
        )
        top_right_to_centre = through(
            across(self.v_top_right, self.v_centre),
            self.r_top_right_spoke.resistance,
        )
        top_right_to_bottom_right = through(
            across(self.v_top_right, self.v_bottom_right), self.r_right.resistance
        )
        centre_to_bottom_right = through(
            across(self.v_centre, self.v_bottom_right),
            self.r_bottom_right_spoke.resistance,
        )
        bottom_left_to_bottom_right = through(
            across(self.v_bottom_left, self.v_bottom_right), self.r_bottom.resistance
        )
        bottom_left_to_ground = through(
            across(self.v_bottom_left, self.v_ground), self.r_left_leg.resistance
        )
        bottom_right_to_ground = through(
            across(self.v_bottom_right, self.v_ground), self.r_right_leg.resistance
        )

        # Kirchhoff's current law, once per node. The bottom rail is implied by
        # the other five and is written anyway: a redundant check that agrees is
        # worth more than one that was left out.
        require(
            equals(
                into_top_left,
                total(
                    top_left_to_top_right,
                    top_left_to_bottom_left,
                    top_left_to_centre,
                ),
            )
        )
        require(
            equals(
                top_left_to_top_right,
                total(top_right_to_centre, top_right_to_bottom_right),
            )
        )
        require(
            equals(
                total(top_left_to_centre, top_right_to_centre),
                centre_to_bottom_right,
            )
        )
        require(
            equals(
                top_left_to_bottom_left,
                total(bottom_left_to_bottom_right, bottom_left_to_ground),
            )
        )
        require(
            equals(
                total(
                    top_right_to_bottom_right,
                    centre_to_bottom_right,
                    bottom_left_to_bottom_right,
                ),
                bottom_right_to_ground,
            )
        )
        require(
            equals(
                total(bottom_left_to_ground, bottom_right_to_ground), into_top_left
            )
        )

        # The answer the paper asks for, written in the direction the current
        # actually flows, which is what makes the magnitude it wants the value
        # on the left.
        require(equals(into_top_left, 1 * A))  # I = 1 A through R

        # Not asked, and the reason the answer is a round number: the two
        # resistors that bridge equal potentials carry nothing, which takes the
        # 10 ohm and the 8 ohm out of the circuit entirely.
        require(equals(bottom_left_to_bottom_right, no_current))  # the 10 ohm
        require(equals(top_right_to_centre, no_current))          # the 8 ohm
