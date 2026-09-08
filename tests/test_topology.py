"""Spec: Topology Intent Separate From Electrical Equivalence; Topology
Verification Enumerates Conductive Paths."""

import pytest

from conftest import conductive

from fang.constraints import CheckStatus, ConstraintClass, Enforcement
from fang.entities import Component, ConnectionKind
from fang.identity import authored
from fang.topology import (
    CONDUCTION_CONDITION,
    TopologyConstraint,
    TopologyMode,
    enumerate_paths,
)
from fang.units import Quantity
from fang.values import Value


def star_constraint(**kwargs):
    return TopologyConstraint(
        authored("TOPO-GND"),
        net="NET-GND",
        mode=TopologyMode.STAR,
        center="NET-MOTOR-STAR",
        branches=("DOM-LOGIC", "DOM-MOTOR"),
        **kwargs,
    )


def clean_star():
    entities = {}
    for connection in (
        conductive("CN-1", "DOM-LOGIC", "NET-MOTOR-STAR"),
        conductive("CN-2", "DOM-MOTOR", "NET-MOTOR-STAR"),
    ):
        entities[connection.id] = connection
    return entities


def looped_star():
    entities = clean_star()
    for connection in (
        conductive("CN-3", "DOM-LOGIC", "NET-CHASSIS"),
        conductive("CN-4", "NET-CHASSIS", "DOM-MOTOR"),
    ):
        entities[connection.id] = connection
    return entities


def test_topology_intent_is_a_constraint_within_the_one_registry():
    constraint = star_constraint()
    assert constraint.constraint_class is ConstraintClass.TOPOLOGY
    assert constraint.kind == "constraint"
    rendered = constraint.as_dict()
    assert rendered["class"] == "topology"
    assert rendered["mode"] == "star"
    assert rendered["center"] == "NET-MOTOR-STAR"
    assert rendered["branches"] == ["DOM-LOGIC", "DOM-MOTOR"]
    assert rendered["forbid_parallel_paths"] is True


def test_a_star_topology_names_its_centre():
    with pytest.raises(ValueError):
        TopologyConstraint(
            authored("TOPO-X"), net="NET-GND", mode=TopologyMode.STAR, branches=("A", "B")
        )


def test_domains_and_bonding_points_are_referenced_by_identity():
    constraint = star_constraint()
    assert "NET-MOTOR-STAR" in constraint.references()
    assert "DOM-LOGIC" in constraint.references()


def test_intent_holds_where_the_only_bond_is_through_the_centre():
    results = star_constraint().verify(clean_star())
    assert [r.status for r in results] == [CheckStatus.PASS]


def test_an_unpermitted_path_is_reported_with_the_elements_that_form_it():
    results = star_constraint().verify(looped_star())
    failures = [r for r in results if r.status is CheckStatus.FAIL]
    assert failures, "a parallel path must be reported"
    finding = failures[0]
    # The finding names the path, not merely a count.
    assert finding.paths
    assert "NET-CHASSIS" in finding.paths[0]
    assert "NET-CHASSIS" in finding.message
    assert "DOM-LOGIC" in finding.message and "DOM-MOTOR" in finding.message


def test_a_finding_names_each_path_rather_than_counting_them():
    entities = looped_star()
    extra = conductive("CN-5", "DOM-LOGIC", "NET-SHIELD")
    entities[extra.id] = extra
    bridge = conductive("CN-6", "NET-SHIELD", "DOM-MOTOR")
    entities[bridge.id] = bridge

    failures = [r for r in star_constraint().verify(entities) if r.status is CheckStatus.FAIL]
    assert len(failures) == 2
    named = {element for f in failures for element in f.paths[0]}
    assert {"NET-CHASSIS", "NET-SHIELD"} <= named


def test_a_conditional_path_carries_its_condition():
    entities = clean_star()
    diode = Component(
        authored("CMP-D1"),
        parameters={
            CONDUCTION_CONDITION: Value.assumed(
                Quantity.scalar("1", "1"), "forward biased above 0.7 V"
            )
        },
    )
    entities[diode.id] = diode
    for connection in (
        conductive("CN-7", "DOM-LOGIC", "CMP-D1"),
        conductive("CN-8", "CMP-D1", "DOM-MOTOR"),
    ):
        entities[connection.id] = connection

    failures = [r for r in star_constraint().verify(entities) if r.status is CheckStatus.FAIL]
    assert failures
    paths = enumerate_paths(entities, ["DOM-LOGIC"], ["DOM-MOTOR"])
    conditional = [p for p in paths if p.conditional]
    assert conditional
    assert "forward biased" in str(conditional[0])


def test_net_equivalence_alone_cannot_express_the_intent():
    """Both graphs are the same net; only the topology constraint tells them apart."""
    clean = star_constraint().verify(clean_star())
    looped = star_constraint().verify(looped_star())
    assert [r.status for r in clean] == [CheckStatus.PASS]
    assert any(r.status is CheckStatus.FAIL for r in looped)


def test_path_enumeration_is_deterministic():
    entities = looped_star()
    first = [p.elements for p in enumerate_paths(entities, ["DOM-LOGIC"], ["DOM-MOTOR"])]
    second = [p.elements for p in enumerate_paths(entities, ["DOM-LOGIC"], ["DOM-MOTOR"])]
    assert first == second


def test_a_dependency_edge_does_not_conduct():
    entities = clean_star()
    non_conductive = conductive(
        "CN-9", "DOM-LOGIC", "DOM-MOTOR", kind=ConnectionKind.DEPENDENCY
    )
    entities[non_conductive.id] = non_conductive
    results = star_constraint().verify(entities)
    assert [r.status for r in results] == [CheckStatus.PASS]


def test_an_advisory_topology_constraint_warns_rather_than_blocks():
    results = star_constraint(enforcement=Enforcement.SOFT).verify(looped_star())
    failures = [r for r in results if r.status is CheckStatus.FAIL]
    assert failures and not failures[0].blocking
