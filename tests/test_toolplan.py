"""Spec: Tool Plan Emission."""

import pytest

from fang.diagnostics import FangError
from fang.toolplan import Condition, Handle, PlanRecorder, ToolPlan


def test_a_tool_call_returns_a_handle_not_a_result():
    recorder = PlanRecorder()
    handle = recorder.record("layout", {"placers": ["pyplacer"]})
    assert isinstance(handle, Handle)
    assert handle.call == 0


def test_a_handle_attribute_is_a_symbolic_condition():
    recorder = PlanRecorder()
    report = recorder.record("check", {"profile": "jlcpcb-2layer"})
    condition = report.passed
    assert isinstance(condition, Condition)
    assert condition.attribute == "passed"


def test_reading_a_handle_during_elaboration_is_an_error():
    recorder = PlanRecorder()
    handle = recorder.record("check", {})
    for read in (
        lambda: bool(handle),
        lambda: handle == True,          # noqa: E712
        lambda: handle < 1,
        lambda: list(handle),
        lambda: len(handle),
    ):
        with pytest.raises(FangError) as caught:
            read()
        assert caught.value.diagnostic.code == "ELAB-0008"


def test_reading_a_condition_during_elaboration_is_an_error():
    recorder = PlanRecorder()
    report = recorder.record("check", {})
    with pytest.raises(FangError) as caught:
        if report.passed:
            pass
    assert caught.value.diagnostic.code == "ELAB-0008"


def test_a_condition_passed_as_an_argument_is_recorded_not_read():
    """The RFC's own example: export records a condition on the report."""
    recorder = PlanRecorder()
    layout = recorder.record("layout", {"routers": ["freerouting"]})
    report = recorder.record("check", {"layout": layout, "profile": "jlcpcb-2layer"})
    recorder.record("export", {"layout": layout, "format": "kicad", "require": report.passed})

    plan = recorder.plan()
    assert len(plan) == 3
    export = plan.as_dict()["calls"][2]
    assert export["arguments"]["require"] == {"call": 1, "attribute": "passed"}
    assert export["conditions"] == [{"call": 1, "attribute": "passed"}]


def test_the_plan_names_its_snapshot_and_keeps_call_order():
    recorder = PlanRecorder()
    for tool in ("layout", "check", "export"):
        recorder.record(tool, {})
    plan = recorder.plan().with_snapshot("sha256:abc")
    rendered = plan.as_dict()
    assert rendered["snapshot"] == "sha256:abc"
    assert [call["tool"] for call in rendered["calls"]] == ["layout", "check", "export"]


def test_the_plan_carries_a_source_map():
    from fang.diagnostics import SourceLocation

    recorder = PlanRecorder()
    recorder.record("layout", {}, source_location=SourceLocation("board.py", 12))
    entry = recorder.plan().as_dict()["source_map"][0]
    assert entry == {"call": 0, "source_location": {"file": "board.py", "line": 12}}


def test_the_plan_is_data_that_can_be_stored_and_replayed():
    from fang.serialization import canonical_bytes

    recorder = PlanRecorder()
    handle = recorder.record("layout", {"selection": "pareto"})
    recorder.record("export", {"layout": handle, "format": "kicad"})
    plan = recorder.plan().with_snapshot("sha256:abc")
    # Serializing it needs no program and no engine.
    assert canonical_bytes(plan.as_dict()) == canonical_bytes(plan.as_dict())


def test_tools_require_named_arguments(): 
    from fang.lang import ElaborationContext, tools

    with ElaborationContext():
        with pytest.raises(FangError):
            tools.layout("positional")


def test_the_tools_surface_records_rather_than_performs():
    from fang.lang import ElaborationContext, tools

    with ElaborationContext() as context:
        handle = tools.layout(placers=["pyplacer"], routers=["freerouting"])
        tools.export(layout=handle, format="kicad")
    plan = context.plan.plan()
    assert [call.tool for call in plan] == ["layout", "export"]
    assert plan.calls[0].source_location.file.endswith("test_toolplan.py")
