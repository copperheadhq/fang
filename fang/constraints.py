"""Constraints: one registry, one record, and a typed expression language.

Spec: "Exactly One Constraint Registry", "The Constraint Record", and "Typed
Constraint Expressions".

A dimension mismatch is rejected where the expression is written, not carried
into evaluation. Undecided is a third truth value, never a pass and never a
silent failure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, localcontext
from enum import Enum
from fractions import Fraction
from typing import Callable, Mapping, Sequence

from .diagnostics import (
    ELAB_SECOND_REGISTRY,
    UNIT_BAD_EXPONENT,
    UNIT_DIMENSION_MISMATCH,
    error,
)
from .entities import Entity
from .units import DIMENSIONLESS, Dimension, Quantity, _CONTEXT, _decimal_str
from .values import Value, ValueStatus


# --------------------------------------------------------------------------
# Three-valued logic
# --------------------------------------------------------------------------


class Truth(Enum):
    """A three-valued truth. Undecided is a value, not an error and not a null."""

    TRUE = "true"
    FALSE = "false"
    UNDECIDED = "undecided"

    def __and__(self, other: "Truth") -> "Truth":
        if self is Truth.FALSE or other is Truth.FALSE:
            return Truth.FALSE
        if self is Truth.UNDECIDED or other is Truth.UNDECIDED:
            return Truth.UNDECIDED
        return Truth.TRUE

    def __or__(self, other: "Truth") -> "Truth":
        if self is Truth.TRUE or other is Truth.TRUE:
            return Truth.TRUE
        if self is Truth.UNDECIDED or other is Truth.UNDECIDED:
            return Truth.UNDECIDED
        return Truth.FALSE

    def __invert__(self) -> "Truth":
        if self is Truth.UNDECIDED:
            return Truth.UNDECIDED
        return Truth.FALSE if self is Truth.TRUE else Truth.TRUE


class CheckStatus(Enum):
    """How a constraint result surfaces."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"              # an undecided result
    NOT_APPLICABLE = "NOT_APPLICABLE"  # applicability evaluated false


@dataclass(frozen=True)
class Interval:
    """The closed interval an operand covers, in SI base units.

    ``None`` is never used for undecided; an operand that is not known produces
    no interval at all and the evaluator returns ``Truth.UNDECIDED``.
    """

    low: Decimal
    high: Decimal

    @classmethod
    def point(cls, value: Decimal) -> "Interval":
        return cls(value, value)

    @property
    def is_point(self) -> bool:
        return self.low == self.high

    def _combine(self, other: "Interval", op: Callable) -> "Interval":
        with localcontext(_CONTEXT):
            corners = [
                op(a, b)
                for a in (self.low, self.high)
                for b in (other.low, other.high)
            ]
            return Interval(min(corners), max(corners))

    def __add__(self, other: "Interval") -> "Interval":
        with localcontext(_CONTEXT):
            return Interval(self.low + other.low, self.high + other.high)

    def __sub__(self, other: "Interval") -> "Interval":
        with localcontext(_CONTEXT):
            return Interval(self.low - other.high, self.high - other.low)

    def __mul__(self, other: "Interval") -> "Interval":
        return self._combine(other, lambda a, b: a * b)

    def __truediv__(self, other: "Interval") -> "Interval":
        if other.low <= 0 <= other.high:
            raise ZeroDivisionError("divisor interval spans zero")
        return self._combine(other, lambda a, b: a / b)

    def __neg__(self) -> "Interval":
        return Interval(-self.high, -self.low)

    def __abs__(self) -> "Interval":
        if self.low >= 0:
            return self
        if self.high <= 0:
            return Interval(-self.high, -self.low)
        return Interval(Decimal(0), max(-self.low, self.high))

    def power(self, exponent: Fraction) -> "Interval":
        if exponent.denominator != 1:
            raise error(
                UNIT_BAD_EXPONENT, "a fractional exponent is not supported numerically"
            )
        with localcontext(_CONTEXT):
            corners = [self.low ** int(exponent), self.high ** int(exponent)]
            if self.low <= 0 <= self.high and int(exponent) % 2 == 0:
                corners.append(Decimal(0))
            return Interval(min(corners), max(corners))


# --------------------------------------------------------------------------
# Expression nodes
# --------------------------------------------------------------------------

#: A resolver answers what an entity attribute currently holds.
Resolver = Callable[[str, str], Value | None]


class Node:
    """A node of a typed expression tree. Every node has a dimension."""

    dimension: Dimension

    def evaluate(self, resolve: Resolver) -> Interval | Truth:
        raise NotImplementedError

    def as_dict(self) -> dict:
        raise NotImplementedError

    def references(self) -> tuple[str, ...]:
        return ()


@dataclass(frozen=True)
class Literal(Node):
    """A quantity, number, string, or boolean."""

    quantity: Quantity | None = None
    number: Decimal | None = None
    text: str | None = None
    boolean: bool | None = None

    def __post_init__(self) -> None:
        supplied = [x for x in (self.quantity, self.number, self.text, self.boolean) if x is not None]
        if len(supplied) != 1:
            raise ValueError("a literal carries exactly one of quantity, number, text, boolean")
        object.__setattr__(
            self,
            "dimension",
            self.quantity.dimension if self.quantity is not None else DIMENSIONLESS,
        )

    @classmethod
    def of(cls, value) -> "Literal":
        if isinstance(value, Quantity):
            return cls(quantity=value)
        if isinstance(value, bool):
            return cls(boolean=value)
        if isinstance(value, str):
            return cls(text=value)
        return cls(number=Decimal(str(value)))

    def evaluate(self, resolve: Resolver) -> Interval | Truth:
        if self.quantity is not None:
            low, high = self.quantity.interval()
            return Interval(low, high)
        if self.number is not None:
            return Interval.point(self.number)
        if self.boolean is not None:
            return Truth.TRUE if self.boolean else Truth.FALSE
        raise TypeError("a string literal has no numeric interval")

    def as_dict(self) -> dict:
        if self.quantity is not None:
            return {"node": "literal", "quantity": self.quantity.as_dict()}
        if self.number is not None:
            return {"node": "literal", "number": _decimal_str(self.number)}
        if self.text is not None:
            return {"node": "literal", "string": self.text}
        return {"node": "literal", "boolean": self.boolean}


@dataclass(frozen=True)
class Ref(Node):
    """An entity identifier and an attribute path.

    The attribute's dimension is declared here, because a dimension mismatch must
    be catchable when the expression is written rather than when it is evaluated.
    """

    ref: str
    attr: str
    attr_dimension: Dimension = DIMENSIONLESS

    def __post_init__(self) -> None:
        object.__setattr__(self, "dimension", self.attr_dimension)

    def evaluate(self, resolve: Resolver) -> Interval | Truth:
        value = resolve(self.ref, self.attr)
        # An operand whose value status is unknown makes the comparison undecided.
        if value is None or not value.known or value.quantity is None:
            return Truth.UNDECIDED
        low, high = value.quantity.interval()
        return Interval(low, high)

    def references(self) -> tuple[str, ...]:
        return (self.ref,)

    def as_dict(self) -> dict:
        return {
            "node": "ref",
            "ref": self.ref,
            "attr": self.attr,
            "dimension": self.attr_dimension.as_list(),
        }


ARITHMETIC_OPS = ("add", "sub", "mul", "div", "pow", "neg", "abs", "min", "max")
COMPARISON_OPS = ("lt", "le", "eq", "ne", "ge", "gt")
LOGICAL_OPS = ("and", "or", "not")


@dataclass(frozen=True)
class Arithmetic(Node):
    op: str
    args: tuple[Node, ...]
    exponent: Fraction | None = None

    def __post_init__(self) -> None:
        if self.op not in ARITHMETIC_OPS:
            raise ValueError(f"{self.op!r} is not an arithmetic operator")
        object.__setattr__(self, "dimension", self._check())

    def _check(self) -> Dimension:
        args = self.args
        if self.op in ("add", "sub", "min", "max"):
            # Addition, subtraction, and comparison require equal dimension.
            first = args[0].dimension
            for other in args[1:]:
                if other.dimension != first:
                    raise error(
                        UNIT_DIMENSION_MISMATCH,
                        f"{self.op} requires operands of equal dimension: "
                        f"{first} is not {other.dimension}",
                    )
            return first
        if self.op == "mul":
            result = DIMENSIONLESS
            for arg in args:
                result = result * arg.dimension
            return result
        if self.op == "div":
            result = args[0].dimension
            for arg in args[1:]:
                result = result / arg.dimension
            return result
        if self.op == "pow":
            if self.exponent is None:
                raise error(
                    UNIT_BAD_EXPONENT, "pow carries a dimensionless rational exponent"
                )
            return args[0].dimension ** self.exponent
        # neg, abs
        return args[0].dimension

    def evaluate(self, resolve: Resolver) -> Interval | Truth:
        evaluated = [arg.evaluate(resolve) for arg in self.args]
        if any(e is Truth.UNDECIDED for e in evaluated):
            return Truth.UNDECIDED
        intervals: list[Interval] = evaluated  # type: ignore[assignment]

        if self.op == "add":
            result = intervals[0]
            for other in intervals[1:]:
                result = result + other
            return result
        if self.op == "sub":
            result = intervals[0]
            for other in intervals[1:]:
                result = result - other
            return result
        if self.op == "mul":
            result = intervals[0]
            for other in intervals[1:]:
                result = result * other
            return result
        if self.op == "div":
            result = intervals[0]
            for other in intervals[1:]:
                result = result / other
            return result
        if self.op == "pow":
            return intervals[0].power(self.exponent)
        if self.op == "neg":
            return -intervals[0]
        if self.op == "abs":
            return abs(intervals[0])
        if self.op == "min":
            return Interval(
                min(i.low for i in intervals), min(i.high for i in intervals)
            )
        return Interval(max(i.low for i in intervals), max(i.high for i in intervals))

    def references(self) -> tuple[str, ...]:
        return tuple(r for arg in self.args for r in arg.references())

    def as_dict(self) -> dict:
        out = {"node": "arithmetic", "op": self.op, "args": [a.as_dict() for a in self.args]}
        if self.exponent is not None:
            out["exponent"] = str(self.exponent)
        return out


@dataclass(frozen=True)
class Comparison(Node):
    op: str
    args: tuple[Node, ...]

    def __post_init__(self) -> None:
        if self.op not in COMPARISON_OPS:
            raise ValueError(f"{self.op!r} is not a comparison operator")
        left, right = self.args
        if left.dimension != right.dimension:
            raise error(
                UNIT_DIMENSION_MISMATCH,
                f"{self.op} requires operands of equal dimension: "
                f"{left.dimension} is not {right.dimension}",
            )
        object.__setattr__(self, "dimension", DIMENSIONLESS)

    def evaluate(self, resolve: Resolver) -> Truth:
        left = self.args[0].evaluate(resolve)
        right = self.args[1].evaluate(resolve)
        if left is Truth.UNDECIDED or right is Truth.UNDECIDED:
            return Truth.UNDECIDED

        a: Interval = left   # type: ignore[assignment]
        b: Interval = right  # type: ignore[assignment]

        def decide(all_true: bool, all_false: bool) -> Truth:
            if all_true:
                return Truth.TRUE
            if all_false:
                return Truth.FALSE
            return Truth.UNDECIDED

        if self.op == "lt":
            return decide(a.high < b.low, a.low >= b.high)
        if self.op == "le":
            return decide(a.high <= b.low, a.low > b.high)
        if self.op == "gt":
            return decide(a.low > b.high, a.high <= b.low)
        if self.op == "ge":
            return decide(a.low >= b.high, a.high < b.low)
        disjoint = a.high < b.low or b.high < a.low
        same_point = a.is_point and b.is_point and a.low == b.low
        if self.op == "eq":
            return decide(same_point, disjoint)
        return decide(disjoint, same_point)

    def references(self) -> tuple[str, ...]:
        return tuple(r for arg in self.args for r in arg.references())

    def as_dict(self) -> dict:
        return {"node": "comparison", "op": self.op, "args": [a.as_dict() for a in self.args]}


@dataclass(frozen=True)
class Logical(Node):
    op: str
    args: tuple[Node, ...]

    def __post_init__(self) -> None:
        if self.op not in LOGICAL_OPS:
            raise ValueError(f"{self.op!r} is not a logical operator")
        if self.op == "not" and len(self.args) != 1:
            raise ValueError("not takes one operand")
        object.__setattr__(self, "dimension", DIMENSIONLESS)

    def evaluate(self, resolve: Resolver) -> Truth:
        results = [arg.evaluate(resolve) for arg in self.args]
        truths = [r if isinstance(r, Truth) else Truth.TRUE for r in results]
        if self.op == "not":
            return ~truths[0]
        result = truths[0]
        for other in truths[1:]:
            result = (result & other) if self.op == "and" else (result | other)
        return result

    def references(self) -> tuple[str, ...]:
        return tuple(r for arg in self.args for r in arg.references())

    def as_dict(self) -> dict:
        return {"node": "logical", "op": self.op, "args": [a.as_dict() for a in self.args]}


# -- construction helpers ---------------------------------------------------


def compare(op: str, left: Node, right: Node) -> Comparison:
    return Comparison(op, (left, right))


def le(left: Node, right: Node) -> Comparison:
    return compare("le", left, right)


def ge(left: Node, right: Node) -> Comparison:
    return compare("ge", left, right)


# --------------------------------------------------------------------------
# The constraint record
# --------------------------------------------------------------------------


class ConstraintClass(Enum):
    ELECTRICAL = "electrical"
    PHYSICS = "physics"
    TOPOLOGY = "topology"
    PLACEMENT = "placement"
    ROUTING = "routing"
    MANUFACTURING = "manufacturing"
    SOURCING = "sourcing"
    TESTABILITY = "testability"


class Enforcement(Enum):
    """How a violation is treated, not how bad it is."""

    HARD = "hard"
    SOFT = "soft"
    ADVISORY = "advisory"


class VerificationMethod(Enum):
    ANALYSIS = "analysis"
    SIMULATION = "simulation"
    RULE_CHECK = "rule check"
    INSPECTION = "inspection"
    TEST = "test"


@dataclass(frozen=True)
class Constraint(Entity):
    """One entity kind with one schema, whatever class it belongs to."""

    kind: str = "constraint"
    constraint_class: ConstraintClass = ConstraintClass.ELECTRICAL
    constraint_kind: str = ""
    targets: tuple[str, ...] = ()
    expression: Node | None = None
    applicability: Node | None = None
    enforcement: Enforcement = Enforcement.HARD
    verification_method: VerificationMethod | None = None
    verification_status: CheckStatus = CheckStatus.UNKNOWN
    source: str | None = None

    def __post_init__(self) -> None:
        if not self.constraint_kind:
            raise ValueError("a constraint carries a kind")
        if not self.targets:
            raise ValueError("a constraint carries its targets")
        if self.expression is None:
            raise ValueError("a constraint carries an expression")

    def references(self) -> tuple[str, ...]:
        refs = self.targets + self.expression.references()
        if self.applicability is not None:
            refs += self.applicability.references()
        if self.source is not None:
            refs += (self.source,)
        return refs

    def evaluate(self, resolve: Resolver) -> CheckStatus:
        """Evaluate applicability, then the expression.

        A constraint whose applicability evaluates false is reported as not
        applicable rather than as passing.
        """
        if self.applicability is not None:
            applicable = self.applicability.evaluate(resolve)
            if applicable is Truth.FALSE:
                return CheckStatus.NOT_APPLICABLE
            if applicable is Truth.UNDECIDED:
                return CheckStatus.UNKNOWN

        result = self.expression.evaluate(resolve)
        if not isinstance(result, Truth):
            raise TypeError(
                "a constraint expression evaluates to a truth, not to a quantity"
            )
        if result is Truth.TRUE:
            return CheckStatus.PASS
        if result is Truth.FALSE:
            return CheckStatus.FAIL
        return CheckStatus.UNKNOWN

    def as_dict(self) -> dict:
        out = self._base_dict()
        out.update(
            {
                "class": self.constraint_class.value,
                "constraint_kind": self.constraint_kind,
                "targets": sorted(self.targets),
                "expression": self.expression.as_dict(),
                "enforcement": self.enforcement.value,
                "verification": {"status": self.verification_status.value},
            }
        )
        if self.verification_method is not None:
            out["verification"]["method"] = self.verification_method.value
        if self.applicability is not None:
            out["applicability"] = self.applicability.as_dict()
        if self.source is not None:
            out["source"] = self.source
        return out


class ConstraintRegistry:
    """The one constraint registry for a project.

    Electrical, physics, topology, placement, routing, manufacturing, sourcing,
    and testability constraints are classes within it. A second constraint store
    does not exist; `Projection` below is what a downstream tool gets.
    """

    _live: dict[str, "ConstraintRegistry"] = {}

    def __init__(self, project_id: str) -> None:
        existing = ConstraintRegistry._live.get(project_id)
        if existing is not None:
            raise error(
                ELAB_SECOND_REGISTRY,
                f"project {project_id} already has a constraint registry; "
                "there is exactly one registry per project",
            )
        ConstraintRegistry._live[project_id] = self
        self.project_id = project_id
        self._constraints: dict[str, Constraint] = {}

    @classmethod
    def for_project(cls, project_id: str) -> "ConstraintRegistry":
        """Get the project's registry, creating it only if it does not exist."""
        existing = cls._live.get(project_id)
        return existing if existing is not None else cls(project_id)

    @classmethod
    def release(cls, project_id: str) -> None:
        """Drop the registry for a project. Used when a project is closed."""
        cls._live.pop(project_id, None)

    def add(self, constraint: Constraint) -> Constraint:
        self._constraints[constraint.id] = constraint
        return constraint

    def get(self, id: str) -> Constraint:
        return self._constraints[id]

    def of_class(self, constraint_class: ConstraintClass) -> list[Constraint]:
        return sorted(
            (c for c in self._constraints.values() if c.constraint_class is constraint_class),
            key=lambda c: c.id,
        )

    def targeting(self, entity_id: str) -> list[Constraint]:
        return sorted(
            (c for c in self._constraints.values() if entity_id in c.targets),
            key=lambda c: c.id,
        )

    def __len__(self) -> int:
        return len(self._constraints)

    def __iter__(self):
        return iter(sorted(self._constraints.values(), key=lambda c: c.id))

    def project(self, constraint_id: str, **class_specific) -> "Projection":
        """Produce a generated projection of one record, for a downstream tool."""
        return Projection(self.get(constraint_id), class_specific)


@dataclass(frozen=True)
class Projection:
    """A generated projection of a constraint record, not a peer copy of it.

    It carries the id of the record it projects, may add class-specific fields,
    and never restates a field the record already defines.
    """

    constraint: Constraint
    class_specific: Mapping[str, object] = field(default_factory=dict)

    _RECORD_FIELDS = frozenset(
        {
            "id", "class", "constraint_kind", "targets", "expression",
            "enforcement", "verification", "applicability", "source",
        }
    )

    def __post_init__(self) -> None:
        restated = self._RECORD_FIELDS & set(self.class_specific)
        if restated:
            raise ValueError(
                "a projection does not restate a field the constraint record "
                f"already defines: {', '.join(sorted(restated))}"
            )

    def as_dict(self) -> dict:
        out = {"projects": self.constraint.id}
        out.update(dict(self.class_specific))
        return out
