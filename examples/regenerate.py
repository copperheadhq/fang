"""Regenerate the outputs every example folder ships.

Spec: "The Command Surface" and "The Netlist Is A Projection".

Each example is a folder: the program, a document explaining it, and the files
`fang` produces from it under `out/`. The outputs are committed so the folder
can be read without running anything, and `tests/test_examples.py` rebuilds
them and compares, so a committed output cannot drift from the program beside
it.

    python examples/regenerate.py           # rewrite every example's out/
    python examples/regenerate.py divider   # just one

An example that declares a verification question also ships
`verification.txt`, what `fang verify` finds; writing it runs the tool the
question routes to, so regenerating that example needs the tool -- ngspice --
on the path, and the suite compares the file only where the tool is installed.

Everything here is written by calling the same functions the CLI calls, on a
program elaborated in the ``PRJ-EXAMPLES`` project. The project namespace is
part of every derived identifier, so the identifiers in these files are the
ones this namespace gives and not the ones a local `fang build` would.
"""

from __future__ import annotations

import contextlib
import io
import re
import sys
from argparse import Namespace
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent

if __name__ == "__main__" and str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from fang.checks import DEFAULT_CHECKS
from fang.cli import cmd_check, cmd_export, cmd_graph, cmd_netlist, load_system
from fang.copperhead import CopperheadDrafter, compile_intent
from fang.elaborate import EPOCH, elaborate
from fang.graph import KernelGraph
from fang.layout import PlacementSeeds, place
from fang.render import to_svg
from fang.schematic import KicadRenderer, compile_schematic
from fang.verification import questions, report, route, verify
from fang.views import view

PROJECT = "PRJ-EXAMPLES"

#: The views each example is worth looking at, and only those: a view answers
#: one question, and shipping all six of them for every board would bury the
#: one that the example was written to show.
VIEWS: dict[str, tuple[str, ...]] = {
    "divider": ("interconnect",),
    "blinky": ("interconnect", "power"),
    "equations": ("interconnect",),
    "sensor_board": ("interfaces", "ground"),
    "i2c_bus": ("interfaces", "interconnect"),
    "sensor_node": ("interfaces", "power"),
    "usb_uart_bridge": ("interfaces", "power"),
    "buck_regulator": ("power", "system"),
    "servo_drive": ("system", "power", "safety"),
    "jee_advanced/problem_1": ("interconnect",),
    "jee_advanced/problem_2": ("interconnect",),
    "noninverting_amp": ("interconnect",),
    "rc_filter": ("interconnect",),
}

#: The examples that ship a schematic. A schematic is the picture an engineer
#: recognizes, and it is KiCad that draws it, so regenerating one of these needs
#: `kicad-cli` on the path.
SCHEMATICS: frozenset[str] = frozenset(
    {"jee_advanced/problem_1", "jee_advanced/problem_2", "noninverting_amp"}
)

#: The examples that also ship copperhead's draft of the same circuit, placed
#: and wired rather than laid on a grid, under out/copperhead/. copperhead draws
#: it and KiCad renders it, so regenerating one of these needs `copperhead` on
#: the path as well as `kicad-cli`. Only the ones copperhead draws legibly: on
#: the two resistor meshes its labels still land on symbol bodies.
DRAFTED: frozenset[str] = frozenset({"noninverting_amp"})

#: The examples whose firmware runs in Renode. For each emulation question the
#: plan, the platform description and the script are written under
#: out/renode/<question>/, here and on every machine: lowering a plan needs no
#: emulator, so these are compared like any other output.
EMULATED: frozenset[str] = frozenset({"sensor_node"})

#: The entity kinds that carry reasoning rather than circuit. An example with
#: none of them gets no rationale document, because it would have nothing in it.
RATIONALE_KINDS = ("requirement", "decision", "evidence", "calculation", "verification")


#: Folders a search never descends into: an example's own outputs, and Python's
#: leavings. Everything else under examples/ is either an example or a folder
#: that groups them.
_SKIP = frozenset({"out", "views", "__pycache__"})


def _find(folder: Path) -> list[str]:
    """Every example at or below a folder, as a path relative to examples/.

    An example is a folder holding a program named after it. A folder that has
    no such program may still *group* examples — `jee_advanced/` holds one
    problem per subfolder — so the search descends rather than stopping, and an
    example's name is its path, which is what keeps two of them distinct.
    """
    if (folder / f"{folder.name}.py").is_file():
        return [folder.relative_to(ROOT).as_posix()]
    found = []
    for child in folder.iterdir():
        if child.is_dir() and child.name not in _SKIP and not child.name.startswith("."):
            found.extend(_find(child))
    return found


def examples() -> list[str]:
    """Every example folder, in the order the documents list them."""
    return sorted(name for child in ROOT.iterdir() if child.is_dir()
                  and child.name not in _SKIP and not child.name.startswith(".")
                  for name in _find(child))


def _program(name: str) -> Path:
    """The program of an example named by its path relative to examples/."""
    return ROOT / name / f"{Path(name).name}.py"


def _run(command, name: str, **extra) -> str:
    """Run a CLI command and capture what it prints, output and errors both.

    A check that is undecided prints to output and a check that failed prints
    to errors; a reader of the file wants them in the order they happened, so
    both are captured into one buffer.
    """
    buffer = io.StringIO()
    args = Namespace(
        program=str(_program(name)),
        system=None,
        project=PROJECT,
        directory=str(ROOT / name),
        output=None,
        **extra,
    )
    with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
        command(args)
    return buffer.getvalue()


# --------------------------------------------------------------------------
# The rationale document
# --------------------------------------------------------------------------


def _label(entity) -> str:
    """What to call an entity: the name it has in the program.

    The semantic path is the one name that is unique and that a reader can find
    in the source. A display name is not — two devices on a bus can both call
    their datasheet claim `thresholds`.
    """
    return str(entity.identity.path) or entity.identity.display_name


#: An identifier as it appears inside a sentence the kernel wrote.
IDENTIFIER = re.compile(r"\b[A-Z]{2,8}-[0-9a-f]{12,}\b")


def _resolve(snapshot, text: str) -> str:
    """Put names back into a sentence that carries identifiers.

    A lowering decision reads "which pin of CMP-91431a8f1d4e carries i2c.scl?".
    The identifier is the precise thing and stays in the graph; a reader needs
    the name it was derived from.
    """
    def name(match) -> str:
        entity = snapshot.entities.get(match.group(0))
        return f"`{_label(entity)}`" if entity else match.group(0)

    return IDENTIFIER.sub(name, text)


def _named(snapshot, identifier: str) -> str:
    """An identifier with the name it was derived from, when the graph has it.

    A component's display name is its class, which is worth saying beside the
    path because the path does not carry it.
    """
    entity = snapshot.entities.get(identifier)
    if entity is None:
        return f"`{identifier}`"
    label, name = _label(entity), entity.identity.display_name
    kind = f" — {name}" if name and label.rsplit(".", 1)[-1] != name else ""
    return f"`{label}`{kind} (`{identifier}`)"


def _rationale(name: str, snapshot) -> str | None:
    """Render the reasoning entities of a snapshot as markdown.

    This is a projection like any other: nothing is written here that is not an
    entity in the graph, and the order is by identifier, so the document is the
    same on every machine.
    """
    kinds: dict[str, list] = {kind: [] for kind in RATIONALE_KINDS}
    for entity in sorted(snapshot.entities.values(), key=lambda e: e.id):
        if entity.kind in kinds:
            kinds[entity.kind].append(entity)
    if not any(kinds.values()):
        return None

    out = [
        f"# {name} — rationale",
        "",
        "Every line below is an entity in the elaborated graph, projected by",
        "`python examples/regenerate.py`. Nothing here is prose kept beside the",
        "design; it is the design.",
        "",
    ]

    if kinds["requirement"]:
        out.append("## Requirements")
        out.append("")
        for req in kinds["requirement"]:
            verifications = [
                v for v in kinds["verification"] if v.verifies == req.id
            ]
            out.append(f"### {_label(req)} — `{req.id}`")
            out.append("")
            out.append(f"> {_resolve(snapshot, req.statement)}")
            out.append("")
            method = req.validation_method or "unstated"
            out.append(
                f"{req.priority}, state {req.state.value}, validation by {method}."
            )
            out.append("")
            for verification in verifications:
                out.append(
                    f"- Verified by `{_label(verification)}` "
                    f"(`{verification.id}`): **{verification.result}** "
                    f"by {verification.method}"
                )
                for evidence in sorted(verification.evidence):
                    out.append(f"  - on {_named(snapshot, evidence)}")
            if not verifications:
                out.append("- No verification closes this requirement yet.")
            out.append("")

    if kinds["decision"]:
        out.append("## Decisions")
        out.append("")
        for decision in kinds["decision"]:
            out.append(f"### {_label(decision)} — `{decision.id}`")
            out.append("")
            choice = decision.choice or ""
            out.append(
                f"**{_resolve(snapshot, decision.question)}** → "
                f"{_named(snapshot, choice) if choice in snapshot.entities else choice or 'undecided'}"
            )
            out.append("")
            for reason in decision.rationale:
                out.append(f"- {_resolve(snapshot, reason)}")
            for rejected in decision.alternatives_rejected:
                option = rejected.get("part") or rejected.get("option") or "alternative"
                out.append(
                    f"- Rejected {option}: {_resolve(snapshot, rejected.get('reason', ''))}"
                )
            for requirement in sorted(decision.requirements):
                out.append(f"- Serves {_named(snapshot, requirement)}")
            out.append("")

    if kinds["calculation"]:
        out.append("## Calculations")
        out.append("")
        for calculation in kinds["calculation"]:
            out.append(f"### {_label(calculation)} — `{calculation.id}`")
            out.append("")
            out.append(f"`{calculation.expression}`")
            out.append("")
            out.append(f"Result: {_resolve(snapshot, calculation.result)}")
            out.append("")
            for reference in sorted(calculation.inputs):
                out.append(f"- Over {_named(snapshot, reference)}")
            out.append("")

    if kinds["evidence"]:
        out.append("## Evidence")
        out.append("")
        for evidence in kinds["evidence"]:
            out.append(f"### {_label(evidence)} — `{evidence.id}`")
            out.append("")
            out.append(f"> {_resolve(snapshot, evidence.claim)}")
            out.append("")
            where = ", ".join(part for part in (evidence.document, evidence.locator) if part)
            out.append(f"Cited from {where}." if where else "Cited from an unnamed source.")
            out.append("")

    return "\n".join(out).rstrip() + "\n"


# --------------------------------------------------------------------------
# The verification listing
# --------------------------------------------------------------------------


def verification_tools(result) -> set[str]:
    """The tools an example's questions route to, so a reader of the suite
    can say which binary an example's verification.txt needs."""
    return {
        routed.tool
        for question in questions(result.snapshot)
        for routed in (route(result.snapshot, question),)
        if routed.routed and not routed.decided
    }


def _verification(result) -> str | None:
    """What `fang verify` finds, run twice: on the elaborated program, and on
    the head the first run's measurements were committed to.

    Numbers are at three significant figures and no tool version appears, so
    a simulator release that moves a number in its fourth figure moves nothing
    here; the evidence keeps every figure and the version. An example with no
    question gets no listing.
    """
    if not questions(result.snapshot):
        return None
    graph = KernelGraph(result.snapshot, checks=DEFAULT_CHECKS)
    with TemporaryDirectory() as scratch:
        first = verify(graph, traits=result.traits, workspace=Path(scratch), record_time=EPOCH)
        out = ["On the elaborated program:", ""] + report(first, versions=False)
        if graph.head.hash != result.snapshot.hash:
            again = verify(graph, traits=result.traits, workspace=Path(scratch), record_time=EPOCH)
            out += ["", "Again, on the head that run committed:", ""]
            out += report(again, versions=False)
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# The output set
# --------------------------------------------------------------------------


def _emulation_bundles(result) -> dict[str, str]:
    """Each emulation question's plan, platform description and script."""
    from fang.emulation import RENODE
    from fang.verification import questions

    files = {}
    for question in questions(result.snapshot):
        if question.method != "emulation":
            continue
        job = RENODE.prepare(result.snapshot, question, traits=result.traits)
        folder = f"renode/{question.label.rsplit('.', 1)[-1]}"
        for file in ("plan.json", "platform.repl", "run.resc"):
            content = job.files[file]
            files[f"{folder}/{file}"] = content.decode("utf-8") if isinstance(content, bytes) else content
    return files


def render(name: str) -> dict[str, str]:
    """Every output file for one example, as relative path to text.

    The name is a path relative to examples/, so a grouped example is
    `jee_advanced/problem_1`. Files inside its own out/ are named after the
    leaf, because that is the name the program has.
    """
    stem = Path(name).name
    result = elaborate(load_system(_program(name)), project_id=PROJECT)
    files = {
        f"{stem}.net": _run(cmd_export, name),
        "netlist.txt": _run(cmd_netlist, name),
        "checks.txt": _run(cmd_check, name),
        "graph.txt": _run(cmd_graph, name),
    }
    for view_name in VIEWS.get(name, ()):
        graph = view(result.snapshot, view_name)
        files[f"views/{view_name}.svg"] = to_svg(place(graph, seeds=PlacementSeeds()))
    if name in SCHEMATICS:
        schematic = compile_schematic(
            result.snapshot, traits=result.traits, title=stem
        )
        files[f"{stem}.kicad_sch"] = schematic
        with TemporaryDirectory() as scratch:
            files["schematic.svg"] = KicadRenderer().to_svg(
                schematic, workspace=Path(scratch), name=stem
            )
    if name in DRAFTED:
        intent = compile_intent(result.snapshot, traits=result.traits, group=stem)
        files["copperhead/schematic.intent.json"] = intent.text()
        with TemporaryDirectory() as scratch:
            drafted = CopperheadDrafter().draft(
                intent, workspace=Path(scratch) / "draft", name=stem
            )
            files[f"copperhead/{stem}.kicad_sch"] = drafted
            files["copperhead/schematic.svg"] = KicadRenderer().to_svg(
                drafted, workspace=Path(scratch) / "render", name=stem
            )
    if name in EMULATED:
        files.update(_emulation_bundles(result))
    rationale = _rationale(stem, result.snapshot)
    if rationale is not None:
        files["rationale.md"] = rationale
    verification = _verification(result)
    if verification is not None:
        files["verification.txt"] = verification
    return files


def _missing_tools(name: str) -> list[str]:
    """The tools an example's questions route to that are not installed."""
    from fang.verification import TOOLS

    result = elaborate(load_system(_program(name)), project_id=PROJECT)
    return sorted(
        tool for tool in verification_tools(result) if not TOOLS.get(tool).available()
    )


def write(name: str) -> list[Path]:
    """Write one example's outputs, replacing whatever is there.

    A verification listing is not rewritten where its tool is missing: it
    would record only that the tool is absent, over the answer it gave.
    """
    out = ROOT / name / "out"
    written = []
    missing = _missing_tools(name)
    for relative, text in sorted(render(name).items()):
        if relative == "verification.txt" and missing:
            print(
                f"regenerate: {', '.join(missing)} is not installed; "
                f"{name}/out/{relative} is left as it is",
                file=sys.stderr,
            )
            continue
        path = out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    names = argv or examples()
    for name in names:
        if not _program(name).is_file():
            print(f"regenerate: no example named {name!r}", file=sys.stderr)
            return 2
        for path in write(name):
            print(path.relative_to(ROOT.parent))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
