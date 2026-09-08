"""Spec: Declarative Module Composition; Parameter Declaration And Reference;
Declared Constraints Are Not Evaluated Eagerly; The Connect Operator."""

from decimal import Decimal

import pytest

from fang.constraints import Arithmetic, Comparison, Truth
from fang.diagnostics import FangError
from fang.entities import ConnectionKind
from fang.lang import (
    Electrical,
    Ground,
    Mechanical,
    Module,
    Parameter,
    Part,
    Power,
    Signal,
    System,
    V,
    between,
    kOhm,
    mA,
    require,
    tolerance,
    uF,
)
from fang.units import Quantity
from fang.values import ValueStatus


class Resistor(Part):
    resistance = Parameter("Ohm")
    p1 = Electrical()
    p2 = Electrical()


class Divider(System):
    top = Resistor()
    bottom = Resistor()


# -- declaration model -----------------------------------------------------


def test_two_instances_do_not_share_a_child():
    a, b = Divider(), Divider()
    assert a.top is not b.top
    assert a.top is not a.bottom


def test_two_instances_do_not_share_a_surface():
    a, b = Divider(), Divider()
    assert a.top.p1 is not b.top.p1
    assert a.top.p1 is not a.top.p2


def test_declaration_order_is_class_body_order():
    ordered = sorted(Divider._children.items(), key=lambda kv: kv[1]._order)
    assert [name for name, _ in ordered] == ["top", "bottom"]
    ordered_surfaces = sorted(Resistor._surfaces.items(), key=lambda kv: kv[1]._order)
    assert [name for name, _ in ordered_surfaces] == ["p1", "p2"]


def test_a_declaration_records_its_source_location():
    assert Resistor._surfaces["p1"]._source is not None
    assert Resistor._surfaces["p1"]._source.file.endswith("test_lang.py")


def test_inheritance_carries_declarations_forward():
    class Fused(Resistor):
        rating = Parameter("W")

    assert set(Fused._surfaces) == {"p1", "p2"}
    assert "resistance" in Fused._parameters and "rating" in Fused._parameters


# -- parameters and units --------------------------------------------------


def test_a_unit_literal_builds_a_decimal_quantity():
    quantity = 3.3 * V
    assert isinstance(quantity, Quantity)
    assert quantity.as_dict() == {"kind": "scalar", "unit": "V", "value": "3.3"}
    assert isinstance(quantity.value, Decimal)


def test_prefixed_unit_literals_keep_their_symbol():
    assert str(4.7 * kOhm) == "4.7 kOhm"
    assert str(100 * mA) == "100 mA"
    assert str(10 * uF) == "10 uF"


def test_an_unassigned_parameter_is_unknown_not_defaulted():
    assert Resistor().value_of("resistance").status is ValueStatus.UNKNOWN


def test_an_assigned_parameter_is_explicit():
    value = Resistor(resistance=4.7 * kOhm).value_of("resistance")
    assert value.status is ValueStatus.EXPLICIT
    assert str(value.quantity) == "4.7 kOhm"


def test_a_declared_default_is_recorded():
    class Pullup(Part):
        resistance = Parameter("Ohm", default=10 * kOhm)

    assert str(Pullup().value_of("resistance").quantity) == "10 kOhm"


def test_a_dimensionally_wrong_assignment_fails_at_elaboration():
    with pytest.raises(FangError) as caught:
        Resistor(resistance=10 * uF)
    assert caught.value.diagnostic.code == "UNIT-0001"


def test_a_bare_number_is_not_a_parameter():
    with pytest.raises(FangError):
        Resistor(resistance=4700)


def test_an_undeclared_parameter_is_refused():
    with pytest.raises(FangError):
        Resistor(inductance=1 * V)


def test_a_default_of_the_wrong_dimension_is_refused_at_declaration():
    with pytest.raises(FangError):
        Parameter("Ohm", default=3.3 * V)


def test_range_and_tolerance_literals():
    span = between(3 * V, 3.6 * V)
    assert span.interval() == (Decimal("3"), Decimal("3.6"))
    band = tolerance(3.3 * V, "2%")
    assert band.interval() == (Decimal("3.234"), Decimal("3.366"))
    absolute = tolerance(3.3 * V, 0.1 * V)
    assert absolute.interval() == (Decimal("3.2"), Decimal("3.4"))


def test_a_range_needs_bounds_of_equal_dimension():
    with pytest.raises(FangError):
        between(3 * V, 3.6 * kOhm)


# -- parameter references and constraints ----------------------------------


def test_a_comparison_builds_an_expression_rather_than_a_boolean():
    resistor = Resistor()
    resistor._entity_id = "CMP-1"
    expression = resistor.resistance <= 1000 * kOhm
    assert isinstance(expression, Comparison)
    assert expression.op == "le"
    assert not isinstance(expression, bool)


def test_arithmetic_between_parameters_builds_a_node():
    divider = Divider()
    divider.top._entity_id = "CMP-1"
    divider.bottom._entity_id = "CMP-2"
    total = divider.top.resistance + divider.bottom.resistance
    assert isinstance(total, Arithmetic)
    assert total.op == "add"


def test_a_dimension_mismatch_in_a_constraint_is_caught_where_it_is_written():
    resistor = Resistor()
    resistor._entity_id = "CMP-1"
    with pytest.raises(FangError) as caught:
        resistor.resistance <= 3.3 * V
    assert caught.value.diagnostic.code == "UNIT-0001"


def test_require_outside_elaboration_is_refused():
    resistor = Resistor()
    resistor._entity_id = "CMP-1"
    with pytest.raises(FangError):
        require(resistor.resistance <= 1000 * kOhm)


def test_require_refuses_something_that_is_not_an_expression():
    from fang.lang import ElaborationContext

    with ElaborationContext():
        with pytest.raises(FangError):
            require(True)


# -- the connect operator --------------------------------------------------


def test_connecting_records_a_typed_connection():
    from fang.lang import ElaborationContext

    class Rail(Module):
        out = Power()

    class Load(Module):
        vin = Power()

    source, sink = Rail(), Load()
    with ElaborationContext() as context:
        source.out >> sink.vin
    assert len(context.connections) == 1
    left, right, location = context.connections[0]
    assert left.connection_kind is ConnectionKind.POWER
    assert location is not None and location.file.endswith("test_lang.py")


def test_connecting_incompatible_surface_kinds_is_refused():
    from fang.lang import ElaborationContext

    class Odd(Module):
        rail = Power()
        chassis = Mechanical()

    odd = Odd()
    with ElaborationContext():
        with pytest.raises(FangError) as caught:
            odd.rail >> odd.chassis
    assert caught.value.diagnostic.code == "ELAB-0005"


def test_the_connect_operator_returns_the_right_hand_side_for_chaining():
    from fang.lang import ElaborationContext

    class Chain(Module):
        a = Electrical()
        b = Electrical()
        c = Electrical()

    chain = Chain()
    with ElaborationContext() as context:
        chain.a >> chain.b >> chain.c
    assert len(context.connections) == 2


def test_connecting_outside_elaboration_is_refused():
    class Rail(Module):
        out = Power()

    with pytest.raises(FangError):
        Rail().out >> Rail().out
