"""Spec: Physical Attributes Resolve Through The Entity They Realize; Routing
And Placement Constraints Are Checked By The Gate; Emitted Design Rules Are
Projections."""

from __future__ import annotations

import pytest

from conftest import PROJECT, tool_provenance
from fang.checks import DEFAULT_CHECKS
from fang.constraints import (
    CheckStatus,
    Constraint,
    ConstraintClass,
    Enforcement,
    Literal,
    Ref,
    ge,
    le,
)
from fang.diagnostics import FangError
from fang.entities import Net
from fang.graph import (
    AddEntity,
    CONSTRAINT_CHECK,
    KernelGraph,
    Snapshot,
    Transaction,
    default_checks,
)
from fang.identity import authored
from fang.kicad import compare_design_rules, emit_design_rules, emit_net_classes
from fang.physical import Board, Placement, Trace, physical_resolver
from fang.routing import (
    ROUTING_CHECK,
    net_classes,
    rule_projections,
    unresolved_references,
)
from fang.units import Quantity
from fang.values import Value, ValueStatus

MM = Quantity.scalar("0", "mm").dimension

NET = "NET-VBUS"


def segment(id: str, width: str, net: str = NET) -> Trace:
    return Trace(
        authored(id),
        net=net,
        width=Quantity.scalar(width, "mm"),
        provenance=tool_provenance(),
    )


def width_rule(
    minimum: str = "0.5",
    *,
    id: str = "RULE-W1",
    enforcement: Enforcement = Enforcement.HARD,
) -> Constraint:
    return Constraint(
        authored(id),
        constraint_class=ConstraintClass.ROUTING,
        constraint_kind="min_trace_width",
        targets=(NET,),
        expression=ge(
            Ref(NET, "physical.trace_width", MM),
            Literal.of(Quantity.scalar(minimum, "mm")),
        ),
        enforcement=enforcement,
        provenance=tool_provenance(),
    )


def routed(*widths: str, rule: Constraint | None = None) -> Snapshot:
    entities = {NET: Net(authored(NET))}
    for index, width in enumerate(widths):
        trace = segment(f"TRC-{index}", width)
        entities[trace.id] = trace
    constraint = rule or width_rule()
    entities[constraint.id] = constraint
    return Snapshot(PROJECT, "REV-000000", entities)


# -- 2.1 the resolver ------------------------------------------------------


def test_a_bare_attribute_still_resolves_from_parameters():
    net = Net(
        authored(NET),
        parameters={"trace_width": Value.explicit(Quantity.scalar("9", "mm"))},
    )
    snapshot = Snapshot(PROJECT, "REV-000000", {net.id: net, "TRC-0": segment("TRC-0", "0.2")})
    resolve = snapshot.resolver()
    # The authored parameter and the physical fact are different questions and
    # give different answers; neither shadows the other.
    assert resolve(NET, "trace_width").quantity.value == Quantity.scalar("9", "mm").value
    assert resolve(NET, "physical.trace_width").quantity.value == Quantity.scalar("0.2", "mm").value


def test_a_physical_reference_resolves_through_the_entity_it_realizes():
    snapshot = routed("0.8")
    value = snapshot.resolver()(NET, "physical.trace_width")
    assert value.known
    assert value.quantity.unit.symbol == "mm"


def test_a_reference_to_an_entity_that_is_not_there_resolves_unknown():
    snapshot = routed("0.8")
    assert not snapshot.resolver()("NET-ABSENT", "physical.trace_width").known


# -- 2.2 the aggregate -----------------------------------------------------


def test_several_segments_resolve_to_the_interval_they_span():
    value = routed("0.5", "1.2", "0.8").resolver()(NET, "physical.trace_width")
    assert value.quantity.kind == "range"
    assert value.quantity.minimum == Quantity.scalar("0.5", "mm").value
    assert value.quantity.maximum == Quantity.scalar("1.2", "mm").value


def test_the_aggregate_is_inferred_and_names_its_source():
    value = routed("0.5", "1.2").resolver()(NET, "physical.trace_width")
    assert value.status is ValueStatus.INFERRED
    assert value.source == NET
    assert not value.is_explicit


def test_one_segment_resolves_to_a_scalar_not_a_degenerate_range():
    value = routed("0.8").resolver()(NET, "physical.trace_width")
    assert value.quantity.kind == "scalar"


def test_a_rule_fails_when_the_narrowest_segment_fails():
    snapshot = routed("0.8", "0.3", "1.0")
    assert width_rule().evaluate(snapshot.resolver()) is CheckStatus.FAIL


def test_a_rule_passes_when_every_segment_passes():
    snapshot = routed("0.8", "0.6", "1.0")
    assert width_rule().evaluate(snapshot.resolver()) is CheckStatus.PASS


def test_a_maximum_rule_is_expressible_from_the_same_reference():
    """Resolving to the minimum alone would make this inexpressible."""
    maximum = Constraint(
        authored("RULE-W2"),
        constraint_class=ConstraintClass.ROUTING,
        constraint_kind="max_trace_width",
        targets=(NET,),
        expression=le(
            Ref(NET, "physical.trace_width", MM),
            Literal.of(Quantity.scalar("1.0", "mm")),
        ),
    )
    assert maximum.evaluate(routed("0.5", "0.8").resolver()) is CheckStatus.PASS
    assert maximum.evaluate(routed("0.5", "2.0").resolver()) is CheckStatus.FAIL


def test_segments_in_different_units_still_span_one_interval():
    net = Net(authored(NET))
    micro = Trace(authored("TRC-0"), net=NET, width=Quantity.scalar("800", "um"))
    milli = Trace(authored("TRC-1"), net=NET, width=Quantity.scalar("0.2", "mm"))
    snapshot = Snapshot(PROJECT, "REV-000000", {net.id: net, micro.id: micro, milli.id: milli})
    value = snapshot.resolver()(NET, "physical.trace_width")
    # The span reads in the first operand's unit, whichever units it was read in.
    assert value.quantity.kind == "range"
    assert value.quantity.unit.symbol in ("um", "mm")
    converted, _ = value.quantity.converted_to("mm")
    assert converted.minimum == Quantity.scalar("0.2", "mm").value
    assert converted.maximum == Quantity.scalar("0.8", "mm").value


# -- 2.3 undecided ---------------------------------------------------------


def test_an_unrouted_net_leaves_its_routing_rule_undecided():
    snapshot = routed()  # a net and a rule, but no copper
    assert width_rule().evaluate(snapshot.resolver()) is CheckStatus.UNKNOWN


def test_the_undecided_result_is_reported_as_undecided_and_names_its_gap():
    results = ROUTING_CHECK.run(routed())
    assert [r.status for r in results] == [CheckStatus.UNKNOWN]
    assert results[0].missing == (NET,)
    assert not results[0].blocking


def test_a_failing_result_names_the_copper_that_failed():
    results = ROUTING_CHECK.run(routed("0.8", "0.3"))
    assert results[0].status is CheckStatus.FAIL
    assert "TRC-1" in results[0].message


# -- 2.4 the vocabulary ----------------------------------------------------


def test_an_unrecognized_physical_attribute_resolves_unknown_rather_than_raising():
    snapshot = routed("0.8")
    assert not snapshot.resolver()(NET, "physical.no_such_attribute").known


def test_a_physical_reference_is_dimensionally_checked_at_write_time():
    with pytest.raises(FangError) as caught:
        ge(Ref(NET, "physical.trace_width", MM), Literal.of(Quantity.scalar("1", "A")))
    assert caught.value.diagnostic.code == "UNIT-0001"


def test_a_placement_carries_position_as_two_scalars():
    placement = Placement(
        authored("PLC-1"),
        component="CMP-1",
        x=Quantity.scalar("5", "mm"),
        y=Quantity.scalar("7", "mm"),
    )
    snapshot = Snapshot(PROJECT, "REV-000000", {placement.id: placement})
    resolve = snapshot.resolver()
    assert resolve("CMP-1", "physical.position_x").quantity.value == Quantity.scalar("5", "mm").value
    assert resolve("CMP-1", "physical.position_y").quantity.value == Quantity.scalar("7", "mm").value


def test_a_board_attribute_resolves_against_the_board_itself():
    board = Board(authored("PCB-1"), thickness=Quantity.scalar("1.6", "mm"))
    snapshot = Snapshot(PROJECT, "REV-000000", {board.id: board})
    value = snapshot.resolver()("PCB-1", "physical.board_thickness")
    assert value.quantity.value == Quantity.scalar("1.6", "mm").value


# -- 2.5 the check classes cover every class exactly once -------------------


def test_an_electrical_constraint_is_still_evaluated_under_the_same_name(
    snapshot, power_constraint
):
    entities = dict(snapshot.entities)
    entities[power_constraint.id] = power_constraint
    results = CONSTRAINT_CHECK.run(Snapshot(PROJECT, "REV-000000", entities))
    assert [(r.check, r.status) for r in results] == [("constraint", CheckStatus.PASS)]


def test_a_routing_constraint_is_evaluated_exactly_once():
    board = routed("0.8")
    evaluated = [r.subject for r in CONSTRAINT_CHECK.run(board)]
    evaluated += [r.subject for r in ROUTING_CHECK.run(board)]
    assert evaluated == ["RULE-W1"]


def test_every_constraint_class_is_covered_by_exactly_one_check_class():
    from fang.graph import STRUCTURAL_CLASSES
    from fang.routing import LAYOUT_CLASSES

    assert not (STRUCTURAL_CLASSES & LAYOUT_CLASSES)
    assert STRUCTURAL_CLASSES | LAYOUT_CLASSES == set(ConstraintClass)


def test_the_routing_check_reports_under_its_constraint_class():
    assert ROUTING_CHECK.run(routed("0.8"))[0].check == "routing"


# -- 2.6 the default check set ---------------------------------------------


def test_the_default_check_set_ships_the_routing_class():
    assert "routing" in {c.name for c in default_checks()}
    assert {c.name for c in default_checks()} == {c.name for c in DEFAULT_CHECKS}


def test_a_graph_built_with_no_explicit_checks_runs_the_routing_check():
    graph = KernelGraph(routed())
    trace = segment("TRC-0", "0.3")
    proposal = graph.propose(
        Transaction(graph.head.hash, (AddEntity(entity=trace),))
    )
    assert any(r.check == "routing" for r in proposal.checks)


def test_the_routing_check_is_not_required_when_nothing_touches_it(snapshot):
    graph = KernelGraph(routed())
    unrelated = Net(authored("NET-UNRELATED"))
    proposal = graph.propose(
        Transaction(graph.head.hash, (AddEntity(entity=unrelated),))
    )
    assert not any(r.check == "routing" for r in proposal.checks)


# -- 2.7 the gate ----------------------------------------------------------


def test_a_failing_hard_routing_rule_rejects_the_proposal():
    graph = KernelGraph(routed())
    before = graph.head.hash
    proposal = graph.propose(
        Transaction(graph.head.hash, (AddEntity(entity=segment("TRC-0", "0.3")),))
    )
    assert not proposal.accepted
    assert any("RULE-W1" == r.subject and r.blocking for r in proposal.checks)
    assert proposal.diff.changes, "a rejection still returns its diff"
    assert graph.head.hash == before


def test_an_advisory_routing_rule_reports_without_blocking():
    graph = KernelGraph(
        routed(rule=width_rule(enforcement=Enforcement.ADVISORY))
    )
    proposal = graph.propose(
        Transaction(graph.head.hash, (AddEntity(entity=segment("TRC-0", "0.3")),))
    )
    failed = [r for r in proposal.checks if r.status is CheckStatus.FAIL]
    assert failed and not any(r.blocking for r in failed)
    assert proposal.accepted


def test_a_passing_routing_rule_commits():
    graph = KernelGraph(routed())
    before = graph.head.hash
    proposal = graph.propose(
        Transaction(graph.head.hash, (AddEntity(entity=segment("TRC-0", "0.8")),))
    )
    assert proposal.accepted
    graph.commit(proposal)
    assert graph.head.hash != before


# -- the projections -------------------------------------------------------


def test_a_projection_carries_the_identity_of_what_it_projects():
    projections = rule_projections(routed("0.8"), layer="F.Cu")
    assert [p.as_dict() for p in projections] == [
        {
            "projects": "RULE-W1",
            "layer": "F.Cu",
            "net_classes": ["fang_min_trace_width_1c7a53"],
        }
    ]


def test_a_projection_does_not_restate_a_field_the_record_defines():
    from fang.constraints import Projection

    rule = width_rule()
    with pytest.raises(ValueError):
        Projection(rule, {"enforcement": "hard"})


# -- 4.1/4.2 net classes and the emitted rule file -------------------------


def clearance_rule(minimum: str = "0.25", *, net: str = NET, id: str = "RULE-C1"):
    return Constraint(
        authored(id),
        constraint_class=ConstraintClass.ROUTING,
        constraint_kind="min_clearance",
        targets=(net,),
        expression=ge(
            Ref(net, "physical.clearance", MM),
            Literal.of(Quantity.scalar(minimum, "mm")),
        ),
        provenance=tool_provenance(),
    )


OTHER = "NET-GND"


def two_nets() -> Snapshot:
    """Two named nets: one carrying two rules, one carrying a single rule."""
    entities = {
        NET: Net(authored(NET), aliases=("VBUS",)),
        OTHER: Net(authored(OTHER), aliases=("GND",)),
    }
    for constraint in (
        width_rule(),
        clearance_rule(),
        width_rule(id="RULE-W2").__class__(
            authored("RULE-W2"),
            constraint_class=ConstraintClass.ROUTING,
            constraint_kind="min_trace_width",
            targets=(OTHER,),
            expression=ge(
                Ref(OTHER, "physical.trace_width", MM),
                Literal.of(Quantity.scalar("0.5", "mm")),
            ),
            provenance=tool_provenance(),
        ),
    ):
        entities[constraint.id] = constraint
    return Snapshot(PROJECT, "REV-000000", entities)


def test_a_net_belongs_to_exactly_one_class():
    classes = net_classes(two_nets())
    memberships = [net for entry in classes for net in entry.nets]
    assert sorted(memberships) == sorted(set(memberships)) == sorted([NET, OTHER])


def test_nets_with_the_same_rules_share_a_class_and_others_do_not():
    classes = net_classes(two_nets())
    assert len(classes) == 2
    by_net = {net: entry.name for entry in classes for net in entry.nets}
    assert by_net[NET] != by_net[OTHER]


def test_a_net_class_names_the_constraints_it_came_from():
    classes = {entry.nets: entry for entry in net_classes(two_nets())}
    assert classes[(NET,)].projects == ("RULE-C1", "RULE-W1")
    assert classes[(OTHER,)].projects == ("RULE-W2",)


def test_a_net_class_carries_the_name_the_layout_tool_knows_the_net_by():
    classes = {entry.nets: entry for entry in net_classes(two_nets())}
    assert classes[(NET,)].net_names == ("VBUS",)


def test_a_net_no_layout_constraint_targets_is_in_no_class():
    snapshot = Snapshot(
        PROJECT, "REV-000000", {OTHER: Net(authored(OTHER), aliases=("GND",))}
    )
    assert net_classes(snapshot) == []


def test_a_class_name_is_stable_when_an_unrelated_rule_is_added():
    before = {e.nets: e.name for e in net_classes(routed("0.8"))}
    after = {e.nets: e.name for e in net_classes(two_nets())}
    assert before[(NET,)] != after[(NET,)]      # NET itself gained a rule
    assert after[(OTHER,)] == {
        e.nets: e.name
        for e in net_classes(
            Snapshot(
                PROJECT,
                "REV-000000",
                {
                    OTHER: Net(authored(OTHER), aliases=("GND",)),
                    "RULE-W2": two_nets().entities["RULE-W2"],
                },
            )
        )
    }[(OTHER,)]


def test_each_emitted_rule_names_the_constraint_it_projects():
    rules = emit_design_rules(rule_projections(two_nets()))
    for identifier in ("RULE-C1", "RULE-W1", "RULE-W2"):
        assert f'(rule "{identifier}"' in rules.text
    assert rules.projected == ("RULE-C1", "RULE-W1", "RULE-W2")


def test_an_emitted_rule_adds_only_class_specific_fields():
    projections = rule_projections(two_nets())
    record_fields = {
        "id", "class", "constraint_kind", "targets", "expression",
        "enforcement", "verification", "applicability", "source",
    }
    for projection in projections:
        assert not record_fields & set(projection.class_specific)


def test_an_emitted_rule_carries_the_bound_and_the_enforcement():
    rules = emit_design_rules(rule_projections(routed("0.8")))
    assert "(constraint track_width" in rules.text
    assert "(min 0.5mm)" in rules.text
    assert "(severity error)" in rules.text


def test_a_soft_rule_emits_as_a_warning_rather_than_being_dropped():
    rule = width_rule(enforcement=Enforcement.SOFT)
    rules = emit_design_rules(rule_projections(routed("0.8", rule=rule)))
    assert "(severity warning)" in rules.text


def test_a_rule_names_the_net_class_it_applies_to():
    snapshot = two_nets()
    names = {entry.nets: entry.name for entry in net_classes(snapshot)}
    rules = emit_design_rules(rule_projections(snapshot))
    assert f"A.NetClass == '{names[(NET,)]}'" in rules.text


def test_an_exclusive_bound_is_reported_rather_than_rounded_into_an_inclusive_one():
    from fang.constraints import compare

    rule = Constraint(
        authored("RULE-W1"),
        constraint_class=ConstraintClass.ROUTING,
        constraint_kind="min_trace_width",
        targets=(NET,),
        expression=compare(
            "gt",
            Ref(NET, "physical.trace_width", MM),
            Literal.of(Quantity.scalar("0.5", "mm")),
        ),
        provenance=tool_provenance(),
    )
    rules = emit_design_rules(rule_projections(routed("0.8", rule=rule)))
    assert rules.projected == ()
    assert not rules.lossless
    assert [d.code for d in rules.diagnostics()] == ["IMPORT-0001"]


def test_an_attribute_with_no_rule_that_means_the_same_is_reported():
    rule = Constraint(
        authored("RULE-T1"),
        constraint_class=ConstraintClass.MANUFACTURING,
        constraint_kind="max_board_thickness",
        targets=(NET,),
        expression=le(
            Ref(NET, "physical.board_thickness", MM),
            Literal.of(Quantity.scalar("1.6", "mm")),
        ),
        provenance=tool_provenance(),
    )
    rules = emit_design_rules(rule_projections(routed("0.8", rule=rule)))
    assert rules.projected == ()
    assert "board_thickness" not in rules.text


def test_a_maximum_reads_off_the_other_end_of_the_literal():
    rule = Constraint(
        authored("RULE-W1"),
        constraint_class=ConstraintClass.ROUTING,
        constraint_kind="max_trace_width",
        targets=(NET,),
        expression=le(
            Ref(NET, "physical.trace_width", MM),
            Literal.of(Quantity.scalar("2", "mm")),
        ),
        provenance=tool_provenance(),
    )
    rules = emit_design_rules(rule_projections(routed("0.8", rule=rule)))
    assert "(max 2mm)" in rules.text


def test_a_bound_written_in_another_unit_emits_in_millimetres():
    rule = Constraint(
        authored("RULE-W1"),
        constraint_class=ConstraintClass.ROUTING,
        constraint_kind="min_trace_width",
        targets=(NET,),
        expression=ge(
            Ref(NET, "physical.trace_width", MM),
            Literal.of(Quantity.scalar("500", "um")),
        ),
        provenance=tool_provenance(),
    )
    rules = emit_design_rules(rule_projections(routed("0.8", rule=rule)))
    assert "(min 0.5mm)" in rules.text


# -- 4.3 emission is deterministic ----------------------------------------


def test_emission_is_byte_identical_across_two_runs_of_one_snapshot():
    snapshot = two_nets()
    first = emit_design_rules(rule_projections(snapshot), snapshot=snapshot.hash).text
    second = emit_design_rules(rule_projections(snapshot), snapshot=snapshot.hash).text
    assert first.encode("utf-8") == second.encode("utf-8")


def test_net_class_emission_is_byte_identical_across_two_runs():
    snapshot = two_nets()
    assert emit_net_classes(net_classes(snapshot)) == emit_net_classes(
        net_classes(snapshot)
    )


def test_emission_is_byte_identical_across_processes_with_differing_hash_seeds():
    """The companion to the snapshot determinism test in test_serialization."""
    import subprocess
    import sys
    import textwrap

    program = textwrap.dedent(
        """
        import sys
        sys.path.insert(0, "tests")
        from conftest import PROJECT
        from test_routing import two_nets
        from fang.kicad import emit_design_rules, emit_net_classes
        from fang.routing import net_classes, rule_projections

        snapshot = two_nets()
        sys.stdout.write(emit_design_rules(rule_projections(snapshot)).text)
        sys.stdout.write(emit_net_classes(net_classes(snapshot)))
        """
    )
    outputs = []
    for seed in ("0", "1", "12345"):
        completed = subprocess.run(
            [sys.executable, "-c", program],
            capture_output=True,
            check=True,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
        )
        outputs.append(completed.stdout)
    assert outputs[0] == outputs[1] == outputs[2]


# -- an edited rule file is reported, never adopted ------------------------


def test_an_unedited_rule_file_reports_no_difference():
    snapshot = two_nets()
    projections = rule_projections(snapshot)
    text = emit_design_rules(projections).text
    assert compare_design_rules(text, projections) == []


def test_a_reformatted_rule_file_is_not_an_edited_one():
    snapshot = two_nets()
    projections = rule_projections(snapshot)
    text = emit_design_rules(projections).text
    # The comment header is dropped and every rule collapsed onto one line.
    body = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    reflowed = " ".join(body.split())
    assert compare_design_rules(reflowed, projections) == []


def test_an_edited_rule_is_reported_as_a_difference_from_the_registry():
    snapshot = two_nets()
    projections = rule_projections(snapshot)
    text = emit_design_rules(projections).text
    findings = compare_design_rules(text.replace("0.25mm", "0.1mm"), projections)
    assert [f.code for f in findings] == ["TOPO-0003"]
    assert "RULE-C1" in findings[0].message


def test_a_rule_added_by_hand_is_reported_and_not_adopted():
    snapshot = two_nets()
    projections = rule_projections(snapshot)
    text = emit_design_rules(projections).text
    text += '\n(rule "invented" (constraint track_width (min 9mm)))\n'
    findings = compare_design_rules(text, projections)
    assert [f.code for f in findings] == ["TOPO-0003"]
    # The registry is untouched: the file is a projection, not a place to write.
    assert emit_design_rules(rule_projections(snapshot)).text == emit_design_rules(
        projections
    ).text


def test_a_deleted_rule_is_reported_as_a_difference():
    snapshot = two_nets()
    projections = rule_projections(snapshot)
    text = emit_design_rules(projections).text
    without = text[: text.index('(rule "RULE-W2"')]
    assert [f.code for f in compare_design_rules(without, projections)] == ["TOPO-0003"]


# -- an undecided reference is said out loud ------------------------------


def test_an_unresolved_physical_reference_is_reported_under_its_code():
    findings = unresolved_references(routed())
    assert [f.code for f in findings] == ["TOPO-0001"]
    assert NET in findings[0].entities


def test_a_realized_reference_reports_nothing():
    assert unresolved_references(routed("0.8")) == []
