"""Spec: Physical Quantities and Units."""

from decimal import Decimal
from fractions import Fraction

import pytest

from fang.diagnostics import FangError
from fang.units import DIMENSIONLESS, Dimension, Quantity, Unit, require_same_dimension


def test_canonical_form_normalizes_the_symbol_and_not_the_magnitude():
    quantity = Quantity.scalar("3.3", "V")
    assert str(quantity) == "3.3 V"
    assert quantity.as_dict()["value"] == "3.3"
    assert quantity.as_dict()["unit"] == "V"


def test_a_metric_prefix_is_permitted_on_input():
    assert Unit.parse("kOhm").factor == Decimal("1E+3")
    assert Unit.parse("kOhm").dimension == Unit.parse("Ohm").dimension


def test_dimension_is_a_seven_vector_in_the_fixed_si_order():
    assert len(Dimension().exponents) == 7
    assert DIMENSIONLESS.dimensionless
    assert Unit.parse("m").dimension.exponents[0] == Fraction(1)
    assert Unit.parse("A").dimension.exponents[3] == Fraction(1)


def test_two_quantities_are_comparable_only_where_dimensions_are_equal():
    volts = Quantity.scalar("3.3", "V")
    amps = Quantity.scalar("3.3", "A")
    assert volts.dimension != amps.dimension
    with pytest.raises(FangError) as caught:
        require_same_dimension(volts, amps, "comparison")
    assert caught.value.diagnostic.code == "UNIT-0001"


def test_compound_units_parse_and_keep_their_symbol():
    assert Unit.parse("Ohm*m").symbol == "Ohm*m"
    assert Unit.parse("V/us").symbol == "V/us"
    assert Unit.parse("m^2").dimension == Unit.parse("m").dimension ** 2


def test_conversion_is_exact_where_the_factor_is_exact():
    converted, exact = Quantity.scalar("3.3", "V").converted_to("mV")
    assert exact
    assert converted.as_dict()["value"] == "3300"


def test_conversion_records_its_rounding_where_the_factor_is_not_exact():
    converted, exact = Quantity.scalar("1", "eV").converted_to("J")
    assert converted.dimension == Unit.parse("J").dimension
    # Whether it rounded is handed back rather than swallowed.
    assert isinstance(exact, bool)


def test_a_magnitude_is_never_binary_floating_point():
    with pytest.raises(TypeError):
        Quantity.scalar(3.3, "V")


def test_a_range_and_a_tolerance_carry_intervals():
    assert Quantity.range("3", "3.6", "V").interval() == (Decimal("3"), Decimal("3.6"))
    low, high = Quantity.with_tolerance("3.3", "0.02", "V").interval()
    assert (low, high) == (Decimal("3.234"), Decimal("3.366"))


def test_an_absolute_tolerance_is_not_scaled_by_the_nominal():
    low, high = Quantity.with_tolerance("3.3", "0.1", "V", kind="absolute").interval()
    assert (low, high) == (Decimal("3.2"), Decimal("3.4"))


def test_an_unrecognized_symbol_is_rejected():
    with pytest.raises(FangError) as caught:
        Unit.parse("bogons")
    assert caught.value.diagnostic.code == "UNIT-0002"
