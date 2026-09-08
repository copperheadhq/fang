"""Regenerate the outputs every example folder ships.

Spec: "The Command Surface" and "The Netlist Is A Projection".

Each example is a folder: the program, a document explaining it, and the files
`fang` produces from it under `out/`. The outputs are committed so the folder
can be read without running anything, and `tests/test_examples.py` rebuilds
them and compares, so a committed output cannot drift from the program beside
it.

    python examples/regenerate.py           # rewrite every example's out/
    python examples/regenerate.py divider   # just one

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

ROOT = Path(__file__).resolve().parent

if __name__ == "__main__" and str(ROOT.parent) not in sys.path:
    sys.path.insert(0, str(ROOT.parent))

from fang.cli import cmd_check, cmd_export, cmd_graph, cmd_netlist, load_system
from fang.elaborate import elaborate
from fang.layout import PlacementSeeds, place
from fang.render import to_svg
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
    "usb_uart_bridge": ("interfaces", "power"),
    "buck_regulator": ("power", "system"),
    "servo_drive": ("system", "power", "safety"),
}

#: The entity kinds that carry reasoning rather than circuit. An example with
#: none of them gets no rationale document, because it would have nothing in it.
RATIONALE_KINDS = ("requirement", "decision", "evidence", "calculation", "verification")


def examples() -> list[str]:
    """Every example folder, in the order the documents list them."""
    return sorted(
        path.name for path in ROOT.iterdir() if (path / f"{path.name}.py").is_file()
    )


def _program(name: str) -> Path:
    return ROOT / name / f"{name}.py"


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
# The output set
# --------------------------------------------------------------------------


def render(name: str) -> dict[str, str]:
    """Every output file for one example, as relative path to text."""
    result = elaborate(load_system(_program(name)), project_id=PROJECT)
    files = {
        f"{name}.net": _run(cmd_export, name),
        "netlist.txt": _run(cmd_netlist, name),
        "checks.txt": _run(cmd_check, name),
        "graph.txt": _run(cmd_graph, name),
    }
    for view_name in VIEWS.get(name, ()):
        graph = view(result.snapshot, view_name)
        files[f"views/{view_name}.svg"] = to_svg(place(graph, seeds=PlacementSeeds()))
    rationale = _rationale(name, result.snapshot)
    if rationale is not None:
        files["rationale.md"] = rationale
    return files


def write(name: str) -> list[Path]:
    """Write one example's outputs, replacing whatever is there."""
    out = ROOT / name / "out"
    written = []
    for relative, text in sorted(render(name).items()):
        path = out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
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
