"""Spec: Rule Checks Are Evidence; Verification Tools Sit Behind One Protocol."""

from __future__ import annotations

import json
import re
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from conftest import FIXED_TIME

from fang import diagnostics
from fang.checks import DEFAULT_CHECKS
from fang.diagnostics import FangError
from fang.elaborate import elaborate
from fang.graph import KernelGraph
from fang.interfaces import AnalogOut, Pin, PinMap
from fang.lang import Part, System, kOhm, nF
from fang.parts import Capacitor, Resistor
from fang.rationale import Requires
from fang.rulecheck import KICAD_ERC, REPORT, KicadErcTool, judge, parse_erc
from fang.runtime import Status
from fang.simulation import Level
from fang.verification import (
    ANSWERED,
    UNSUPPORTED,
    Checks,
    RawRun,
    ToolRegistry,
    answer,
    questions,
    route,
)

PROJECT = "PRJ-RULES"

#: What kicad-cli 10.0.6 wrote for the buck regulator's sheet, trimmed to one
#: violation of each rule (two of the commonest): one error, four warnings.
CAPTURED = (Path(__file__).parent / "data" / "erc-kicad-10.0.6.json").read_text()


def warnings_only() -> str:
    """The same report with its one error taken out."""
    report = json.loads(CAPTURED)
    for sheet in report["sheets"]:
        sheet["violations"] = [v for v in sheet["violations"] if v["severity"] != "error"]
    return json.dumps(report)


EXCLUDED = {
    "endpoint_off_grid": "fang draws its sheet on its own grid",
    "lib_symbol_issues": "fang draws its own symbols",
}


class Jack(Part):
    designator_prefix = "J"
    line = AnalogOut()
    TIP = Pin("TIP", role="analog", number="1")
    SLEEVE = Pin("SLEEVE", role="ground", number="2")
    pinmap = PinMap({"line.signal": "TIP", "line.ref": "SLEEVE"})


class Filter(System):
    sheet_spec = Requires("The schematic passes the electrical rules check")

    inlet = Jack()
    r = Resistor(resistance=10 * kOhm)
    c = Capacitor(capacitance=10 * nF)

    sheet_rules = Checks("sheet_spec", tool="kicad-erc", excluded=EXCLUDED)

    def architecture(self):
        self.inlet.line.signal >> self.r.p1
        self.r.p2 >> self.c.p1
        self.c.p2 >> self.inlet.line.ref


def build(system=Filter):
    result = elaborate(system, project_id=PROJECT)
    assert result.ok, [d.message for d in result.diagnostics]
    return result


class Canned(KicadErcTool):
    """kicad-cli as a run reaches it, answering with a captured report."""

    def __init__(self, report: str = CAPTURED, installed: bool = True) -> None:
        super().__init__()
        self.report = report
        self.installed = installed

    def available(self) -> bool:
        return self.installed

    def version(self) -> str:
        return "kicad-cli 10.0.6"

    def run(self, job, *, workspace) -> RawRun:
        return RawRun(self.name, self.version(), 0, outputs={REPORT: self.report})


def answered(tmp_path, tool):
    result = build()
    graph = KernelGraph(result.snapshot, checks=DEFAULT_CHECKS)
    outcome = answer(
        graph, questions(graph.head)[0], traits=result.traits, tools=ToolRegistry((tool,)),
        workspace=tmp_path, record_time=FIXED_TIME,
    )
    return graph, outcome


# -- the declaration -----------------------------------------------------------


def test_a_rule_check_cannot_state_its_own_answer():
    with pytest.raises(FangError) as raised:
        Checks("sheet_spec", excluded=EXCLUDED, result="PASS")
    assert raised.value.diagnostic.code == diagnostics.SIM_QUESTION_RESULT


def test_an_exclusion_without_a_reason_is_refused():
    with pytest.raises(FangError) as raised:
        Checks("sheet_spec", excluded={"endpoint_off_grid": "  "})
    assert raised.value.diagnostic.code == diagnostics.SIM_EXCLUSION_WITHOUT_REASON
    assert "'endpoint_off_grid'" in raised.value.diagnostic.message
    with pytest.raises(FangError) as raised:
        Checks("sheet_spec", excluded={"endpoint_off_grid", "lib_symbol_issues"})
    assert raised.value.diagnostic.code == diagnostics.SIM_EXCLUSION_WITHOUT_REASON


def test_a_rule_check_elaborates_with_its_exclusions_and_routes_to_the_checker():
    snapshot = build().snapshot
    (question,) = questions(snapshot)
    assert question.method == "rule check"
    check = question.data["check"]
    assert check["artifact"] == "schematic"
    assert sorted(check["excluded"], key=lambda entry: entry["rule"]) == [
        {"rule": "endpoint_off_grid", "reason": "fang draws its sheet on its own grid"},
        {"rule": "lib_symbol_issues", "reason": "fang draws its own symbols"},
    ]
    routed = route(snapshot, question)
    assert (routed.level, routed.tool) == (Level.EXTERNAL, "kicad-erc")


# -- the report ----------------------------------------------------------------


def test_the_report_kicad_cli_writes_is_read_into_violations():
    violations = parse_erc(CAPTURED)
    assert [(v.rule, v.severity) for v in violations] == [
        ("pin_not_connected", "error"),
        ("endpoint_off_grid", "warning"),
        ("endpoint_off_grid", "warning"),
        ("lib_symbol_issues", "warning"),
        ("unconnected_wire_endpoint", "warning"),
    ]
    assert violations[0].items == ("Symbol U1 Pin 6 [EN, Passive, Line]",)
    with pytest.raises(ValueError, match="not JSON"):
        parse_erc("Found 3 violations")


def edited(change) -> str:
    """The captured report with one change made to it."""
    report = json.loads(CAPTURED)
    change(report)
    return json.dumps(report)


def test_a_report_the_reader_is_not_written_for_is_refused_not_read_as_empty():
    """Read leniently, a report of a changed schema, or one with no sheets,
    was a report of no violations, and passed."""
    refused = {
        "schema is 'https://schemas.kicad.org/erc.v2.json'": edited(
            lambda r: r.update({"$schema": "https://schemas.kicad.org/erc.v2.json"})
        ),
        "schema is None": edited(lambda r: r.pop("$schema")),
        "no list of sheets": edited(lambda r: r.pop("sheets")),
        "no list of violations": edited(lambda r: r["sheets"][0].pop("violations")),
        "gives no severity": edited(lambda r: r["sheets"][0]["violations"][0].pop("severity")),
        "of severity 'critical'": edited(
            lambda r: r["sheets"][0]["violations"][0].update({"severity": "critical"})
        ),
        "does not list the items": edited(lambda r: r["sheets"][0]["violations"][0].pop("items")),
        "not a JSON object": "[]",
    }
    for reason, text in refused.items():
        with pytest.raises(ValueError, match=re.escape(reason)):
            parse_erc(text)
    assert parse_erc(edited(lambda r: r["sheets"][0].update({"violations": []}))) == ()


def fake_kicad_cli(tmp_path, report: str) -> str:
    """An executable that answers as kicad-cli does, writing the report given."""
    import stat
    import sys

    script = tmp_path / "kicad-cli"
    (tmp_path / "report.json").write_text(report)
    script.write_text(
        f"#!{sys.executable}\n"
        "import shutil, sys\n"
        "if sys.argv[1] == 'version':\n"
        "    print('10.0.6')\n"
        "else:\n"
        "    out = sys.argv[sys.argv.index('-o') + 1]\n"
        f"    shutil.copyfile({str(tmp_path / 'report.json')!r}, out)\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="the stand-in kicad-cli is a script started by its shebang, which Windows does not run",
)
def test_an_unread_report_fails_the_run_and_leaves_the_result_unknown(tmp_path):
    """A report with no sheets is a run that did not complete, with the
    reason; no verdict is drawn from it."""
    hollow = json.dumps({"$schema": "https://schemas.kicad.org/erc.v1.json"})
    tool = KicadErcTool(executable=fake_kicad_cli(tmp_path, hollow))
    graph, outcome = answered(tmp_path / "runs", tool)
    assert outcome.status == ANSWERED and outcome.result == "UNKNOWN"
    record = graph.head.entities[outcome.evidence].extensions["measurement"]
    assert record["status"] == "failed"
    assert "wrote a report fang does not read: the ERC report holds no list of sheets" in record["message"]
    assert "errors" not in record
    assert "did not complete" in outcome.verdict.summary[0]

    # The captured report through the same executable is read as it was.
    tool = KicadErcTool(executable=fake_kicad_cli(tmp_path, CAPTURED))
    graph, outcome = answered(tmp_path / "again", tool)
    assert outcome.result == "FAIL"

    # A recorded run's report is judged by the same reader.
    graph, outcome = answered(tmp_path / "canned", Canned(edited(lambda r: r.pop("$schema"))))
    assert outcome.result == "UNKNOWN"
    assert "the reader is written for" in outcome.verdict.summary[0]


def test_errors_fail_and_warnings_do_not():
    failing = judge(parse_erc(CAPTURED), [])
    assert failing.result == "FAIL"
    assert (failing.record["errors"], failing.record["warnings"]) == (1, 4)
    passing = judge(parse_erc(warnings_only()), [])
    assert passing.result == "PASS"
    assert passing.record["warnings"] == 4


def test_an_excluded_rule_neither_fails_nor_counts_and_is_recorded_with_its_reason():
    excluded = [{"rule": "pin_not_connected", "reason": "EN is tied on the module"}]
    verdict = judge(parse_erc(CAPTURED), excluded)
    assert verdict.result == "PASS"
    assert verdict.record["errors"] == 0
    assert verdict.record["excluded"] == [
        {"rule": "pin_not_connected", "reason": "EN is tied on the module", "count": 1}
    ]
    flagged = [v for v in verdict.record["violations"] if v.get("excluded")]
    assert [v["rule"] for v in flagged] == ["pin_not_connected"]


# -- through the gate ------------------------------------------------------------


def test_a_violation_is_recorded_with_its_rule_severity_and_items(tmp_path):
    graph, outcome = answered(tmp_path, Canned())
    assert outcome.status == ANSWERED and outcome.result == "FAIL"
    record = graph.head.entities[outcome.evidence].extensions["measurement"]
    assert record["tool"] == {"name": "kicad-erc", "version": "kicad-cli 10.0.6"}
    assert record["level"] == "external"
    assert {
        "rule": "pin_not_connected",
        "severity": "error",
        "description": "Pin not connected",
        "items": ["Symbol U1 Pin 6 [EN, Passive, Line]"],
    } in record["violations"]
    assert {"rule": "endpoint_off_grid", "reason": "fang draws its sheet on its own grid",
            "count": 2} in record["excluded"]
    verification = graph.head.entities[outcome.question.id]
    assert (verification.result, verification.level, verification.tool) == (
        "FAIL", "external", "kicad-erc",
    )


def test_a_sheet_with_only_warnings_passes_and_its_warnings_are_recorded(tmp_path):
    graph, outcome = answered(tmp_path, Canned(warnings_only()))
    assert outcome.result == "PASS"
    record = graph.head.entities[outcome.evidence].extensions["measurement"]
    assert record["warnings"] == 1
    assert any(v["rule"] == "unconnected_wire_endpoint" for v in record["violations"])


def test_an_absent_kicad_cli_reports_unsupported_by_name(tmp_path):
    graph, outcome = answered(tmp_path, KicadErcTool(executable="not-kicad-cli"))
    assert outcome.status == UNSUPPORTED
    assert "kicad-erc is not installed" in outcome.message
    assert len(graph.history) == 1


def test_a_check_that_wrote_no_report_leaves_the_result_unknown(tmp_path):
    class Broken(Canned):
        def run(self, job, *, workspace):
            return RawRun(self.name, self.version(), 1, status=Status.FAILED,
                          message="kicad-cli wrote no report")

    graph, outcome = answered(tmp_path, Broken())
    assert outcome.result == "UNKNOWN"
    assert "did not complete" in outcome.verdict.summary[0]


def test_preparation_draws_the_sheet_and_names_its_snapshot_beside_it():
    result = build()
    question = questions(result.snapshot)[0]
    first = KICAD_ERC.prepare(result.snapshot, question, traits=result.traits)
    again = KICAD_ERC.prepare(result.snapshot, question, traits=result.traits)
    assert first.input == again.input and first.hash == again.hash
    assert result.snapshot.hash not in first.input
    assert first.input.startswith("(kicad_sch")
    assert "endpoint_off_grid is excluded: fang draws its sheet on its own grid" in first.assumptions


@pytest.mark.skipif(not KICAD_ERC.available(), reason="kicad-cli is not installed here")
def test_the_installed_kicad_cli_checks_the_sheet_fang_draws(tmp_path):
    graph, outcome = answered(tmp_path, KICAD_ERC)
    record = graph.head.entities[outcome.evidence].extensions["measurement"]
    assert outcome.status == ANSWERED
    assert record["tool"]["version"].startswith("kicad-cli")
    # Both rules a fang sheet trips on every symbol fired, and were set aside.
    counts = {entry["rule"]: entry["count"] for entry in record["excluded"]}
    assert counts["endpoint_off_grid"] > 0 and counts["lib_symbol_issues"] > 0
