"""The `fang` command line.

Spec: "The Command Surface". Every command exits non-zero when the work it names
did not succeed, so a build script can rely on the exit code rather than on
parsing output.
"""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import sys
from pathlib import Path
from typing import Iterable, Sequence

from . import __version__
from .checks import DEFAULT_CHECKS
from .constraints import CheckStatus
from .diagnostics import Diagnostic, FangError, Severity
from .elaborate import Elaboration, elaborate
from .graph import AddEntity, KernelGraph, Snapshot, Transaction
from .kicad import emit_netlist
from .lang import System
from .netlist import compile_netlist
from .layout import PlacementSeeds, place
from .render import to_svg
from .runtime import Status, default_registry, execute
from .views import REGISTRY as VIEW_REGISTRY, REQUIRED_VIEWS, view
from .workspace import Workspace, find_workspace

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2


# --------------------------------------------------------------------------
# Loading a program
# --------------------------------------------------------------------------


def load_system(path: Path, name: str | None = None) -> type[System]:
    """Import a Fang program and find the system it defines."""
    if not path.is_file():
        raise SystemExit(f"fang: {path} is not a file")

    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"fang: {path} could not be imported")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    systems = [
        value
        for value in vars(module).values()
        if inspect.isclass(value) and issubclass(value, System) and value is not System
    ]
    if name:
        for candidate in systems:
            if candidate.__name__ == name:
                return candidate
        raise SystemExit(f"fang: {path} defines no system named {name!r}")
    if not systems:
        raise SystemExit(f"fang: {path} defines no System subclass")
    if len(systems) > 1:
        names = ", ".join(sorted(s.__name__ for s in systems))
        raise SystemExit(
            f"fang: {path} defines more than one system ({names}); "
            "name one with --system"
        )
    return systems[0]


def report_diagnostics(diagnostics: Iterable[Diagnostic], stream=None) -> int:
    """Print each diagnostic with its code and source location."""
    stream = stream if stream is not None else sys.stderr
    count = 0
    for diagnostic in diagnostics:
        location = diagnostic.location
        where = f"{location.file}:{location.line}: " if location else ""
        print(
            f"{where}{diagnostic.severity.value}: {diagnostic.code}: {diagnostic.message}",
            file=stream,
        )
        count += 1
    return count


def _elaborate(args) -> Elaboration:
    try:
        system = load_system(Path(args.program), getattr(args, "system", None))
        result = elaborate(system, project_id=args.project)
    except FangError as exc:
        # A program's own error is a diagnostic, not a crash of the tool.
        report_diagnostics([exc.diagnostic])
        raise SystemExit(EXIT_FAILED) from None
    if not result.ok:
        report_diagnostics(result.diagnostics)
        raise SystemExit(EXIT_FAILED)
    return result


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def cmd_init(args) -> int:
    workspace = Workspace(args.directory).create()
    print(f"initialized {workspace.dir}")
    return EXIT_OK


def _with_measurements(snapshot: Snapshot, workspace: Workspace) -> Snapshot:
    """A fresh elaboration, keeping what runs measured into this workspace.

    The program declared each measured parameter without a value, so building
    it again must not withdraw a measurement a run committed.
    """
    if not workspace.manifest_path.exists():
        return snapshot
    from .verification import MeasuredFacts, carry_measurements

    facts = MeasuredFacts.from_records(workspace.read_records())
    if not facts.verifications:
        return snapshot
    # The measurements belong to the revision they were committed in, so the
    # state rebuilt around them keeps that revision: an unchanged program
    # rebuilt this way is the persisted snapshot, byte for byte.
    carried = carry_measurements(snapshot, facts)
    return carried.with_entities(carried.entities, workspace.read_manifest().revision_id)


def _revision_number(revision_id: str) -> int:
    """Where a graph over a persisted head continues numbering revisions."""
    _, _, number = revision_id.partition("-")
    return int(number) if number.isdigit() else 0


def cmd_build(args) -> int:
    """Elaborate, gate, persist, and run the plan. The whole pipeline."""
    result = _elaborate(args)
    workspace = Workspace(args.directory)
    snapshot = _with_measurements(result.snapshot, workspace)
    plan = result.plan.with_snapshot(snapshot.hash)

    # Canonical state advances only through the gate, even here.
    graph = KernelGraph(
        Snapshot(snapshot.project_id, "REV-000000"), checks=DEFAULT_CHECKS
    )
    operations = tuple(
        AddEntity(entity=entity, reason="elaborated")
        for entity in sorted(snapshot.entities.values(), key=lambda e: e.id)
    )
    proposal = graph.apply(Transaction(graph.head.hash, operations))
    if proposal.rejected:
        report_diagnostics(proposal.diagnostics)
        print("fang: the commit gate rejected the build", file=sys.stderr)
        return EXIT_FAILED

    manifest = workspace.write_snapshot(snapshot)
    workspace.write_plan(plan)

    run = execute(
        plan,
        snapshot,
        default_registry(),
        workspace=workspace.dir / "cache",
        traits=result.traits,
        checks=DEFAULT_CHECKS,
    )
    for tool_result in run.results:
        print(f"  {tool_result.tool:10} {tool_result.status.value:12} {tool_result.message}")

    print(f"{manifest.entity_count} entities, snapshot {manifest.snapshot}")
    return EXIT_OK if run.succeeded else EXIT_FAILED


def cmd_check(args) -> int:
    result = _elaborate(args)
    failures, undecided, total = 0, 0, 0
    for check in DEFAULT_CHECKS:
        for outcome in check.run(result.snapshot):
            total += 1
            if outcome.status is CheckStatus.FAIL:
                failures += 1
                print(f"FAIL {outcome.check}: {outcome.message}", file=sys.stderr)
            elif outcome.status is CheckStatus.UNKNOWN:
                undecided += 1
                print(f"UNDECIDED {outcome.check}: {outcome.message}")

    print(f"{total} checks, {failures} failed, {undecided} undecided")
    return EXIT_FAILED if failures else EXIT_OK


def cmd_netlist(args) -> int:
    result = _elaborate(args)
    netlist = compile_netlist(result.snapshot, traits=result.traits)
    for component in netlist.components:
        print(f"{component.designator:6} {component.value:16} {component.footprint or '-'}")
    for net in netlist.nets:
        nodes = " ".join(f"{n.designator}.{n.pin}" for n in net.nodes)
        print(f"{net.name:24} {nodes}")
    return EXIT_OK


def cmd_export(args) -> int:
    result = _elaborate(args)
    netlist = compile_netlist(result.snapshot, traits=result.traits)
    text = emit_netlist(netlist, source=Path(args.program).name)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        sys.stdout.write(text)
    return EXIT_OK


def cmd_schematic(args) -> int:
    """Lower a snapshot to a KiCad schematic, and render it if asked to."""
    from .schematic import KicadRenderer, RendererUnavailable, compile_schematic

    result = _elaborate(args)
    name = Path(args.program).stem
    if getattr(args, "drafter", "fang") == "copperhead":
        from .copperhead import (
            CopperheadDrafter,
            DraftRefused,
            DrafterUnavailable,
            compile_intent,
        )

        intent = compile_intent(result.snapshot, traits=result.traits, group=name)
        for loss in intent.losses:
            print(f"fang: {loss}", file=sys.stderr)
        try:
            text = CopperheadDrafter().draft(
                intent, workspace=Workspace(args.directory).dir / "drafts", name=name
            )
        except (DrafterUnavailable, DraftRefused) as exc:
            print(f"fang: {exc}", file=sys.stderr)
            return EXIT_FAILED
    else:
        text = compile_schematic(result.snapshot, traits=result.traits, title=name)

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"wrote {args.output}")
    elif not args.svg:
        sys.stdout.write(text)

    if not args.svg:
        return EXIT_OK

    workspace = Workspace(args.directory)
    try:
        svg = KicadRenderer().to_svg(
            text, workspace=workspace.dir / "schematics", name=name
        )
    except RendererUnavailable as exc:
        print(f"fang: {exc}", file=sys.stderr)
        return EXIT_FAILED
    Path(args.svg).write_text(svg, encoding="utf-8")
    print(f"wrote {args.svg}")
    return EXIT_OK


def cmd_graph(args) -> int:
    result = _elaborate(args)
    counts: dict[str, int] = {}
    for entity in result.snapshot.entities.values():
        counts[entity.kind] = counts.get(entity.kind, 0) + 1
    for kind in sorted(counts):
        print(f"{counts[kind]:5}  {kind}")
    print(f"{len(result.snapshot):5}  total")
    print(f"snapshot {result.snapshot.hash}")
    return EXIT_OK


def cmd_view(args) -> int:
    """Compile a view and render it, or list the views available."""
    if args.list:
        for name in REQUIRED_VIEWS:
            print(f"{name:13} {VIEW_REGISTRY[name].question}")
        return EXIT_OK

    result = _elaborate(args)
    if args.name not in VIEW_REGISTRY:
        print(
            f"fang: no view named {args.name!r}; try --list", file=sys.stderr
        )
        return EXIT_FAILED

    graph = view(result.snapshot, args.name)
    if args.output:
        Path(args.output).write_text(
            to_svg(place(graph, seeds=PlacementSeeds())), encoding="utf-8"
        )
        print(f"wrote {args.output}")
    else:
        print(f"{graph.spec.name}: {graph.spec.question}")
        print(f"  {len(graph.nodes)} nodes, {len(graph.edges)} edges")
        completeness = graph.completeness()
        if not completeness["complete"]:
            print(
                f"  {completeness['nodes_with_unknowns']} node(s) carry unknown "
                "parameters"
            )
        for note in graph.notes:
            print(f"  note: {note}")
    return EXIT_OK


def cmd_sim(args) -> int:
    """Compile a simulation plan, lower it, and run it if the backend is there."""
    from .simulation import (
        BackendUnavailable,
        NgspiceBackend,
        OperatingPoint,
        SimulationError,
        Transient,
        compile_plan,
        lower_to_spice,
        normalize,
    )

    result = _elaborate(args)
    analysis = (
        Transient(stop=args.stop, step=args.step, probes=tuple(args.probe or ()))
        if args.analysis == "transient"
        else OperatingPoint(probes=tuple(args.probe or ()))
    )

    try:
        plan = compile_plan(
            result.snapshot, backend=args.backend, analysis=analysis, traits=result.traits
        )
    except SimulationError as exc:
        print(f"fang: the simulation plan was rejected: {exc}", file=sys.stderr)
        return EXIT_FAILED

    deck = lower_to_spice(
        result.snapshot, plan, traits=result.traits, title=Path(args.program).name
    )
    if args.output:
        Path(args.output).write_text(deck, encoding="utf-8")
        print(f"wrote {args.output}")

    for gap in plan.coverage_gaps:
        print(f"  coverage gap: {gap}")

    backend = NgspiceBackend()
    if not backend.available():
        print(
            f"fang: {args.backend} is not installed; the plan compiled but no run "
            "was made and no result is fabricated",
            file=sys.stderr,
        )
        return EXIT_FAILED

    workspace = Workspace(args.directory)
    raw = backend.run(deck, workspace=workspace.dir / "simulations")
    normalized = normalize(plan, raw)
    finding = normalized.as_finding()
    print(f"{finding['result']} on {normalized.backend} {normalized.backend_version}")
    print(f"  {finding['caveat']}")
    return EXIT_OK if normalized.passed else EXIT_FAILED


def cmd_emulate(args) -> int:
    """Run each emulation question's firmware in Renode and print what it measured.

    The low-level command, as `fang sim` is for SPICE: each question's plan is
    compiled and lowered, its bundle written where asked, and the run made if
    Renode is installed. Nothing goes through the gate and no workspace
    changes; `fang verify` is the command that takes the answer back in.
    """
    from tempfile import TemporaryDirectory

    from .emulation import RENODE
    from .verification import NotRunnable, ToolUnavailable, _quantity_text, questions

    result = _elaborate(args)
    asked = [q for q in questions(result.snapshot) if q.method == "emulation"]
    if not asked:
        print(f"nothing to emulate: {Path(args.program).name} declares no emulation question")
        return EXIT_OK

    status = EXIT_OK
    for question in asked:
        print(f"{question.label} ({question.id})")
        try:
            job = RENODE.prepare(result.snapshot, question, traits=result.traits)
        except NotRunnable as exc:
            print(f"  not runnable [{exc.code}]: {exc}")
            status = EXIT_FAILED
            continue
        print(f"  plan {job.extra['plan']}")
        if args.output:
            folder = Path(args.output) / question.label.rsplit(".", 1)[-1]
            folder.mkdir(parents=True, exist_ok=True)
            for path, content in sorted(job.files.items()):
                data = content.encode("utf-8") if isinstance(content, str) else content
                (folder / path).write_bytes(data)
            print(f"  wrote the bundle to {folder}")
        if args.bundle_only:
            continue
        try:
            if not RENODE.available():
                raise ToolUnavailable("renode is not installed")
            RENODE.version()
            with TemporaryDirectory() as scratch:
                raw = RENODE.run(job, workspace=Path(scratch))
        except ToolUnavailable as exc:
            print(f"  unsupported: {exc}; nothing ran and no result is fabricated")
            continue
        print(f"  renode {raw.version}: the run {raw.outputs.get('outcome', 'ended')}")
        for measurement in RENODE.read(job, raw):
            if measurement.quantity is None:
                print(f"  {measurement.name}: no value ({measurement.reason})")
            else:
                print(f"  {measurement.name} = {_quantity_text(measurement.quantity, 3)}")
    return status


def cmd_verify(args) -> int:
    """Route and run every declared question, and persist only on --commit.

    Each question is printed with its level, its tool, its measurements and
    its result, or the reason it did not run. A failed verification exits
    non-zero, as does a question the program left unrunnable; a tool that is
    not installed is reported and is not by itself a failure.
    """
    from tempfile import TemporaryDirectory

    from .verification import NOT_RUNNABLE, REJECTED, questions, report, verify

    result = _elaborate(args)
    workspace = Workspace(args.directory)
    if args.commit and not workspace.manifest_path.exists():
        print(
            "fang: --commit persists into an existing workspace, and there is none "
            f"at {workspace.dir}; run 'fang build' first",
            file=sys.stderr,
        )
        return EXIT_FAILED

    head = _with_measurements(result.snapshot, workspace)
    from .emulation import stale

    for label, path, recorded, current in stale(head):
        print(
            f"stale: {label}: {path} is now {current}, not the {recorded} its evidence "
            "names; it runs again"
        )
    if not questions(head):
        print(f"nothing to verify: {Path(args.program).name} declares no question")
        return EXIT_OK

    graph = KernelGraph(
        head, checks=DEFAULT_CHECKS, revision_counter=_revision_number(head.revision_id)
    )
    with TemporaryDirectory() as scratch:
        # Without --commit nothing is written into the workspace, not even a
        # scratch deck; with it, each run's files are kept beside its evidence.
        runs = workspace.dir / "simulations" if args.commit else Path(scratch)
        outcomes = verify(graph, traits=result.traits, workspace=runs)

    for line in report(outcomes):
        print(line)

    if args.commit:
        if workspace.read_manifest().snapshot == graph.head.hash:
            print("nothing new to commit")
        else:
            manifest = workspace.write_snapshot(graph.head)
            print(f"committed {manifest.entity_count} entities, snapshot {manifest.snapshot}")

    unfinished = any(o.status in (NOT_RUNNABLE, REJECTED) for o in outcomes)
    return EXIT_FAILED if any(o.failed for o in outcomes) or unfinished else EXIT_OK


def cmd_mcp(args) -> int:
    """Serve the agent surface over stdio, bound to one project root."""
    from .diagnostics import MCP_DEPENDENCY_MISSING

    try:
        from .mcp import Session, serve
    except ImportError:
        # This module imports no SDK, so the missing extra surfaces where
        # `build_server` reaches for it — below, as a coded refusal. The guard
        # stays for the case where fang.mcp itself cannot be imported.
        print(
            f"fang: {MCP_DEPENDENCY_MISSING}: the agent surface needs the "
            "protocol dependency, which is not installed; install it with "
            "'pip install \"copperhead-fang[mcp]\"'",
            file=sys.stderr,
        )
        return EXIT_FAILED

    try:
        session = Session(
            args.directory,
            args.program,
            system=getattr(args, "system", None),
            project_id=args.project,
            checks=DEFAULT_CHECKS,
        )
        # Named rather than degraded: a server that cannot speak the protocol
        # is not a smaller server, it is a broken one.
        serve(session)
    except FangError as exc:
        report_diagnostics([exc.diagnostic])
        return EXIT_FAILED

    return EXIT_OK


def cmd_diff(args) -> int:
    """Diff a program against the workspace's persisted design."""
    workspace = find_workspace(args.directory)
    if workspace is None or not workspace.manifest_path.exists():
        print("fang: no workspace to diff against; run 'fang build' first", file=sys.stderr)
        return EXIT_FAILED

    result = _elaborate(args)
    snapshot = _with_measurements(result.snapshot, workspace)
    manifest = workspace.read_manifest()
    if manifest.snapshot == snapshot.hash:
        print("no change")
        return EXIT_OK

    stored = {record["id"] for record in workspace.read_records()}
    current = set(snapshot.entities)
    for entity_id in sorted(current - stored):
        print(f"+ {entity_id} {snapshot.entities[entity_id].kind}")
    for entity_id in sorted(stored - current):
        print(f"- {entity_id}")
    print(f"snapshot {manifest.snapshot[:19]} -> {snapshot.hash[:19]}")
    return EXIT_OK


# --------------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fang", description="The Fang hardware kernel")
    parser.add_argument("--version", action="version", version=f"fang {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def program_arguments(sub):
        sub.add_argument("program", help="the Fang program to elaborate")
        sub.add_argument("--system", help="which system to build, if the file has several")
        sub.add_argument("--project", default="PRJ-LOCAL", help="the project identifier")
        sub.add_argument("-C", "--directory", default=".", help="the project directory")
        return sub

    init = subparsers.add_parser("init", help="create a workspace")
    init.add_argument("-C", "--directory", default=".", help="the project directory")
    init.set_defaults(handler=cmd_init)

    program_arguments(subparsers.add_parser("build", help="elaborate, gate, persist, and run the plan")).set_defaults(handler=cmd_build)
    program_arguments(subparsers.add_parser("check", help="run the check classes")).set_defaults(handler=cmd_check)
    program_arguments(subparsers.add_parser("netlist", help="show the compiled netlist")).set_defaults(handler=cmd_netlist)
    program_arguments(subparsers.add_parser("graph", help="summarize the kernel graph")).set_defaults(handler=cmd_graph)
    program_arguments(subparsers.add_parser("diff", help="diff a program against the workspace")).set_defaults(handler=cmd_diff)
    program_arguments(subparsers.add_parser("mcp", help="serve the agent surface over stdio")).set_defaults(handler=cmd_mcp)

    view_command = subparsers.add_parser("view", help="compile and render a view")
    view_command.add_argument("program", nargs="?", help="the Fang program to elaborate")
    view_command.add_argument("name", nargs="?", default="interconnect", help="which view")
    view_command.add_argument("--list", action="store_true", help="list the available views")
    view_command.add_argument("--system", help="which system, if the file has several")
    view_command.add_argument("--project", default="PRJ-LOCAL", help="the project identifier")
    view_command.add_argument("-C", "--directory", default=".", help="the project directory")
    view_command.add_argument("-o", "--output", help="write SVG here instead of summarizing")
    view_command.set_defaults(handler=cmd_view)

    emulate = program_arguments(
        subparsers.add_parser("emulate", help="run the firmware in Renode and print what it measured")
    )
    emulate.add_argument("-o", "--output", help="write each question's bundle into a folder here")
    emulate.add_argument("--bundle-only", action="store_true", help="write the bundles and run nothing")
    emulate.set_defaults(handler=cmd_emulate)

    sim = program_arguments(subparsers.add_parser("sim", help="compile and run a simulation"))
    sim.add_argument("--analysis", choices=("op", "transient"), default="op")
    sim.add_argument("--backend", default="ngspice")
    sim.add_argument("--stop", default="1ms")
    sim.add_argument("--step", default="1us")
    sim.add_argument("--probe", action="append", help="a signal to probe; repeatable")
    sim.add_argument("-o", "--output", help="write the SPICE deck here")
    sim.set_defaults(handler=cmd_sim)

    verify_command = program_arguments(
        subparsers.add_parser("verify", help="route and run every declared question")
    )
    verify_command.add_argument(
        "--commit",
        action="store_true",
        help="persist the measurements into the existing workspace",
    )
    verify_command.set_defaults(handler=cmd_verify)

    export = program_arguments(subparsers.add_parser("export", help="write a KiCad netlist"))
    export.add_argument("-o", "--output", help="where to write it; stdout by default")
    export.set_defaults(handler=cmd_export)

    schematic = program_arguments(
        subparsers.add_parser("schematic", help="write a KiCad schematic")
    )
    schematic.add_argument(
        "-o", "--output", help="where to write the .kicad_sch; stdout by default"
    )
    schematic.add_argument("--svg", help="also render it here, with kicad-cli")
    schematic.add_argument(
        "--drafter",
        choices=("fang", "copperhead"),
        default="fang",
        help="who draws the sheet: fang's grid, or copperhead's placed and wired draft",
    )
    schematic.set_defaults(handler=cmd_schematic)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except SystemExit as exit_code:
        return exit_code.code if isinstance(exit_code.code, int) else EXIT_FAILED


if __name__ == "__main__":       # pragma: no cover
    raise SystemExit(main())
