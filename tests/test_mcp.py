"""Spec: The Agent Surface, and the five requirements beside it.

One test per scenario in the fang-mcp delta spec. The projection layer is
exercised directly; the registration layer is exercised through the SDK where it
is installed and skipped by name where it is not.
"""

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import PROJECT, REGULATOR, FIXED_TIME, tool_provenance

from fang import __version__
from fang.constraints import CheckStatus
from fang.diagnostics import (
    MCP_MALFORMED_ARGUMENT,
    MCP_PATH_OUTSIDE_ROOT,
    MCP_UNACCEPTED_PROPOSAL,
    MCP_UNKNOWN_OPERATION,
    MCP_UNKNOWN_TOOL,
    TXN_APPROVAL_REQUIRED,
    TXN_STALE_SNAPSHOT,
    TXN_UNDECIDED_BLOCKED,
    FangError,
)
from fang.entities import Component
from fang.graph import CONSTRAINT_CHECK, Policy, Snapshot, Transaction
from fang.identity import derive
from fang.mcp import (
    PAGE,
    RATIONALE_QUESTIONS,
    ElaborationFailed,
    Session,
    build_operation,
    commit,
    guarded,
    project_checks,
    project_entities,
    project_entity,
    project_manifest,
    project_netlist,
    project_rationale,
    project_records,
    project_snapshot,
    project_summary,
    project_view,
    project_views,
    propose,
    render,
    workspace_entity_ids,
)
from fang.units import Quantity
from fang.values import Candidate, ConflictingValue, Value
from fang.views import REQUIRED_VIEWS
from fang.workspace import Workspace

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture
def project(tmp_path):
    """A project root with one real program inside it."""
    shutil.copy(EXAMPLES / "sensor_board" / "sensor_board.py", tmp_path)
    return tmp_path


@pytest.fixture
def session(project):
    return Session(project, "sensor_board.py", project_id="PRJ-MCP")


@pytest.fixture
def attached(snapshot):
    """A session over the shared fixture slice, with no program behind it."""
    return Session.over(snapshot, checks=(CONSTRAINT_CHECK,))


# --------------------------------------------------------------------------
# The Agent Surface
# --------------------------------------------------------------------------


def test_the_surface_holds_nothing_the_kernel_does_not(session):
    """The projection layer has no store of its own."""
    project_summary(session)
    project_checks(session)
    # Everything the session holds is the graph, the elaboration it came from,
    # and the proposals the client asked it to hold. There is no fact store.
    assert set(vars(session)) == {
        "root", "system", "project_id", "policy", "checks", "program",
        "elaborations", "_cache_key", "_cache", "_graph", "_proposals",
        "_proposal_count",
    }
    assert session._proposals == {}


def test_every_value_is_derivable_from_the_named_snapshot(session):
    answer = project_summary(session)
    assert answer["snapshot"] == session.graph().head.hash
    assert answer["entity_count"] == len(session.graph().head)


def test_a_rationale_question_is_answered_from_graph_structure(attached):
    answer = project_rationale(attached, "causing_requirements", entity=REGULATOR)
    assert answer["answer"] == ["REQ-PWR-001"]
    assert answer["question"] == "causing_requirements"


def test_every_rationale_question_is_reachable(attached, snapshot):
    reached = {}
    reached["causing_requirements"] = project_rationale(
        attached, "causing_requirements", entity=REGULATOR
    )
    reached["supporting_evidence"] = project_rationale(
        attached, "supporting_evidence", entity=REGULATOR, parameter="vin_max"
    )
    reached["dependents"] = project_rationale(attached, "dependents", entity="REQ-PWR-001")
    reached["unverified_assumptions"] = project_rationale(
        attached, "unverified_assumptions"
    )
    reached["decisions_on_changed_evidence"] = project_rationale(
        attached, "decisions_on_changed_evidence", evidence=["REQ-PWR-001"]
    )

    held = propose(
        attached,
        [{"op": "remove_entity", "target": "NET-CHASSIS", "reason": "test"}],
    )
    reached["lost_verification"] = project_rationale(
        attached, "lost_verification", proposal=held["handle"]
    )

    assert set(reached) == set(RATIONALE_QUESTIONS)
    assert reached["supporting_evidence"]["answer"] == ["EVD-TPS62130-VIN"]
    assert "DEC-017" in reached["decisions_on_changed_evidence"]["answer"]


def test_a_view_is_served_with_what_it_left_out(session):
    answer = project_view(session, "ground")
    assert answer["view"]["notes"] == answer["view"]["notes"]  # present, even if empty
    assert "notes" in answer["view"]
    assert set(answer["completeness"]) >= {"complete"}


def test_every_required_view_is_offered(session):
    listed = [entry["name"] for entry in project_views(session)["views"]]
    assert listed == list(REQUIRED_VIEWS)


def test_the_netlist_is_served_as_a_projection(session):
    answer = project_netlist(session)
    designators = {c["ref"] for c in answer["netlist"]["components"]}
    assert "U1" in designators and "R1" in designators


def test_every_response_names_the_snapshot_it_answered_from(session):
    head = session.graph().head.hash
    for answer in (
        project_summary(session),
        project_entities(session),
        project_checks(session),
        project_views(session),
        project_netlist(session),
        project_manifest(session),
    ):
        assert answer["snapshot"] == head


# --------------------------------------------------------------------------
# Agent Mutation Passes The Commit Gate
# --------------------------------------------------------------------------


def test_a_rejected_transaction_returns_its_explanation(attached):
    before = attached.graph().head.hash
    answer = propose(
        attached,
        [{"op": "remove_entity", "target": "NOPE-0001", "reason": "test"}],
    )
    proposal = answer["proposal"]
    assert proposal["accepted"] is False
    assert proposal["diagnostics"], "a rejection explains itself"
    assert "diff" in proposal
    assert attached.graph().head.hash == before


def test_a_stale_base_is_refused(attached):
    graph = attached.graph()
    stale = Transaction("sha256:" + "0" * 64, ())
    # The surface always proposes against the head, so staleness is reached the
    # way it is reached anywhere else: through the gate itself.
    proposal = graph.propose(stale)
    assert proposal.rejected
    assert [d.code for d in proposal.diagnostics] == [TXN_STALE_SNAPSHOT]
    assert graph.head.hash == attached.graph().head.hash


def test_committing_requires_an_accepted_proposal(attached):
    before = attached.graph().head.hash
    rejected = propose(
        attached, [{"op": "remove_entity", "target": "NOPE-0001", "reason": "test"}]
    )
    with pytest.raises(FangError) as caught:
        commit(attached, rejected["handle"])
    assert caught.value.diagnostic.code == MCP_UNACCEPTED_PROPOSAL
    assert attached.graph().head.hash == before


def test_an_undecided_result_over_a_must_be_decided_requirement_blocks(
    snapshot, power_constraint
):
    """The regulator's constraint is undecided once its parameter is unknown."""
    policy = Policy(must_be_decided=frozenset({"REQ-PWR-001"}))
    entities = dict(snapshot.entities)
    entities[power_constraint.id] = power_constraint
    session = Session.over(
        Snapshot(PROJECT, "REV-000000", entities), policy=policy,
        checks=(CONSTRAINT_CHECK,),
    )

    answer = propose(
        session,
        [
            {
                "op": "set_parameter",
                "target": REGULATOR,
                "name": "power_dissipation",
                "value": {"status": "unknown"},
                "reason": "the datasheet number is missing",
            }
        ],
    )
    proposal = answer["proposal"]
    codes = [d["code"] for d in proposal["diagnostics"]]
    assert TXN_UNDECIDED_BLOCKED in codes
    assert proposal["accepted"] is False
    undecided = [
        c for c in proposal["checks"] if c["status"] == CheckStatus.UNKNOWN.value
    ]
    assert undecided, "the response names the undecided result rather than a pass"


def test_the_agents_commit_is_bounded_by_the_active_policy(snapshot):
    policy = Policy(approvals_required=frozenset({"electrical-review"}))
    session = Session.over(snapshot, policy=policy, checks=(CONSTRAINT_CHECK,))
    answer = propose(
        session, [{"op": "remove_entity", "target": "NET-CHASSIS", "reason": "test"}]
    )
    proposal = answer["proposal"]
    assert proposal["accepted"] is False
    approval = [
        d for d in proposal["diagnostics"] if d["code"] == TXN_APPROVAL_REQUIRED
    ]
    assert approval, "the gate withholds the commit for want of approval"
    assert "electrical-review" in approval[0]["message"]


def test_a_granted_approval_lets_the_commit_through(snapshot):
    policy = Policy(
        approvals_required=frozenset({"electrical-review"}),
        approvals_granted=frozenset({"electrical-review"}),
    )
    session = Session.over(snapshot, policy=policy, checks=(CONSTRAINT_CHECK,))
    answer = propose(
        session, [{"op": "remove_entity", "target": "NET-CHASSIS", "reason": "test"}]
    )
    assert answer["proposal"]["accepted"] is True


def test_a_commit_names_the_revision_the_head_moved_to(attached):
    before = attached.graph().head.hash
    answer = propose(
        attached, [{"op": "remove_entity", "target": "NET-CHASSIS", "reason": "test"}]
    )
    assert answer["proposal"]["accepted"] is True

    committed = commit(attached, answer["handle"])
    assert committed["committed"] is True
    assert committed["from"] == before
    assert committed["snapshot"] != before
    assert committed["revision_id"] == attached.graph().head.revision_id
    assert "NET-CHASSIS" not in attached.graph().head.entities


def test_only_the_operation_kinds_the_gate_evaluates_are_constructible():
    with pytest.raises(FangError) as caught:
        build_operation({"op": "rewrite_everything", "target": "X"})
    assert caught.value.diagnostic.code == MCP_UNKNOWN_OPERATION


def test_the_surface_offers_no_route_around_the_gate():
    """`apply()` proposes and commits in one call, so it is not exposed."""
    source = (Path(__file__).resolve().parent.parent / "fang" / "mcp.py").read_text()
    assert ".apply(" not in source
    assert ".propose(" in source and ".commit(" in source


# --------------------------------------------------------------------------
# Deterministic Agent Responses
# --------------------------------------------------------------------------


def test_the_same_question_twice_gives_the_same_bytes(session):
    first = render(project_summary(session)).encode("utf-8")
    second = render(project_summary(session)).encode("utf-8")
    assert first == second


def test_every_projection_is_byte_stable(session):
    for call in (project_summary, project_entities, project_checks, project_views):
        assert render(call(session)) == render(call(session))


def test_responses_do_not_depend_on_hash_ordering(project):
    """The same question in two processes with differing hash seeds."""
    script = (
        "import sys;"
        "sys.path.insert(0, %r);"
        "from fang.mcp import Session, project_summary, project_entities, render;"
        "s = Session(%r, 'sensor_board.py', project_id='PRJ-MCP');"
        "sys.stdout.write(render(project_summary(s)) + render(project_entities(s)))"
        % (str(Path(__file__).resolve().parent.parent), str(project))
    )
    outputs = []
    for seed in ("0", "1"):
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
        )
        assert result.returncode == 0, result.stderr
        outputs.append(result.stdout)
    assert outputs[0] == outputs[1]


def test_a_magnitude_crosses_the_boundary_as_a_decimal(attached):
    answer = project_entity(attached, REGULATOR)
    quantity = answer["entity"]["parameters"]["power_dissipation"]["quantity"]
    assert isinstance(quantity["value"], str)
    assert quantity["value"] == "0.1"
    # And it survives serialization as a quoted decimal, never a float literal.
    assert '"value":"0.1"' in render(answer)


# --------------------------------------------------------------------------
# The Agent Session Is Bound To One Project
# --------------------------------------------------------------------------


def test_a_path_outside_the_project_root_is_refused(project):
    session = Session(project, "sensor_board.py", project_id="PRJ-MCP")
    for outside in ("../escape.py", "/etc/passwd", str(Path(project).parent / "x.py")):
        with pytest.raises(FangError) as caught:
            session.resolve(outside)
        assert caught.value.diagnostic.code == MCP_PATH_OUTSIDE_ROOT


def test_binding_a_program_outside_the_root_is_refused(tmp_path):
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n")
    root = tmp_path / "root"
    root.mkdir()
    with pytest.raises(FangError) as caught:
        Session(root, outside)
    assert caught.value.diagnostic.code == MCP_PATH_OUTSIDE_ROOT


def test_reload_contains_the_program_a_client_names(project):
    session = Session(project, "sensor_board.py", project_id="PRJ-MCP")
    with pytest.raises(FangError) as caught:
        session.reload("../elsewhere.py")
    assert caught.value.diagnostic.code == MCP_PATH_OUTSIDE_ROOT


def test_elaboration_for_an_agent_obeys_the_sandbox(project):
    """A reach past the boundary is reported, not served."""
    program = Path(project) / "reaching.py"
    program.write_text(
        "import socket\n"
        "from fang.lang import System, kOhm\n"
        "from fang.parts import Resistor\n"
        "\n"
        "\n"
        "class Reaching(System):\n"
        "    r = Resistor(resistance=10 * kOhm, package='R_0603_1608Metric')\n"
        "\n"
        "    def architecture(self):\n"
        "        socket.socket()\n"
    )
    session = Session(project, "reaching.py", project_id="PRJ-MCP")
    answer = guarded(project_summary, session)
    assert answer["ok"] is False
    assert answer["diagnostics"], "the violation is reported rather than served"


def test_the_session_never_disables_the_sandbox():
    """The one way to weaken elaboration is not taken anywhere in the surface."""
    source = (Path(__file__).resolve().parent.parent / "fang" / "mcp.py").read_text()
    assert "enforce_sandbox" not in source.replace(
        "module never passes `enforce_sandbox=False`.", ""
    )


def test_the_workspace_and_the_program_agree_on_the_entity_set(project):
    from fang.cli import main

    assert main(["build", str(Path(project) / "sensor_board.py"),
                 "--project", "PRJ-MCP", "-C", str(project)]) in (0, 1)
    session = Session(project, "sensor_board.py", project_id="PRJ-MCP")
    persisted = workspace_entity_ids(session)
    if persisted:  # a build that reached the gate wrote the records
        assert persisted == sorted(session.graph().head.entities)


def test_the_manifest_is_served_where_a_workspace_exists(project):
    Workspace(project).create()
    session = Session(project, "sensor_board.py", project_id="PRJ-MCP")
    assert project_manifest(session)["workspace"] is None  # created, not yet written


def test_a_second_read_does_not_re_execute_the_program(session):
    project_summary(session)
    assert session.elaborations == 1
    project_checks(session)
    project_entities(session)
    project_views(session)
    assert session.elaborations == 1, "a read-only question re-uses the elaboration"


def test_a_changed_program_is_elaborated_again(session, project):
    project_summary(session)
    assert session.elaborations == 1
    program = Path(project) / "sensor_board.py"
    program.write_text(program.read_text() + "\n# a comment changes the content hash\n")
    session.reload()
    project_summary(session)
    assert session.elaborations == 2


def test_entity_reads_are_scoped_and_paginated(session):
    total = len(session.graph().head)
    page = project_entities(session, limit=3)
    assert len(page["entities"]) == 3
    assert page["total"] == total and page["offset"] == 0

    second = project_entities(session, offset=3, limit=3)
    assert second["entities"] != page["entities"]

    scoped = project_entities(session, kind="component")
    assert scoped["total"] < total
    assert {e["kind"] for e in scoped["entities"]} == {"component"}


def test_the_whole_snapshot_is_a_deliberate_ask(session):
    """The default page is bounded; the logical root is a separate resource."""
    assert len(project_entities(session)["entities"]) <= PAGE
    root = project_snapshot(session)
    assert root["project_id"] == "PRJ-MCP"
    assert project_records(session).count("\n") == len(session.graph().head)


def test_a_program_that_fails_to_elaborate_yields_diagnostics_not_a_snapshot(project):
    program = Path(project) / "broken.py"
    program.write_text(
        "from fang.lang import System, V, kOhm, require\n"
        "from fang.parts import Resistor\n"
        "\n"
        "\n"
        "class Broken(System):\n"
        "    r = Resistor(resistance=10 * kOhm, package='R_0603_1608Metric')\n"
        "\n"
        "    def constraints(self):\n"
        "        require(self.r.resistance >= 1 * V)\n"
    )
    session = Session(project, "broken.py", project_id="PRJ-MCP")
    answer = guarded(project_summary, session)
    assert answer["ok"] is False
    assert "snapshot" not in answer
    assert answer["diagnostics"]
    for diagnostic in answer["diagnostics"]:
        assert diagnostic["code"]


# --------------------------------------------------------------------------
# Undecided Crosses The Agent Boundary Intact
# --------------------------------------------------------------------------


def test_an_undecided_check_is_reported_as_undecided(snapshot, power_constraint):
    entities = dict(snapshot.entities)
    entities[power_constraint.id] = power_constraint
    session = Session.over(
        Snapshot(PROJECT, "REV-000000", entities), checks=(CONSTRAINT_CHECK,)
    )
    answer = propose(
        session,
        [
            {
                "op": "set_parameter",
                "target": REGULATOR,
                "name": "power_dissipation",
                "value": {"status": "unknown"},
                "reason": "the datasheet number is missing",
            }
        ],
    )
    statuses = {c["status"] for c in answer["proposal"]["checks"]}
    assert CheckStatus.UNKNOWN.value in statuses
    assert CheckStatus.UNKNOWN.value not in (
        CheckStatus.PASS.value,
        CheckStatus.FAIL.value,
    )


def test_the_check_projection_counts_undecided_as_its_own_status(snapshot, power_constraint):
    """An unknown operand makes the check undecided, and it is counted as such."""
    entities = dict(snapshot.entities)
    entities[power_constraint.id] = power_constraint
    entities[REGULATOR] = entities[REGULATOR].with_parameter(
        "power_dissipation", Value.unknown()
    )
    session = Session.over(
        Snapshot(PROJECT, "REV-000000", entities), checks=(CONSTRAINT_CHECK,)
    )
    answer = project_checks(session)
    assert set(answer["counts"]) == {s.value for s in CheckStatus}
    assert sum(answer["counts"].values()) == answer["total"]
    assert answer["counts"][CheckStatus.UNKNOWN.value] > 0
    assert all(r["status"] in answer["counts"] for r in answer["results"])


def test_an_unknown_value_is_distinguishable_from_an_absent_one(attached):
    answer = propose(
        attached,
        [
            {
                "op": "set_parameter",
                "target": REGULATOR,
                "name": "efficiency",
                "value": {"status": "unknown"},
                "reason": "not yet measured",
            }
        ],
    )
    commit(attached, answer["handle"])

    parameters = project_entity(attached, REGULATOR)["entity"]["parameters"]
    assert parameters["efficiency"] == {"status": "unknown"}
    assert "quantity" not in parameters["efficiency"]
    assert "never_set" not in parameters, "an absent parameter is simply absent"
    assert parameters["efficiency"] is not None


def test_an_unknown_is_not_rendered_as_null_zero_or_false(attached):
    answer = propose(
        attached,
        [
            {
                "op": "set_parameter",
                "target": REGULATOR,
                "name": "efficiency",
                "value": {"status": "unknown"},
                "reason": "not yet measured",
            }
        ],
    )
    commit(attached, answer["handle"])
    text = render(project_entity(attached, REGULATOR))
    assert '"efficiency":{"status":"unknown"}' in text


def test_a_conflicting_value_keeps_its_candidates(slice_entities):
    conflict = ConflictingValue(
        (
            Candidate(Value.explicit(Quantity.scalar("17", "V")), "EVD-TPS62130-VIN"),
            Candidate(Value.explicit(Quantity.scalar("19", "V")), "EVD-VENDOR-ERRATA"),
        )
    )
    regulator = slice_entities[REGULATOR]
    entities = dict(slice_entities)
    entities[REGULATOR] = regulator.with_parameter("vin_max", conflict)
    session = Session.over(
        Snapshot(PROJECT, "REV-000000", entities), checks=(CONSTRAINT_CHECK,)
    )

    projected = project_entity(session, REGULATOR)["entity"]["parameters"]["vin_max"]
    sources = [c["source"] for c in projected["candidates"]]
    assert sources == ["EVD-TPS62130-VIN", "EVD-VENDOR-ERRATA"]
    assert "resolution" not in projected, "no candidate is chosen on the agent's behalf"


# --------------------------------------------------------------------------
# The Agent Surface Refuses With A Code
# --------------------------------------------------------------------------


def test_an_unknown_rationale_question_is_refused(attached):
    with pytest.raises(FangError) as caught:
        project_rationale(attached, "why_is_the_sky_blue")
    assert caught.value.diagnostic.code == MCP_UNKNOWN_TOOL


def test_a_malformed_argument_is_refused(attached):
    for call, args in (
        (project_entity, ("NOT-AN-ENTITY",)),
        (project_view, ("not-a-view",)),
    ):
        with pytest.raises(FangError) as caught:
            call(attached, *args)
        assert caught.value.diagnostic.code == MCP_MALFORMED_ARGUMENT

    with pytest.raises(FangError) as caught:
        project_entities(attached, limit=0)
    assert caught.value.diagnostic.code == MCP_MALFORMED_ARGUMENT


def test_a_malformed_operation_is_refused_before_anything_is_written(attached):
    before = attached.graph().head.hash
    for bad in (
        {"op": "set_parameter", "target": REGULATOR},
        {"op": "set_parameter", "target": REGULATOR, "name": "x", "value": {}},
        {"op": "connect", "from": "A", "to": "B", "id": "C", "kind": "telepathy"},
        {"op": "remove_entity"},
    ):
        with pytest.raises(FangError) as caught:
            build_operation(bad)
        assert caught.value.diagnostic.code in (
            MCP_MALFORMED_ARGUMENT,
            MCP_UNKNOWN_OPERATION,
        )
    assert attached.graph().head.hash == before


def test_an_empty_transaction_is_refused(attached):
    with pytest.raises(FangError) as caught:
        propose(attached, [])
    assert caught.value.diagnostic.code == MCP_MALFORMED_ARGUMENT


def test_a_refusal_is_rendered_rather_than_a_fabricated_answer(attached):
    answer = guarded(project_entity, attached, "NOT-AN-ENTITY")
    assert answer == {
        "ok": False,
        "diagnostics": [
            {
                "code": MCP_MALFORMED_ARGUMENT,
                "severity": "error",
                "message": "no entity 'NOT-AN-ENTITY' in this snapshot",
            }
        ],
    }


# --------------------------------------------------------------------------
# Packaging and the command
# --------------------------------------------------------------------------


def test_the_projection_layer_imports_no_protocol_sdk():
    """The core stays standard library only; only the registration layer imports."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys, fang.mcp; "
            "assert 'mcp' not in sys.modules, sorted(sys.modules); "
            "print('clean')",
        ],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "clean" in result.stdout


def test_the_command_is_offered(capsys):
    from fang.cli import build_parser

    build_parser().print_help()
    assert "mcp" in capsys.readouterr().out


def test_a_missing_dependency_is_named_and_no_degraded_server_starts(
    project, monkeypatch, capsys
):
    import builtins

    from fang.cli import EXIT_FAILED, main

    real_import = builtins.__import__

    def refuse(name, *args, **kwargs):
        if name == "mcp" or name.startswith("mcp."):
            raise ImportError("no module named 'mcp'")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "fang.mcp", raising=False)
    monkeypatch.setattr(builtins, "__import__", refuse)
    code = main(["mcp", str(Path(project) / "sensor_board.py"), "-C", str(project)])
    monkeypatch.setattr(builtins, "__import__", real_import)

    assert code == EXIT_FAILED
    assert "MCP-0005" in capsys.readouterr().err


# --------------------------------------------------------------------------
# The registration layer
# --------------------------------------------------------------------------

#: The registration layer needs the optional extra. Skipped by name where it is
#: absent, so the suite reports what it actually demonstrated.
requires_sdk = pytest.mark.skipif(
    importlib.util.find_spec("mcp") is None,
    reason="the mcp SDK is not installed; it is the optional 'mcp' extra",
)


@requires_sdk
def test_the_server_registers_every_tool_and_resource(session):
    import asyncio

    from fang.mcp import build_server

    server = build_server(session)
    tools = {tool.name for tool in asyncio.run(server.list_tools())}
    assert tools == {
        "summary", "entities", "entity", "manifest", "netlist", "checks",
        "views", "view", "rationale", "propose", "commit", "reload",
    }
    resources = {str(r.uri) for r in asyncio.run(server.list_resources())}
    assert resources == {"fang://snapshot", "fang://records"}


@requires_sdk
def test_a_tool_returns_the_canonical_bytes_the_kernel_produced(session):
    import asyncio

    from fang.mcp import build_server

    server = build_server(session)
    result = asyncio.run(server.call_tool("summary", {}))
    payload = result.content[0].text
    assert payload == render(project_summary(session))
    assert json.loads(payload)["snapshot"] == session.graph().head.hash


@requires_sdk
def test_an_unknown_tool_is_refused_by_the_server(session):
    import asyncio

    from fang.mcp import build_server

    server = build_server(session)
    with pytest.raises(Exception) as caught:
        asyncio.run(server.call_tool("delete_the_board", {}))
    assert "delete_the_board" in str(caught.value)


@requires_sdk
def test_the_mutation_tools_reach_the_gate_over_the_protocol(attached):
    """The whole mutation path, called the way a client calls it.

    The tools that carry it are the two whose protocol names collide with the
    functions they delegate to, so this exercises them through `call_tool`
    rather than through the projection the other mutation tests use.
    """
    import asyncio

    from fang.mcp import build_server

    server = build_server(attached)
    before = attached.graph().head.hash

    answer = json.loads(
        asyncio.run(
            server.call_tool(
                "propose",
                {"operations": [{"op": "remove_entity", "target": "NET-CHASSIS",
                                 "reason": "test"}]},
            )
        ).content[0].text
    )
    assert answer["ok"] is True, answer
    assert answer["proposal"]["accepted"] is True
    assert attached.graph().head.hash == before, "proposing moves nothing"

    committed = json.loads(
        asyncio.run(
            server.call_tool("commit", {"handle": answer["handle"]})
        ).content[0].text
    )
    assert committed["committed"] is True
    assert committed["from"] == before
    assert attached.graph().head.hash != before


def test_a_transaction_records_the_path_it_arrived_by(attached):
    """`Transaction.origin` differs by mutation path, and nothing else does."""
    answer = propose(
        attached, [{"op": "remove_entity", "target": "NET-CHASSIS", "reason": "test"}]
    )
    origin = answer["proposal"]["transaction"]["origin"]
    assert origin["actor"] == {"kind": "adapter", "id": "fang-mcp", "version": __version__}
    assert origin["activity"] == "mcp:propose"
    assert origin["revision_id"] == attached.graph().head.revision_id


def test_a_magnitude_that_is_not_a_number_is_refused_with_a_code(attached):
    """An untrusted magnitude is a coded refusal, not a decimal exception."""
    for bad in ("abc", None, [1], "", "1.2.3"):
        answer = guarded(
            propose,
            attached,
            [
                {
                    "op": "set_parameter",
                    "target": REGULATOR,
                    "name": "power_dissipation",
                    "value": {
                        "status": "explicit",
                        "quantity": {"magnitude": bad, "unit": "W"},
                    },
                    "reason": "test",
                }
            ],
        )
        assert answer["ok"] is False, bad
        assert [d["code"] for d in answer["diagnostics"]] == [MCP_MALFORMED_ARGUMENT]


def test_a_reload_that_names_nothing_leaves_the_session_bound(session):
    """A refused reload is survivable: the session keeps the program it had."""
    program = session.program
    head = session.graph().head.hash

    with pytest.raises(FangError) as caught:
        session.reload("not_a_program.py")
    assert caught.value.diagnostic.code == MCP_MALFORMED_ARGUMENT
    assert session.program == program
    assert session.graph().head.hash == head


def test_a_program_named_for_a_dependency_does_not_replace_it(project):
    """The client names the program, so the module it registers is namespaced."""
    shutil.copy(Path(project) / "sensor_board.py", Path(project) / "mcp.py")
    before = sys.modules.get("mcp")

    session = Session(project, "mcp.py", project_id="PRJ-MCP")
    assert session.graph().head.entities

    assert sys.modules.get("mcp") is before
    assert "fang_program_mcp" in sys.modules
    del sys.modules["fang_program_mcp"]
