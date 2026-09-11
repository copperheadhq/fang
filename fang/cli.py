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


def cmd_build(args) -> int:
    """Elaborate, gate, persist, and run the plan. The whole pipeline."""
    result = _elaborate(args)

    # Canonical state advances only through the gate, even here.
    graph = KernelGraph(
        Snapshot(result.snapshot.project_id, "REV-000000"), checks=DEFAULT_CHECKS
    )
    operations = tuple(
        AddEntity(entity=entity, reason="elaborated")
        for entity in sorted(result.snapshot.entities.values(), key=lambda e: e.id)
    )
    proposal = graph.apply(Transaction(graph.head.hash, operations))
    if proposal.rejected:
        report_diagnostics(proposal.diagnostics)
        print("fang: the commit gate rejected the build", file=sys.stderr)
        return EXIT_FAILED

    workspace = Workspace(args.directory)
    manifest = workspace.write_snapshot(result.snapshot)
    workspace.write_plan(result.plan)

    run = execute(
        result.plan,
        result.snapshot,
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
    manifest = workspace.read_manifest()
    if manifest.snapshot == result.snapshot.hash:
        print("no change")
        return EXIT_OK

    stored = {record["id"] for record in workspace.read_records()}
    current = set(result.snapshot.entities)
    for entity_id in sorted(current - stored):
        print(f"+ {entity_id} {result.snapshot.entities[entity_id].kind}")
    for entity_id in sorted(stored - current):
        print(f"- {entity_id}")
    print(f"snapshot {manifest.snapshot[:19]} -> {result.snapshot.hash[:19]}")
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

    sim = program_arguments(subparsers.add_parser("sim", help="compile and run a simulation"))
    sim.add_argument("--analysis", choices=("op", "transient"), default="op")
    sim.add_argument("--backend", default="ngspice")
    sim.add_argument("--stop", default="1ms")
    sim.add_argument("--step", default="1us")
    sim.add_argument("--probe", action="append", help="a signal to probe; repeatable")
    sim.add_argument("-o", "--output", help="write the SPICE deck here")
    sim.set_defaults(handler=cmd_sim)

    export = program_arguments(subparsers.add_parser("export", help="write a KiCad netlist"))
    export.add_argument("-o", "--output", help="where to write it; stdout by default")
    export.set_defaults(handler=cmd_export)

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
