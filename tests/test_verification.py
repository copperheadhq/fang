"""Spec: Verification Questions Are Declared; The Bench Is Explicit; The Cheapest
Verification Level Is Chosen And Recorded; Verification Tools Sit Behind One
Protocol; Measurements Re-enter Through The Commit Gate; A Failing Measurement
Is Recorded And Not Applied; The Verify Command."""

from __future__ import annotations

from decimal import Decimal

import pytest

from fang import diagnostics
from fang.constraints import Comparison, Literal, Ref, Truth
from fang.diagnostics import REGISTRY
from fang.entities import Verification
from fang.identity import authored
from fang.serialization import canonical_dumps
from fang.units import Quantity
from fang.values import Value


# ==========================================================================
# Diagnostics and entity fields
# ==========================================================================

SIM_CODES = (
    "SIM_UNDECLARED_PARAMETER",
    "SIM_QUESTION_RESULT",
    "SIM_UNRESOLVED_SURFACE",
    "SIM_MISSING_BENCH",
    "SIM_LOAD_DIMENSION",
    "SIM_MODEL_PORT_UNREACHED",
    "SIM_OUTSIDE_MODEL_RANGE",
    "SIM_EXCLUSION_WITHOUT_REASON",
)


def test_the_sim_codes_are_allocated_in_their_own_area_and_none_is_reused():
    codes = [getattr(diagnostics, name) for name in SIM_CODES]
    assert codes == [f"SIM-{n:04d}" for n in range(1, len(codes) + 1)]
    descriptions = [REGISTRY.get(code).description for code in codes]
    assert len(set(descriptions)) == len(descriptions)
    for code in codes:
        assert REGISTRY.get(code).area == "SIM"


def test_a_sim_code_is_never_reallocated_to_another_condition():
    with pytest.raises(ValueError, match="never reused"):
        REGISTRY.allocate(diagnostics.SIM_MISSING_BENCH, "something else entirely")


def test_a_verification_nobody_ran_serializes_as_it_always_did():
    plain = Verification(authored("VER-1"), verifies="REQ-1", method="inspection")
    assert "level" not in plain.as_dict() and "tool" not in plain.as_dict()


def test_a_verification_a_tool_answered_names_the_level_and_the_tool():
    answered = Verification(
        authored("VER-1"), verifies="REQ-1", method="simulation",
        result="PASS", level="circuit", tool="ngspice",
    )
    assert answered.as_dict()["level"] == "circuit"
    assert answered.as_dict()["tool"] == "ngspice"


def test_an_unbounded_range_serializes_canonically_and_compares_as_an_interval():
    """An event observed not to occur before a run's end is the range from that
    end to infinity; interval comparison decides exactly what was observed."""
    after_the_run = Quantity.range("2", "Infinity", "s")
    assert canonical_dumps(after_the_run.as_dict()) == (
        '{"kind":"range","max":"Infinity","min":"2","unit":"s"}'
    )
    assert Quantity.range("2", Decimal("Infinity"), "s").as_dict()["max"] == "Infinity"

    def resolve(entity, attr):
        return Value.inferred(after_the_run, "EVD-1", "1")

    first_read = Ref("CMP-1", "first_read", after_the_run.dimension)
    within = Comparison("le", (first_read, Literal.of(Quantity.scalar("200", "ms"))))
    beyond = Comparison("ge", (first_read, Literal.of(Quantity.scalar("1", "s"))))
    assert within.evaluate(resolve) is Truth.FALSE
    assert beyond.evaluate(resolve) is Truth.TRUE


def test_a_nan_has_no_canonical_form():
    with pytest.raises(ValueError, match="NaN"):
        Quantity.scalar(Decimal("NaN"), "V").as_dict()
