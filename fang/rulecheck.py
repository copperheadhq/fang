"""Rule checks: an external checker's report, recorded as evidence.

Spec: "Rule Checks Are Evidence" and "Verification Tools Sit Behind One
Protocol".

A rule-check question runs KiCad's electrical rules check over the schematic
the kernel draws, across a process boundary, on a scratch copy. Every
violation the checker reports is recorded with its rule, its severity and the
items it names; a rule the question excludes is recorded with its reason and
how many violations it set aside. A violation of error severity fails the
verification, and a warning does not.

The report is read as `kicad-cli sch erc --format json` writes it in KiCad
10.0.6, schema `erc.v1`, and a report of any other schema, or one missing a
field the reader reads, fails the run with the reason: read as empty, it
would pass. On a sheet fang draws, two rules fire on every symbol
-- `endpoint_off_grid`, because fang draws on its own grid, and
`lib_symbol_issues`, because its symbols are its own -- which is why a question
names exclusions, each with a reason, rather than the tool hiding anything.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .runtime import Status
from .simulation import Level
from .verification import Job, Question, RawRun, ToolUnavailable, Verdict

#: The sheet a job carries, and the report a run writes beside it.
SHEET = "board.kicad_sch"
REPORT = "erc.json"

#: The report schema the reader is written for, as kicad-cli 10.0.6 names it,
#: and the severities a report of it gives a violation.
SCHEMA = "https://schemas.kicad.org/erc.v1.json"
SEVERITIES = ("error", "warning", "exclusion")


@dataclass(frozen=True)
class Violation:
    """One violation as the checker reports it: a rule, a severity, the items."""

    rule: str
    severity: str             # error, warning, or exclusion (excluded in KiCad)
    description: str
    items: tuple[str, ...] = ()

    def as_record(self, *, excluded: bool = False) -> dict:
        out = {
            "rule": self.rule,
            "severity": self.severity,
            "description": self.description,
            "items": list(self.items),
        }
        if excluded:
            out["excluded"] = True
        return out


def parse_erc(text: str) -> tuple[Violation, ...]:
    """Read kicad-cli's JSON report into violations, and nothing else.

    The report must be of the schema the reader is written for and hold
    every field it reads, each of the kind it reads: a report of another
    schema, or one without its sheets, is refused with the reason rather
    than read as a report of no violations, which would pass.
    """
    try:
        report = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"the ERC report is not JSON: {exc}") from None
    if not isinstance(report, dict):
        raise ValueError("the ERC report is not a JSON object")
    schema = report.get("$schema")
    if schema != SCHEMA:
        raise ValueError(
            f"the ERC report's schema is {schema!r}, and the reader is written for {SCHEMA}"
        )
    sheets = report.get("sheets")
    if not isinstance(sheets, list):
        raise ValueError("the ERC report holds no list of sheets")
    found: list[Violation] = []
    for sheet in sheets:
        violations = sheet.get("violations") if isinstance(sheet, dict) else None
        if not isinstance(violations, list):
            raise ValueError("a sheet of the ERC report holds no list of violations")
        for violation in violations:
            if not isinstance(violation, dict):
                raise ValueError("a violation in the ERC report is not a JSON object")
            for key in ("type", "severity", "description"):
                if not isinstance(violation.get(key), str):
                    raise ValueError(f"a violation in the ERC report gives no {key}")
            if violation["severity"] not in SEVERITIES:
                raise ValueError(
                    f"a {violation['type']} violation in the ERC report is of severity "
                    f"{violation['severity']!r}, which is none of {', '.join(SEVERITIES)}"
                )
            items = violation.get("items")
            if not isinstance(items, list) or not all(
                isinstance(item, dict) and isinstance(item.get("description"), str)
                for item in items
            ):
                raise ValueError(
                    f"a {violation['type']} violation in the ERC report does not list "
                    "the items it names"
                )
            found.append(
                Violation(
                    violation["type"],
                    violation["severity"],
                    violation["description"],
                    tuple(item["description"] for item in items),
                )
            )
    return tuple(found)


def judge(violations: Sequence[Violation], excluded: Sequence[Mapping[str, str]]) -> Verdict:
    """The verdict on a report, under a question's declared exclusions.

    Errors fail and warnings do not; an excluded rule does neither, and is
    recorded with its reason and its count. A violation KiCad itself reports
    as excluded counts toward nothing either, and is recorded as reported.
    """
    reasons = {entry["rule"]: entry["reason"] for entry in excluded}
    counted = [v for v in violations if v.rule not in reasons and v.severity != "exclusion"]
    errors = [v for v in counted if v.severity == "error"]
    warnings = [v for v in counted if v.severity == "warning"]

    record = {
        "violations": [v.as_record(excluded=v.rule in reasons) for v in violations],
        "excluded": [
            {
                "rule": rule,
                "reason": reason,
                "count": sum(1 for v in violations if v.rule == rule),
            }
            for rule, reason in sorted(reasons.items())
        ],
        "errors": len(errors),
        "warnings": len(warnings),
    }

    def tally(found: Sequence[Violation]) -> str:
        rules: dict[str, int] = {}
        for violation in found:
            rules[violation.rule] = rules.get(violation.rule, 0) + 1
        return ", ".join(f"{rule} {count}" for rule, count in sorted(rules.items()))

    summary = [f"{len(errors)} error(s), {len(warnings)} warning(s)"]
    summary += [
        f"error {v.rule}: {'; '.join(v.items) or v.description}"
        for v in sorted(errors, key=lambda v: (v.rule, v.items))
    ]
    if warnings:
        summary.append(f"warnings: {tally(warnings)}")
    summary += [
        f"excluded {entry['rule']} {entry['count']}: {entry['reason']}"
        for entry in record["excluded"]
    ]
    return Verdict("FAIL" if errors else "PASS", record, tuple(summary))


@dataclass
class KicadErcTool:
    """KiCad's electrical rules check, over the schematic fang draws.

    Preparation compiles the sheet from the snapshot; the run writes it into a
    workspace of its own and runs `kicad-cli` there, so the checker never sees
    the project; reading turns the JSON report into a verdict. Where kicad-cli
    is not installed the question is unsupported, by name.
    """

    name: str = "kicad-erc"
    level: Level = Level.EXTERNAL
    executable: str = "kicad-cli"

    def covers(self, question: Question) -> bool:
        check = question.data.get("check", {})
        return question.method == "rule check" and check.get("artifact") == "schematic"

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def version(self) -> str:
        if not self.available():
            raise ToolUnavailable(f"{self.executable} is not installed")
        completed = subprocess.run(
            [self.executable, "version"], capture_output=True, text=True, timeout=60
        )
        printed = (completed.stdout or completed.stderr).strip().splitlines()
        return f"kicad-cli {printed[0]}" if printed else "kicad-cli"

    def prepare(self, snapshot, question: Question, *, traits=None) -> Job:
        from .schematic import compile_schematic

        sheet = compile_schematic(snapshot, traits=traits, title="fang")
        # The sheet names the snapshot it came from, and that hash covers the
        # checkout's path; the job names its snapshot beside itself instead, so
        # the job is the same wherever the program was read from.
        sheet = sheet.replace(f'"snapshot {snapshot.hash}"', '"snapshot named by the job"')
        excluded = sorted(
            question.data.get("check", {}).get("excluded", ()), key=lambda entry: entry["rule"]
        )
        assumptions = [
            "the sheet is the one fang draws: its own symbols on its own grid, "
            "every connection a global label on a pin"
        ]
        assumptions += [f"{entry['rule']} is excluded: {entry['reason']}" for entry in excluded]
        return Job.single(
            self.name,
            question,
            snapshot.hash,
            SHEET,
            sheet,
            assumptions=tuple(assumptions),
            coverage_gaps=(
                "an electrical rules check reads the drawn sheet, not a board: "
                "nothing about layout, routing or copper is checked",
            ),
        )

    def run(self, job: Job, *, workspace: Path) -> RawRun:
        if not self.available():
            raise ToolUnavailable(
                f"{self.executable} is not installed; the rule check is unsupported "
                "and nothing else answers it"
            )
        # Absolute, because kicad-cli is run from inside it and named it too.
        workspace = Path(workspace).resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        (workspace / SHEET).write_text(job.input, encoding="utf-8")
        report = workspace / REPORT
        completed = subprocess.run(
            [
                self.executable, "sch", "erc", "--format", "json", "--severity-all",
                "-o", str(report), str(workspace / SHEET),
            ],
            capture_output=True,
            text=True,
            cwd=workspace,
            timeout=120,
        )
        written = report.is_file()
        text = report.read_text(encoding="utf-8") if written else ""
        succeeded = completed.returncode == 0 and written
        message = "" if succeeded else (
            f"{self.executable} wrote no report: "
            f"{(completed.stderr or completed.stdout).strip()}"
        )
        if succeeded:
            # A report the reader is not written for is a run that did not
            # complete, with the reason, and never an empty report that passes.
            try:
                parse_erc(text)
            except ValueError as exc:
                succeeded = False
                message = f"{self.executable} wrote a report fang does not read: {exc}"
        return RawRun(
            self.name,
            self.version(),
            completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            outputs={REPORT: text} if written else {},
            status=Status.SUCCEEDED if succeeded else Status.FAILED,
            message=message,
        )

    def read(self, job: Job, raw: RawRun) -> tuple:
        """A rule check measures into no parameter; its answer is the verdict."""
        return ()

    def verdict(self, job: Job, raw: RawRun) -> Verdict:
        if raw.status is not Status.SUCCEEDED or REPORT not in raw.outputs:
            return Verdict(
                "UNKNOWN", {}, (f"the check did not complete: {raw.message or raw.status.value}",)
            )
        try:
            violations = parse_erc(raw.outputs[REPORT])
        except ValueError as exc:
            return Verdict("UNKNOWN", {}, (str(exc),))
        return judge(violations, job.question.data.get("check", {}).get("excluded", ()))


#: KiCad's electrical rules check, a built-in tool at the external level.
KICAD_ERC = KicadErcTool()
