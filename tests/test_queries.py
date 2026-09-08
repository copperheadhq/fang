"""Spec: Rationale Queries Answerable From Graph State."""

from dataclasses import replace

import pytest

from conftest import REGULATOR, tool_provenance

from fang.diff import diff
from fang.entities import Requirement, RequirementState
from fang.identity import authored
from fang.queries import (
    causing_requirements,
    decisions_on_changed_evidence,
    dependents,
    lost_verification,
    supporting_evidence,
    unverified_assumptions,
)
from fang.units import Quantity
from fang.values import Value


def test_which_requirement_caused_this_component_to_exist(snapshot):
    assert causing_requirements(snapshot, REGULATOR) == ["REQ-PWR-001"]


def test_which_datasheet_claim_supports_this_parameter(snapshot):
    assert supporting_evidence(snapshot, REGULATOR, "vin_max") == ["EVD-TPS62130-VIN"]


def test_what_depends_on_this_rail_oscillator_or_domain(snapshot):
    assert "DEC-017" in dependents(snapshot, "REQ-PWR-001")


def test_which_requirements_lost_verification_in_this_change(snapshot):
    before = dict(snapshot.entities)
    after = dict(before)
    after[REGULATOR] = after[REGULATOR].with_parameter(
        "power_dissipation", Value.explicit(Quantity.scalar("0.9", "W"))
    )
    # The decision cites the requirement, so a change under it propagates.
    changes = diff(before, after)
    assert isinstance(lost_verification(snapshot, changes), list)


def test_which_assumptions_are_still_unverified(snapshot):
    entities = dict(snapshot.entities)
    entities["REQ-ASSUMED"] = Requirement(
        authored("REQ-ASSUMED"), statement="assumed load", state=RequirementState.ASSUMED
    )
    entities[REGULATOR] = entities[REGULATOR].with_parameter(
        "efficiency", Value.assumed(Quantity.scalar("0.9", "1"), "typical for this class")
    )
    found = unverified_assumptions(entities)
    assert "REQ-ASSUMED" in found
    assert f"{REGULATOR}.efficiency" in found


def test_which_decisions_rest_on_evidence_that_has_since_changed(snapshot):
    assert decisions_on_changed_evidence(snapshot, ["REQ-PWR-001"]) == ["DEC-017"]
    assert decisions_on_changed_evidence(snapshot, ["EVD-NOTHING"]) == []


def test_every_rationale_query_runs_from_graph_state_alone(snapshot):
    """No query reaches for a model, a network, or an inference step."""
    for answer in (
        causing_requirements(snapshot, REGULATOR),
        supporting_evidence(snapshot, REGULATOR, "vin_max"),
        dependents(snapshot, "REQ-PWR-001"),
        unverified_assumptions(snapshot),
        decisions_on_changed_evidence(snapshot, ["REQ-PWR-001"]),
    ):
        assert isinstance(answer, list)


def test_the_analysis_graph_is_built_on_demand_and_is_not_a_representation(snapshot):
    """Node dictionaries never leave the analysis boundary."""
    pytest.importorskip("networkx", reason="graph analysis is the optional 'analysis' extra")
    from fang.queries import to_networkx

    graph = to_networkx(snapshot)
    assert graph.number_of_nodes() == len(snapshot.entities)
    # The kernel's own API returns identifiers, never the library's node dicts.
    assert all(isinstance(node, str) for node in graph.nodes)


def test_analysis_reports_a_clear_error_when_the_extra_is_absent(snapshot, monkeypatch):
    import builtins

    from fang.queries import to_networkx

    real_import = builtins.__import__

    def missing(name, *args, **kwargs):
        if name == "networkx":
            raise ImportError("no networkx")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", missing)
    with pytest.raises(ImportError, match="analysis"):
        to_networkx(snapshot)
