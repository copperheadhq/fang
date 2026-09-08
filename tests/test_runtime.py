"""Spec: Tool Terminal Statuses; Conditions Resolve In The Operation Phase;
Tool Calls Are Idempotent; The Operation Phase Does Not Mutate Canonical State."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pytest

from fang.checks import DEFAULT_CHECKS
from fang.elaborate import elaborate
from fang.graph import KernelGraph, Realization
from fang.lang import System, kOhm, tools
from fang.parts import Resistor
from fang.runtime import (
    CheckTool,
    ExportTool,
    NetlistTool,
    RunContext,
    Status,
    ToolRegistry,
    ToolResult,
    default_registry,
    execute,
)

PROJECT = "PRJ-RUNTIME"


class Board(System):
    a = Resistor(resistance=10 * kOhm, package="R_0603")
    b = Resistor(resistance=4.7 * kOhm, package="R_0603")

    def architecture(self):
        self.a.p2 >> self.b.p1
        netlist = tools.netlist()
        report = tools.check(profile="jlcpcb-2layer")
        tools.export(netlist=netlist, format="kicad", source="board.py", require=report.passed)


@pytest.fixture
def elaborated():
    result = elaborate(Board, project_id=PROJECT)
    assert result.ok
    return result


def run(elaborated, registry=None, **kwargs):
    return execute(
        elaborated.plan,
        elaborated.snapshot,
        registry or default_registry(),
        traits=elaborated.traits,
        checks=DEFAULT_CHECKS,
        **kwargs,
    )


@dataclass
class AlwaysFails:
    name: str = "check"
    version: str = "1.0"

    def run(self, arguments: Mapping[str, Any], context: RunContext) -> ToolResult:
        return ToolResult(0, self.name, Status.FAILED, message="a rule failed")


@dataclass
class Raises:
    name: str = "check"
    version: str = "1.0"

    def run(self, arguments: Mapping[str, Any], context: RunContext) -> ToolResult:
        raise RuntimeError("the checker blew up")


# -- terminal statuses -----------------------------------------------------


def test_every_call_ends_in_a_terminal_status(elaborated):
    outcome = run(elaborated)
    assert len(outcome.results) == 3
    for result in outcome.results:
        assert isinstance(result.status, Status)
        assert result.status.terminal


def test_an_unregistered_tool_returns_unsupported(elaborated):
    outcome = run(elaborated, registry=ToolRegistry((NetlistTool(),)))
    statuses = {r.tool: r.status for r in outcome.results}
    assert statuses["check"] is Status.UNSUPPORTED
    assert "no tool named 'check' is registered" in outcome.result(1).message


def test_no_substitute_is_attempted_for_an_unsupported_tool(elaborated):
    outcome = run(elaborated, registry=ToolRegistry((NetlistTool(),)))
    assert outcome.result(1).value is None


def test_an_unsupported_format_is_reported_rather_than_degraded():
    class Odd(System):
        a = Resistor(resistance=10 * kOhm)

        def architecture(self):
            tools.export(format="gerber")

    result = elaborate(Odd, project_id=PROJECT)
    outcome = execute(result.plan, result.snapshot, default_registry(), traits=result.traits)
    assert outcome.results[0].status is Status.UNSUPPORTED
    assert "gerber" in outcome.results[0].message


def test_a_raising_tool_ends_failed_rather_than_propagating(elaborated):
    registry = ToolRegistry((NetlistTool(), Raises(), ExportTool()))
    outcome = run(elaborated, registry=registry)
    assert outcome.result(1).status is Status.FAILED
    assert "blew up" in outcome.result(1).message


# -- conditions ------------------------------------------------------------


def test_a_false_condition_skips_the_call_and_records_why(elaborated):
    registry = ToolRegistry((NetlistTool(), AlwaysFails(), ExportTool()))
    outcome = run(elaborated, registry=registry)

    export = outcome.result(2)
    assert export.status is Status.SKIPPED
    assert "resolved false" in export.message
    assert "passed" in export.message


def test_a_true_condition_runs_the_call(elaborated):
    outcome = run(elaborated)
    assert outcome.result(2).status is Status.SUCCEEDED


def test_a_call_conditioned_on_an_unsupported_one_is_skipped(elaborated):
    registry = ToolRegistry((NetlistTool(), ExportTool()))   # no check tool
    outcome = run(elaborated, registry=registry)
    assert outcome.result(1).status is Status.UNSUPPORTED
    assert outcome.result(2).status is Status.SKIPPED


def test_a_handle_resolves_to_the_earlier_result(elaborated):
    """The export receives the netlist the earlier call produced."""
    outcome = run(elaborated)
    export = outcome.result(2)
    assert export.status is Status.SUCCEEDED
    assert "exported 2 components" in export.message


# -- idempotence -----------------------------------------------------------


def test_the_same_plan_against_the_same_snapshot_repeats_its_result(elaborated):
    cache: dict = {}
    first = run(elaborated, cache=cache)
    second = run(elaborated, cache=cache)
    assert [r.as_dict() for r in first.results] == [r.as_dict() for r in second.results]


def test_a_different_snapshot_is_a_different_run(elaborated):
    from datetime import datetime, timezone

    other = elaborate(
        Board, project_id=PROJECT, built_at=datetime(2026, 1, 1, tzinfo=timezone.utc)
    )
    assert other.snapshot.hash != elaborated.snapshot.hash

    cache: dict = {}
    run(elaborated, cache=cache)
    keys_after_first = set(cache)
    execute(
        other.plan, other.snapshot, default_registry(), traits=other.traits,
        checks=DEFAULT_CHECKS, cache=cache,
    )
    assert set(cache) - keys_after_first, "a new snapshot must not reuse cached results"


# -- isolation from canonical state ---------------------------------------


def test_running_a_plan_leaves_the_graph_unchanged(elaborated):
    graph = KernelGraph(elaborated.snapshot)
    before = graph.head.hash
    run(elaborated)
    assert graph.head.hash == before


def test_realizations_name_their_parent_snapshot(elaborated):
    outcome = run(elaborated)
    realizations = outcome.realizations()
    assert realizations
    for realization in realizations:
        assert realization.parent_snapshot == elaborated.snapshot.hash
        assert realization.tools


def test_an_implied_semantic_change_returns_through_the_gate(elaborated):
    from fang.graph import SetParameter, Transaction
    from fang.units import Quantity
    from fang.values import Value

    graph = KernelGraph(elaborated.snapshot)
    component = next(
        e for e in graph.head.entities.values() if e.kind == "component"
    )
    realization = Realization(
        "layout",
        graph.head.hash,
        implied_changes=(
            SetParameter(
                target=component.id,
                name="power_rating",
                value=Value.explicit(Quantity.scalar("0.25", "W")),
                reason="derated during placement",
            ),
        ),
    )
    # It reaches canonical state only as a transaction.
    proposal = graph.apply(realization.to_transaction(graph.head.hash))
    assert proposal.accepted
    assert graph.head.entities[component.id].parameters["power_rating"].known


def test_export_writes_to_the_workspace_and_nowhere_else(tmp_path, elaborated):
    outcome = run(elaborated, workspace=tmp_path)
    assert outcome.result(2).status is Status.SUCCEEDED
    written = list(tmp_path.iterdir())
    assert [p.name for p in written] == ["design.net"]
    assert written[0].read_text().startswith('(export "version" "E"')


def test_the_registry_reports_what_it_carries():
    registry = default_registry()
    assert registry.names() == ["check", "export", "netlist"]
    assert "netlist" in registry
    assert registry.get("nothing") is None
