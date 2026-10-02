"""Spec: Verification Questions Are Declared; The Bench Is Explicit; The Cheapest
Verification Level Is Chosen And Recorded; Verification Tools Sit Behind One
Protocol; Measurements Re-enter Through The Commit Gate; A Failing Measurement
Is Recorded And Not Applied; The Verify Command."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from fang import diagnostics
from fang.constraints import Comparison, Literal, Ref, Truth
from fang.diagnostics import REGISTRY, FangError
from fang.elaborate import elaborate
from fang.entities import Requirement, Verification
from fang.identity import Identity, authored, derive
from fang.interfaces import AnalogOut, Pin, PinMap
from fang.lang import (
    Electrical,
    Parameter,
    Part,
    System,
    V,
    kHz,
    kOhm,
    mA,
    ms,
    mV,
    nF,
    require,
)
from fang.parts import Capacitor, Resistor
from fang.rationale import Requires, Verifies
from fang.serialization import canonical_bytes, canonical_dumps
from fang.simulation import ACSweep
from fang.units import Quantity
from fang.values import Value
from fang.verification import Average, Crossing, Simulates


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


# ==========================================================================
# Declaring questions
# ==========================================================================

PROJECT = "PRJ-VERIFY"


class Jack(Part):
    """A two-wire signal connection: a tip, and a sleeve that is ground."""

    designator_prefix = "J"
    line = AnalogOut()
    TIP = Pin("TIP", role="analog", number="1")
    SLEEVE = Pin("SLEEVE", role="ground", number="2")
    pinmap = PinMap({"line.signal": "TIP", "line.ref": "SLEEVE"})


def corner_question(**overrides):
    arguments = dict(
        measures={"corner": Crossing("outlet.line", level=707.1 * mV, edge="falling")},
        supplies={"inlet.line": 1 * V},
        analysis=ACSweep(variation="dec", points=100, start="10", stop="1meg"),
        abstracted=("inlet", "outlet"),
    )
    arguments.update(overrides)
    return Simulates("corner_spec", **arguments)


class Filter(System):
    """A first-order RC low-pass between two jacks."""

    corner_spec = Requires("The corner lies between 1.5 kHz and 1.7 kHz")
    corner = Parameter("Hz", description="the -3 dB corner, as measured")

    inlet = Jack()
    outlet = Jack()
    r = Resistor(resistance=10 * kOhm)
    c = Capacitor(capacitance=10 * nF)

    by_simulation = corner_question()

    def architecture(self):
        self.inlet.line.signal >> self.r.p1
        self.r.p2 >> self.c.p1
        self.c.p2 >> self.inlet.line.ref
        self.outlet.line.signal >> self.c.p1
        self.outlet.line.ref >> self.c.p2

    def constraints(self):
        require(self.corner >= 1.5 * kHz)
        require(self.corner <= 1.7 * kHz)


def build(system=Filter):
    result = elaborate(system, project_id=PROJECT)
    assert result.ok, [d.message for d in result.diagnostics]
    return result


def verification_of(snapshot, attribute="by_simulation") -> Verification:
    return next(
        e for e in snapshot.entities.values()
        if isinstance(e, Verification) and e.identity.display_name == attribute
    )


def test_a_question_cannot_state_its_own_answer():
    with pytest.raises(FangError) as raised:
        corner_question(result="PASS")
    assert raised.value.diagnostic.code == diagnostics.SIM_QUESTION_RESULT
    # Not even an explicit "nothing": a result is produced by a run.
    with pytest.raises(FangError):
        corner_question(result=None)


def test_a_declared_question_becomes_an_unanswered_verification():
    snapshot = build().snapshot
    verification = verification_of(snapshot)
    requirement = next(e for e in snapshot.entities.values() if isinstance(e, Requirement))
    question = verification.extensions["question"]

    assert verification.result == "UNKNOWN"
    assert verification.verifies == requirement.id
    assert verification.method == "simulation"
    assert verification.source_location is not None
    system = derive(PROJECT, "block", "system").id
    assert [m["parameter"] for m in question["measures"]] == [f"{system}.corner"]
    assert question["bench"]["supplies"] == [
        {"surface": "inlet.line", "quantity": {"kind": "scalar", "unit": "V", "value": "1"}}
    ]
    assert question["bench"]["analysis"]["kind"] == "ac"


def test_every_surface_is_resolved_to_pins_at_elaboration():
    snapshot = build().snapshot
    question = verification_of(snapshot).extensions["question"]
    outlet = derive(PROJECT, "component", "system.outlet").id
    assert question["surfaces"]["outlet.line"] == {
        "signal": {"component": outlet, "pin": "TIP"},
        "return": {"component": outlet, "pin": "SLEEVE"},
    }
    assert {part["name"] for part in question["abstracted"]} == {"inlet", "outlet"}


def test_two_elaborations_of_a_question_are_byte_identical():
    first, second = build().snapshot, build().snapshot
    assert canonical_bytes(first.as_dict()) == canonical_bytes(second.as_dict())


def test_a_measure_naming_an_undeclared_parameter_fails_elaboration():
    class Misnamed(Filter):
        by_simulation = corner_question(
            measures={"knee": Crossing("outlet.line", level=707.1 * mV)}
        )

    result = elaborate(Misnamed, project_id=PROJECT)
    assert not result.ok
    diagnostic = result.diagnostics[0]
    assert diagnostic.code == diagnostics.SIM_UNDECLARED_PARAMETER
    assert "'knee'" in diagnostic.message
    assert diagnostic.location is not None


def test_a_surface_with_no_pins_fails_elaboration_naming_it():
    class Probed(Filter):
        board_in = Electrical()
        by_simulation = corner_question(supplies={"board_in": 1 * V})

    result = elaborate(Probed, project_id=PROJECT)
    assert not result.ok
    assert result.diagnostics[0].code == diagnostics.SIM_UNRESOLVED_SURFACE
    assert "'board_in'" in result.diagnostics[0].message
    assert "system's own surface is not a probe" in result.diagnostics[0].message

    class Mistyped(Filter):
        by_simulation = corner_question(supplies={"inlet.jack": 1 * V})

    result = elaborate(Mistyped, project_id=PROJECT)
    assert result.diagnostics[0].code == diagnostics.SIM_UNRESOLVED_SURFACE
    assert "'inlet.jack'" in result.diagnostics[0].message


def test_a_load_is_a_current_or_a_resistance_and_nothing_else():
    corner_question(loads={"outlet.line": 1 * mA})
    corner_question(loads={"outlet.line": 10 * kOhm})
    with pytest.raises(FangError) as raised:
        corner_question(loads={"outlet.line": 3 * V})
    assert raised.value.diagnostic.code == diagnostics.SIM_LOAD_DIMENSION
    assert "outlet.line" in raised.value.diagnostic.message


def test_a_window_in_the_wrong_dimension_is_refused_where_it_is_written():
    with pytest.raises(FangError) as raised:
        corner_question(measures={"corner": Average("outlet.line", after=1 * ms)})
    assert raised.value.diagnostic.code == diagnostics.UNIT_DIMENSION_MISMATCH


def test_a_measure_producing_the_wrong_dimension_fails_elaboration():
    class Averaged(Filter):
        by_simulation = corner_question(measures={"corner": Average("outlet.line")})

    result = elaborate(Averaged, project_id=PROJECT)
    assert result.diagnostics[0].code == diagnostics.UNIT_DIMENSION_MISMATCH


def test_a_question_reads_back_from_its_record_without_the_program():
    """A question in the graph is data: its measures rebuild from the record,
    and the values and provenance beside it round-trip exactly."""
    from fang.provenance import Provenance
    from fang.verification import Measure

    snapshot = build().snapshot
    verification = verification_of(snapshot)
    record = json.loads(canonical_dumps(verification.as_dict()))

    for entry in record["extensions"]["question"]["measures"]:
        assert Measure.from_dict(entry["measure"]).as_dict() == entry["measure"]
    assert Identity.from_dict(record["identity"]) == verification.identity
    assert Provenance.from_list(record["provenance"]).as_list() == verification.provenance.as_list()

    value = Value.inferred(Quantity.range("2", "Infinity", "s"), "EVD-1", "0.5")
    assert Value.from_dict(json.loads(canonical_dumps(value.as_dict()))) == value


def test_a_verification_by_inspection_elaborates_exactly_as_before():
    class Inspected(Filter):
        looked_at = Verifies("corner_spec", method="inspection", result="PASS")

    snapshot = build(Inspected).snapshot
    inspected = verification_of(snapshot, "looked_at")
    assert inspected.result == "PASS"
    assert inspected.method == "inspection"
    assert inspected.extensions == {}
    assert "extensions" not in inspected.as_dict()
