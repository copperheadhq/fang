"""Spec: Semantic Diff Classification."""

from dataclasses import replace

from conftest import PROJECT, REGULATOR, WATTS, tool_provenance

from fang.constraints import CheckStatus, Constraint, Literal, Ref, le
from fang.diff import ChangeClass, diff
from fang.entities import Component, Connection, ConnectionKind, Requirement
from fang.identity import authored, derive
from fang.units import Quantity
from fang.values import Value


def component(name="CMP-A", **kwargs):
    return Component(authored(name), **kwargs)


def test_a_component_addition_and_removal_are_classified():
    before = {"CMP-A": component()}
    after = {"CMP-A": component(), "CMP-B": component("CMP-B")}
    classes = {c.type for c in diff(before, after)}
    assert ChangeClass.COMPONENT_ADDED in classes
    classes = {c.type for c in diff(after, before)}
    assert ChangeClass.COMPONENT_REMOVED in classes


def test_a_connection_addition_is_classified():
    connection = Connection(
        authored("CN-1"), connection_kind=ConnectionKind.POWER, source="CMP-A", target="CMP-B"
    )
    changes = diff({}, {"CN-1": connection})
    assert changes.changes[0].type is ChangeClass.CONNECTION_ADDED


def test_a_parameter_change_names_the_before_and_after():
    before = {"CMP-R42": component("CMP-R42", parameters={
        "resistance": Value.explicit(Quantity.scalar("10", "kOhm"))
    })}
    after = {"CMP-R42": component("CMP-R42", parameters={
        "resistance": Value.explicit(Quantity.scalar("4.7", "kOhm"))
    })}
    changes = list(diff(before, after))
    parameter = next(c for c in changes if c.type is ChangeClass.PARAMETER_CHANGED)
    assert parameter.subject == "CMP-R42.resistance"
    assert parameter.before == "10 kOhm"
    assert parameter.after == "4.7 kOhm"


def test_a_presentation_change_is_separable_from_an_electrical_change():
    identity = derive(PROJECT, "component", "system.x.u1")
    before = {identity.id: Component(identity, provenance=tool_provenance(), designator="U1")}
    renamed_identity = replace(identity, display_name="Main Regulator")
    after = {identity.id: Component(renamed_identity, provenance=tool_provenance(), designator="U1")}

    changes = diff(before, after)
    assert not changes.electrical
    assert all(c.type is ChangeClass.RENAME for c in changes)


def test_an_electrical_change_is_marked_electrical():
    before = {"CMP-A": component(part="OLD")}
    after = {"CMP-A": component(part="NEW")}
    changes = diff(before, after)
    assert changes.electrical
    assert changes.electrical[0].type is ChangeClass.COMPONENT_CHANGED


def test_a_preserved_identity_rename_is_not_an_add_and_a_remove():
    old = derive(PROJECT, "component", "system.power.old_name", key="buck_main")
    new = derive(PROJECT, "component", "system.power.new_name", key="buck_main")
    # An explicit key pins identity, so the id itself is unchanged.
    assert old.id == new.id

    # A path-derived move without a key still reports as a rename via the uuid.
    a = derive(PROJECT, "component", "system.a.u1")
    before = {a.id: Component(a, provenance=tool_provenance())}
    moved = replace(a, display_name="renamed")
    after = {a.id: Component(moved, provenance=tool_provenance())}
    changes = list(diff(before, after))
    assert [c.type for c in changes] == [ChangeClass.RENAME]


def test_a_verification_status_change_is_classified():
    rule = Constraint(
        authored("RULE-1"),
        constraint_kind="max_power",
        targets=("CMP-A",),
        expression=le(Ref("CMP-A", "p", WATTS), Literal.of(Quantity.scalar("1", "W"))),
    )
    verified = replace(rule, verification_status=CheckStatus.PASS)
    changes = list(diff({"RULE-1": rule}, {"RULE-1": verified}))
    assert any(c.type is ChangeClass.VERIFICATION_STATUS_CHANGED for c in changes)


def test_a_diff_carries_the_impact_of_a_change():
    resistor = component("CMP-R42", parameters={
        "resistance": Value.explicit(Quantity.scalar("10", "kOhm"))
    })
    requirement = Requirement(authored("REQ-PWR-3V3"), statement="3V3 rail")
    rule = Constraint(
        authored("RULE-1"),
        constraint_kind="divider_ratio",
        targets=("CMP-R42",),
        expression=le(Ref("CMP-R42", "resistance", Quantity.scalar("0", "Ohm").dimension),
                      Literal.of(Quantity.scalar("100", "kOhm"))),
        source="REQ-PWR-3V3",
    )
    before = {"CMP-R42": resistor, "REQ-PWR-3V3": requirement, "RULE-1": rule}
    after = dict(before)
    after["CMP-R42"] = component("CMP-R42", parameters={
        "resistance": Value.explicit(Quantity.scalar("4.7", "kOhm"))
    })

    changes = diff(before, after)
    assert "RULE-1" in changes.invalidated
    assert "REQ-PWR-3V3" in changes.invalidated


def test_the_required_change_classes_all_exist():
    required = {
        "component_added", "component_removed", "component_changed",
        "connection_added", "connection_removed", "parameter_changed",
        "interface_changed", "pin_assignment_changed", "domain_changed",
        "topology_intent_changed", "model_or_trait_changed",
        "requirement_changed", "decision_changed", "evidence_changed",
        "verification_status_changed", "constraint_changed",
        "physical_changed", "manufacturing_data_changed", "rename",
    }
    assert required <= {c.value for c in ChangeClass}
