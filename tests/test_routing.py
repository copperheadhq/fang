"""Spec: Physical Attributes Resolve Through The Entity They Realize; Routing
And Placement Constraints Are Checked By The Gate."""

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
from fang.physical import Board, Placement, Trace, physical_resolver
from fang.routing import ROUTING_CHECK, rule_projections
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
        {"projects": "RULE-W1", "layer": "F.Cu"}
    ]


def test_a_projection_does_not_restate_a_field_the_record_defines():
    from fang.constraints import Projection

    rule = width_rule()
    with pytest.raises(ValueError):
        Projection(rule, {"enforcement": "hard"})
