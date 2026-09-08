"""Spec: Structural Validation; Requirement State Transitions; Schema
Versioning; Provenance; Typed Connections."""

import pytest

from conftest import REGULATOR, VOLTS, WATTS, tool_provenance

from fang.constraints import Constraint, Enforcement, Literal, Ref, compare, ge, le
from fang.diagnostics import FangError, SourceLocation
from fang.entities import (
    Component,
    Connection,
    ConnectionKind,
    Requirement,
    RequirementState,
    TRANSITIONS,
)
from fang.identity import Origin, authored, derive, imported
from fang.units import Quantity
from fang.validation import StateTransition, check_schema_version, check_transition, validate


def test_an_untyped_connection_is_not_representable():
    with pytest.raises(FangError) as caught:
        Connection(authored("CN-1"), source="A", target="B")
    assert caught.value.diagnostic.code == "ELAB-0005"


def test_every_required_connection_kind_exists():
    expected = {
        "electrical", "power", "signal", "ground",
        "mechanical", "control", "dependency", "containment",
    }
    assert {k.value for k in ConnectionKind} == expected


def test_a_dangling_required_reference_is_rejected():
    connection = Connection(
        authored("CN-1"), connection_kind=ConnectionKind.POWER, source="CMP-A", target="CMP-MISSING"
    )
    report = validate({"CN-1": connection, "CMP-A": Component(authored("CMP-A"))})
    assert not report.ok
    assert any(d.code == "ELAB-0006" for d in report.diagnostics)


def test_referential_integrity_passes_when_every_reference_resolves():
    entities = {
        "CMP-A": Component(authored("CMP-A")),
        "CMP-B": Component(authored("CMP-B")),
    }
    entities["CN-1"] = Connection(
        authored("CN-1"), connection_kind=ConnectionKind.SIGNAL, source="CMP-A", target="CMP-B"
    )
    assert validate(entities).ok


def test_a_derived_entity_without_provenance_is_rejected():
    entity = Component(derive("PRJ-1", "component", "system.x.u1"))
    report = validate({entity.id: entity})
    assert not report.ok
    assert any(d.code == "ELAB-0004" for d in report.diagnostics)


def test_a_derived_entity_with_provenance_and_a_source_location_passes():
    entity = Component(
        derive("PRJ-1", "component", "system.x.u1"), provenance=tool_provenance()
    )
    assert validate({entity.id: entity}).ok


def test_a_containment_cycle_is_rejected():
    entities = {name: Component(authored(name)) for name in ("A", "B", "C")}
    report = validate(entities, containment={"A": ["B"], "B": ["C"], "C": ["A"]})
    assert not report.ok
    assert any(d.code == "ELAB-0010" for d in report.diagnostics)


def test_contradictory_mandatory_constraints_are_rejected():
    component = Component(authored("CMP-1"))
    low = Constraint(
        authored("RULE-LOW"),
        constraint_kind="power_budget",
        targets=("CMP-1",),
        expression=le(Ref("CMP-1", "p", WATTS), Literal.of(Quantity.scalar("0.1", "W"))),
        enforcement=Enforcement.HARD,
    )
    high = Constraint(
        authored("RULE-HIGH"),
        constraint_kind="power_budget",
        targets=("CMP-1",),
        expression=ge(Ref("CMP-1", "p", WATTS), Literal.of(Quantity.scalar("0.5", "W"))),
        enforcement=Enforcement.HARD,
    )
    report = validate({"CMP-1": component, "RULE-LOW": low, "RULE-HIGH": high})
    assert not report.ok
    assert any(d.code == "ELAB-0011" for d in report.diagnostics)


def test_compatible_mandatory_constraints_are_not_flagged():
    component = Component(authored("CMP-1"))
    low = Constraint(
        authored("RULE-LOW"),
        constraint_kind="power_budget",
        targets=("CMP-1",),
        expression=le(Ref("CMP-1", "p", WATTS), Literal.of(Quantity.scalar("0.5", "W"))),
    )
    high = Constraint(
        authored("RULE-HIGH"),
        constraint_kind="power_budget",
        targets=("CMP-1",),
        expression=ge(Ref("CMP-1", "p", WATTS), Literal.of(Quantity.scalar("0.1", "W"))),
    )
    assert validate({"CMP-1": component, "RULE-LOW": low, "RULE-HIGH": high}).ok


def test_constraints_bounding_different_parameters_are_not_compared():
    """A floor on one quantity says nothing about a ceiling on another.

    Both constraints sit on the same target and are of the same kind, so only
    the parameter each one references separates them.
    """
    component = Component(authored("CMP-1"))
    voltage_floor = Constraint(
        authored("RULE-V"),
        constraint_kind="declared",
        targets=("CMP-1",),
        expression=ge(Ref("CMP-1", "v", VOLTS), Literal.of(Quantity.scalar("5", "V"))),
        enforcement=Enforcement.HARD,
    )
    power_ceiling = Constraint(
        authored("RULE-P"),
        constraint_kind="declared",
        targets=("CMP-1",),
        expression=le(Ref("CMP-1", "p", WATTS), Literal.of(Quantity.scalar("0.5", "W"))),
        enforcement=Enforcement.HARD,
    )
    entities = {"CMP-1": component, "RULE-V": voltage_floor, "RULE-P": power_ceiling}
    assert validate(entities).ok


# -- requirement state machine ---------------------------------------------


def test_no_transition_enters_missing():
    for permitted in TRANSITIONS.values():
        assert RequirementState.MISSING not in permitted


def test_verified_is_reachable_only_from_known_or_derived():
    sources = {
        state for state, permitted in TRANSITIONS.items()
        if RequirementState.VERIFIED in permitted
    }
    assert sources == {RequirementState.KNOWN, RequirementState.DERIVED}


def test_a_transition_outside_the_table_is_rejected():
    problems = check_transition(
        StateTransition("REQ-1", RequirementState.MISSING, RequirementState.VERIFIED, "a", "r")
    )
    assert any(p.code == "ELAB-0007" for p in problems)


def test_a_transition_to_verified_cites_evidence():
    without = check_transition(
        StateTransition("REQ-1", RequirementState.KNOWN, RequirementState.VERIFIED, "a", "r")
    )
    assert without
    with_evidence = check_transition(
        StateTransition(
            "REQ-1", RequirementState.KNOWN, RequirementState.VERIFIED, "a", "r", evidence="VER-1"
        )
    )
    assert not with_evidence


def test_a_transition_to_waived_cites_a_waiver():
    assert check_transition(
        StateTransition("REQ-1", RequirementState.KNOWN, RequirementState.WAIVED, "a", "r")
    )
    assert not check_transition(
        StateTransition(
            "REQ-1", RequirementState.KNOWN, RequirementState.WAIVED, "a", "r", waiver="WVR-1"
        )
    )


def test_promotion_out_of_assumed_cites_approval_or_evidence():
    assert check_transition(
        StateTransition("REQ-1", RequirementState.ASSUMED, RequirementState.KNOWN, "a", "r")
    )
    assert not check_transition(
        StateTransition(
            "REQ-1", RequirementState.ASSUMED, RequirementState.KNOWN, "a", "r", approval="APR-1"
        )
    )


def test_every_transition_records_actor_and_reason():
    assert check_transition(
        StateTransition("REQ-1", RequirementState.KNOWN, RequirementState.DERIVED, "", "")
    )


# -- schema versioning -----------------------------------------------------


def test_an_unimplemented_major_version_is_rejected_and_never_downgraded():
    with pytest.raises(FangError) as caught:
        check_schema_version("2.0")
    assert caught.value.diagnostic.code == "ELAB-0009"


def test_an_additive_minor_version_is_accepted():
    check_schema_version("1.9")


# -- identity uniqueness across origins -----------------------------------


def test_identifiers_are_unique_across_every_origin():
    authored_entity = Component(authored("CMP-SHARED"))
    imported_entity = Component(imported("CMP-SHARED", external_id="/ext/1"))
    report = validate({"a": authored_entity, "b": imported_entity})
    assert not report.ok
    assert any(d.code == "ELAB-0003" for d in report.diagnostics)
