"""Spec: Rationale Authored From The Program; Calculations Are First-Class;
Verification Results Form A Graph; Impact Propagation."""

import pytest

from fang.diff import ChangeClass, diff
from fang.elaborate import elaborate
from fang.entities import (
    Assumption,
    Calculation,
    Decision,
    Evidence,
    Requirement,
    RequirementState,
    Verification,
)
from fang.lang import System, V, kOhm, require
from fang.parts import Resistor
from fang.rationale import (
    Assumes,
    Calculates,
    Chooses,
    Cites,
    Requires,
    Verifies,
    coverage,
    impacted_by,
)
from fang.units import Quantity
from fang.values import Value

PROJECT = "PRJ-RATIONALE"


class Board(System):
    input_range = Requires(
        "Input shall tolerate 36 V continuous", validation="analysis"
    )
    ambient = Assumes("Ambient stays below 40 C", rationale="enclosure is vented")
    vin_absmax = Cites(
        "Absolute maximum VIN is 17 V",
        document="SRC-DS-TPS62130",
        locator="table 6.1",
    )

    divider_ratio = Calculates(
        "top / (top + bottom)", inputs=("top", "bottom"), result="0.68"
    )

    top = Resistor(resistance=10 * kOhm)
    bottom = Resistor(resistance=4.7 * kOhm)


def entities_of(snapshot, cls):
    return [e for e in snapshot.entities.values() if isinstance(e, cls)]


@pytest.fixture
def board():
    result = elaborate(Board, project_id=PROJECT)
    assert result.ok, [d.message for d in result.diagnostics]
    return result


# -- authoring -------------------------------------------------------------


def test_a_requirement_declared_in_a_program_becomes_an_entity(board):
    requirement = entities_of(board.snapshot, Requirement)[0]
    assert requirement.statement.startswith("Input shall tolerate")
    assert requirement.state is RequirementState.KNOWN
    assert requirement.validation_method == "analysis"


def test_every_rationale_entity_carries_its_declaring_source_location(board):
    for cls in (Requirement, Assumption, Evidence, Calculation):
        for entity in entities_of(board.snapshot, cls):
            assert entity.source_location is not None
            assert entity.source_location.file.endswith("test_rationale.py")
            assert entity.source_location.line > 0


def test_a_claim_without_a_citation_is_recorded_as_an_assumption(board):
    assumptions = entities_of(board.snapshot, Assumption)
    assert len(assumptions) == 1
    assert assumptions[0].claim.startswith("Ambient stays")
    assert assumptions[0].rationale


def test_a_claim_with_a_citation_is_recorded_as_evidence(board):
    evidence = entities_of(board.snapshot, Evidence)
    assert len(evidence) == 1
    assert evidence[0].document == "SRC-DS-TPS62130"
    assert evidence[0].locator == "table 6.1"


def test_an_uncited_claim_is_not_promoted_to_evidence(board):
    """The difference between known and hoped stays visible in the graph."""
    assert not any(
        e.claim.startswith("Ambient") for e in entities_of(board.snapshot, Evidence)
    )


def test_a_decision_names_its_alternatives_and_what_it_serves():
    class Choosing(System):
        requirement = Requires("Provide 3V3 at 1 A")
        choice = Chooses(
            "Which buck regulator provides 3V3?",
            selected="TPS62130",
            alternatives=[
                {"part": "MP1584", "reason": "package and EMI preference"},
                {"part": "TPSM63603", "reason": "cost"},
            ],
            requirements=(),
            rationale=("efficiency target", "input voltage margin"),
        )

    result = elaborate(Choosing, project_id=PROJECT)
    decision = entities_of(result.snapshot, Decision)[0]
    assert decision.choice == "TPS62130"
    assert {a["part"] for a in decision.alternatives_rejected} == {"MP1584", "TPSM63603"}
    assert decision.rationale == ("efficiency target", "input voltage margin")


# -- calculations ----------------------------------------------------------


def test_a_calculation_records_what_it_depends_on(board):
    calculation = entities_of(board.snapshot, Calculation)[0]
    assert calculation.expression == "top / (top + bottom)"
    assert calculation.result == "0.68"
    # Sibling names resolve to the entities they meant, not to literal strings.
    components = {
        e.id for e in board.snapshot.entities.values() if e.kind == "component"
    }
    assert set(calculation.inputs) == components


def test_changing_an_input_invalidates_the_calculation():
    from fang.identity import authored

    resistor = next(
        e
        for e in elaborate(Board, project_id=PROJECT).snapshot.entities.values()
        if e.kind == "component"
    )
    calculation = Calculation(
        authored("CALC-1"),
        expression="v_out = v_in * ratio",
        inputs=(resistor.id,),
        requirements=(),
    )
    before = {resistor.id: resistor, "CALC-1": calculation}
    after = dict(before)
    after[resistor.id] = resistor.with_parameter(
        "resistance", Value.explicit(Quantity.scalar("22", "kOhm"))
    )

    changes = diff(before, after)
    assert "CALC-1" in changes.invalidated


# -- verification ----------------------------------------------------------


def test_a_verification_links_a_requirement_to_its_evidence():
    class Verified(System):
        requirement = Requires("Rail is 3V3 +/- 2%")
        measurement = Verifies(
            "requirement", method="test", evidence=(), result="PASS"
        )

    result = elaborate(Verified, project_id=PROJECT)
    verification = entities_of(result.snapshot, Verification)[0]
    assert verification.method == "test"
    assert verification.result == "PASS"


def test_an_uncovered_requirement_is_visible(board):
    report = coverage(board.snapshot)
    assert report["total"] == 1
    assert report["covered"] == []
    assert len(report["uncovered"]) == 1


def test_coverage_is_answerable_from_graph_structure_alone():
    from fang.graph import Snapshot
    from fang.identity import authored

    requirement = Requirement(authored("REQ-1"), statement="a requirement")
    verification = Verification(
        authored("VER-1"), verifies="REQ-1", method="analysis", result="PASS"
    )
    snapshot = Snapshot(PROJECT, "REV-1", {"REQ-1": requirement, "VER-1": verification})

    report = coverage(snapshot)
    assert report["covered"] == ["REQ-1"]
    assert report["uncovered"] == []
    assert report["verifications"] == {"REQ-1": ["VER-1"]}


# -- impact ----------------------------------------------------------------


def test_a_parameter_change_names_the_requirement_it_puts_at_risk():
    from fang.constraints import Constraint, Literal, Ref, le
    from fang.graph import Snapshot
    from fang.identity import authored
    from fang.units import Quantity

    watts = Quantity.scalar("0", "W").dimension
    component = next(
        e for e in elaborate(Board, project_id=PROJECT).snapshot.entities.values()
        if e.kind == "component"
    )
    requirement = Requirement(authored("REQ-PWR"), statement="stay under a quarter watt")
    constraint = Constraint(
        authored("RULE-1"),
        constraint_kind="max_power",
        targets=(component.id,),
        expression=le(Ref(component.id, "power", watts), Literal.of(Quantity.scalar("0.25", "W"))),
        source="REQ-PWR",
    )
    snapshot = Snapshot(
        PROJECT,
        "REV-1",
        {component.id: component, "REQ-PWR": requirement, "RULE-1": constraint},
    )

    impact = impacted_by(snapshot, [component.id])
    assert "REQ-PWR" in impact["requirements"]


def test_a_verification_whose_evidence_changed_is_reported():
    from fang.graph import Snapshot
    from fang.identity import authored

    evidence = Evidence(authored("EVD-1"), claim="VIN max 17 V", document="DS")
    requirement = Requirement(authored("REQ-1"), statement="tolerate the input")
    verification = Verification(
        authored("VER-1"), verifies="REQ-1", evidence=("EVD-1",), result="PASS"
    )
    snapshot = Snapshot(
        PROJECT,
        "REV-1",
        {"EVD-1": evidence, "REQ-1": requirement, "VER-1": verification},
    )

    impact = impacted_by(snapshot, ["EVD-1"])
    assert impact["verifications"] == ["VER-1"]
    assert "REQ-1" in impact["requirements"]


def test_nothing_is_impacted_by_an_unrelated_change(board):
    impact = impacted_by(board.snapshot, ["CMP-does-not-exist"])
    assert impact == {"calculations": [], "requirements": [], "verifications": []}
