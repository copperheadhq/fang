"""Spec: Exactly One Constraint Registry; The Constraint Record; Typed
Constraint Expressions."""

import pytest

from fang.constraints import (
    Arithmetic,
    CheckStatus,
    Constraint,
    ConstraintClass,
    ConstraintRegistry,
    Enforcement,
    Literal,
    Logical,
    Ref,
    Truth,
    compare,
    le,
)
from fang.diagnostics import FangError
from fang.identity import authored
from fang.units import Quantity
from fang.values import Value

WATTS = Quantity.scalar("0", "W").dimension
VOLTS = Quantity.scalar("0", "V").dimension
AMPS = Quantity.scalar("0", "A").dimension


def constraint(expression, **kwargs):
    return Constraint(
        authored(kwargs.pop("id", "RULE-1")),
        constraint_kind=kwargs.pop("constraint_kind", "max_power_dissipation"),
        targets=kwargs.pop("targets", ("CMP-1",)),
        expression=expression,
        **kwargs,
    )


def resolver(value):
    return lambda entity_id, attr: value


# -- three-valued logic ----------------------------------------------------


def test_and_is_false_if_any_operand_is_false():
    assert (Truth.FALSE & Truth.UNDECIDED) is Truth.FALSE
    assert (Truth.UNDECIDED & Truth.TRUE) is Truth.UNDECIDED
    assert (Truth.TRUE & Truth.TRUE) is Truth.TRUE


def test_or_is_true_if_any_operand_is_true():
    assert (Truth.TRUE | Truth.UNDECIDED) is Truth.TRUE
    assert (Truth.UNDECIDED | Truth.FALSE) is Truth.UNDECIDED
    assert (Truth.FALSE | Truth.FALSE) is Truth.FALSE


def test_not_maps_undecided_to_undecided():
    assert ~Truth.UNDECIDED is Truth.UNDECIDED
    assert ~Truth.TRUE is Truth.FALSE
    assert ~Truth.FALSE is Truth.TRUE


# -- dimensional discipline ------------------------------------------------


def test_a_dimension_mismatch_is_rejected_where_the_expression_is_written():
    with pytest.raises(FangError) as caught:
        le(Ref("CMP-1", "voltage", VOLTS), Literal.of(Quantity.scalar("1", "A")))
    assert caught.value.diagnostic.code == "UNIT-0001"


def test_addition_requires_operands_of_equal_dimension():
    with pytest.raises(FangError):
        Arithmetic("add", (Literal.of(Quantity.scalar("1", "V")), Literal.of(Quantity.scalar("1", "A"))))


def test_multiplication_adds_dimension_vectors_and_division_subtracts_them():
    volts = Literal.of(Quantity.scalar("2", "V"))
    amps = Literal.of(Quantity.scalar("3", "A"))
    watts = Arithmetic("mul", (volts, amps))
    assert watts.dimension == WATTS
    assert Arithmetic("div", (watts, amps)).dimension == VOLTS


def test_an_exponent_must_be_a_dimensionless_rational():
    from fractions import Fraction

    squared = Arithmetic("pow", (Literal.of(Quantity.scalar("2", "m")),), exponent=Fraction(2))
    assert squared.dimension == Quantity.scalar("0", "m^2").dimension
    with pytest.raises(FangError):
        Arithmetic("pow", (Literal.of(Quantity.scalar("2", "m")),))


# -- interval semantics ----------------------------------------------------


def test_a_comparison_is_true_only_when_it_holds_across_the_whole_interval():
    rule = constraint(le(Ref("CMP-1", "p", WATTS), Literal.of(Quantity.scalar("0.25", "W"))))
    assert rule.evaluate(resolver(Value.explicit(Quantity.scalar("0.1", "W")))) is CheckStatus.PASS


def test_a_comparison_is_false_when_it_fails_across_the_whole_interval():
    rule = constraint(le(Ref("CMP-1", "p", WATTS), Literal.of(Quantity.scalar("0.25", "W"))))
    assert rule.evaluate(resolver(Value.explicit(Quantity.scalar("0.5", "W")))) is CheckStatus.FAIL


def test_a_comparison_is_undecided_when_it_holds_across_only_part_of_the_interval():
    rule = constraint(le(Ref("CMP-1", "p", WATTS), Literal.of(Quantity.scalar("0.25", "W"))))
    partial = Value.explicit(Quantity.range("0.1", "0.5", "W"))
    assert rule.evaluate(resolver(partial)) is CheckStatus.UNKNOWN


def test_an_unknown_operand_makes_the_comparison_undecided():
    rule = constraint(le(Ref("CMP-1", "p", WATTS), Literal.of(Quantity.scalar("0.25", "W"))))
    assert rule.evaluate(resolver(Value.unknown())) is CheckStatus.UNKNOWN
    assert rule.evaluate(lambda i, a: None) is CheckStatus.UNKNOWN


def test_undecided_is_never_reported_as_a_pass_or_a_failure():
    rule = constraint(le(Ref("CMP-1", "p", WATTS), Literal.of(Quantity.scalar("0.25", "W"))))
    status = rule.evaluate(resolver(Value.unknown()))
    assert status is CheckStatus.UNKNOWN
    assert status not in (CheckStatus.PASS, CheckStatus.FAIL)


def test_equality_is_true_only_between_two_identical_points():
    rule = constraint(compare("eq", Ref("CMP-1", "v", VOLTS), Literal.of(Quantity.scalar("3.3", "V"))))
    assert rule.evaluate(resolver(Value.explicit(Quantity.scalar("3.3", "V")))) is CheckStatus.PASS
    assert rule.evaluate(
        resolver(Value.explicit(Quantity.with_tolerance("3.3", "0.02", "V")))
    ) is CheckStatus.UNKNOWN
    assert rule.evaluate(resolver(Value.explicit(Quantity.scalar("5", "V")))) is CheckStatus.FAIL


# -- the record ------------------------------------------------------------


def test_a_constraint_carries_its_required_fields():
    expression = le(Ref("CMP-1", "p", WATTS), Literal.of(Quantity.scalar("1", "W")))
    complete = {"constraint_kind": "max_power", "targets": ("CMP-1",), "expression": expression}
    for field in complete:
        incomplete = dict(complete)
        incomplete[field] = "" if field == "constraint_kind" else (() if field == "targets" else None)
        with pytest.raises(ValueError):
            Constraint(authored("RULE-1"), **incomplete)


def test_a_non_applicable_constraint_is_not_reported_as_passing():
    rule = constraint(
        le(Ref("CMP-1", "p", WATTS), Literal.of(Quantity.scalar("0.25", "W"))),
        applicability=Literal.of(False),
    )
    assert rule.evaluate(resolver(Value.explicit(Quantity.scalar("9", "W")))) is CheckStatus.NOT_APPLICABLE


def test_enforcement_states_how_a_violation_is_treated():
    rule = constraint(
        le(Ref("CMP-1", "p", WATTS), Literal.of(Quantity.scalar("0.25", "W"))),
        enforcement=Enforcement.ADVISORY,
    )
    assert rule.as_dict()["enforcement"] == "advisory"


# -- the registry ----------------------------------------------------------


def test_there_is_exactly_one_registry_per_project():
    ConstraintRegistry.release("PRJ-REG")
    registry = ConstraintRegistry("PRJ-REG")
    with pytest.raises(FangError) as caught:
        ConstraintRegistry("PRJ-REG")
    assert caught.value.diagnostic.code == "ELAB-0012"
    assert ConstraintRegistry.for_project("PRJ-REG") is registry
    ConstraintRegistry.release("PRJ-REG")


def test_every_class_lives_in_the_one_registry():
    ConstraintRegistry.release("PRJ-CLASSES")
    registry = ConstraintRegistry("PRJ-CLASSES")
    for index, klass in enumerate(ConstraintClass):
        registry.add(
            constraint(
                le(Ref("CMP-1", "p", WATTS), Literal.of(Quantity.scalar("1", "W"))),
                id=f"RULE-{index}",
                constraint_class=klass,
            )
        )
    assert len(registry) == len(list(ConstraintClass))
    assert len(registry.of_class(ConstraintClass.ROUTING)) == 1
    ConstraintRegistry.release("PRJ-CLASSES")


def test_a_projection_carries_the_id_and_does_not_restate_the_record():
    ConstraintRegistry.release("PRJ-PROJ")
    registry = ConstraintRegistry("PRJ-PROJ")
    rule = registry.add(constraint(le(Ref("CMP-1", "p", WATTS), Literal.of(Quantity.scalar("1", "W")))))
    projection = registry.project(rule.id, layer="F.Cu")
    assert projection.as_dict() == {"projects": "RULE-1", "layer": "F.Cu"}
    with pytest.raises(ValueError):
        registry.project(rule.id, targets=("CMP-2",))
    ConstraintRegistry.release("PRJ-PROJ")
