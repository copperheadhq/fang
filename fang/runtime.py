"""The operation phase: executing a tool plan.

Spec: "Tool Plan Emission", "Tool Terminal Statuses", "Conditions Resolve In The
Operation Phase", "Tool Calls Are Idempotent", and "The Operation Phase Does Not
Mutate Canonical State".

Operations run against immutable snapshots and produce candidate realizations.
Nothing here reaches canonical state; what a run implies returns through a
transaction and its gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence

from .graph import Realization, Snapshot
from .serialization import canonical_dumps
from .toolplan import Condition, Handle, ToolCall, ToolPlan


class Status(Enum):
    """How a call ended. Exactly one of these, always."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"

    @property
    def terminal(self) -> bool:
        return True


@dataclass(frozen=True)
class ToolResult:
    """What one call produced."""

    call: int
    tool: str
    status: Status
    value: Any = None
    message: str = ""
    realization: Realization | None = None

    @property
    def passed(self) -> bool:
        """The attribute a plan's `report.passed` condition resolves against."""
        return self.status is Status.SUCCEEDED

    def attribute(self, name: str) -> Any:
        if name == "passed":
            return self.passed
        if isinstance(self.value, Mapping) and name in self.value:
            return self.value[name]
        return getattr(self.value, name, None)

    def as_dict(self) -> dict:
        out: dict = {"call": self.call, "tool": self.tool, "status": self.status.value}
        if self.message:
            out["message"] = self.message
        if self.realization is not None:
            out["realization"] = self.realization.as_dict()
        return out


class Tool(Protocol):
    """A versioned tool. The runtime executes these; a program never calls one."""

    name: str
    version: str

    def run(self, arguments: Mapping[str, Any], context: "RunContext") -> ToolResult: ...


@dataclass
class RunContext:
    """What a tool is given: a snapshot, a workspace, and the run's identity."""

    snapshot: Snapshot
    workspace: Path | None = None
    traits: Any = None
    checks: Sequence[Any] = ()
    seed: int | None = None
    results: dict[int, ToolResult] = field(default_factory=dict)


class ToolRegistry:
    def __init__(self, tools: Sequence[Tool] = ()) -> None:
        self._tools: dict[str, Tool] = {tool.name: tool for tool in tools}

    def register(self, tool: Tool) -> Tool:
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)

    def __contains__(self, name: object) -> bool:
        return name in self._tools


@dataclass(frozen=True)
class Run:
    """One execution of a plan against one snapshot."""

    snapshot: str
    results: tuple[ToolResult, ...]

    @property
    def succeeded(self) -> bool:
        return all(
            result.status in (Status.SUCCEEDED, Status.SKIPPED) for result in self.results
        )

    def result(self, call: int) -> ToolResult | None:
        for result in self.results:
            if result.call == call:
                return result
        return None

    def realizations(self) -> tuple[Realization, ...]:
        return tuple(r.realization for r in self.results if r.realization is not None)

    def as_dict(self) -> dict:
        return {
            "snapshot": self.snapshot,
            "succeeded": self.succeeded,
            "results": [result.as_dict() for result in self.results],
        }


def _cache_key(call: ToolCall, snapshot: Snapshot, seed: int | None) -> str:
    """Idempotence is over the snapshot, the arguments, the configuration, and
    the seed — exactly what the contract says, and nothing else."""
    resolvable = {
        key: value
        for key, value in call.arguments.items()
        if not isinstance(value, (Handle, Condition))
    }
    return canonical_dumps(
        {
            "tool": call.tool,
            "snapshot": snapshot.hash,
            "arguments": resolvable,
            "seed": seed,
        }
    )


def execute(
    plan: ToolPlan,
    snapshot: Snapshot,
    registry: ToolRegistry,
    *,
    workspace: Path | None = None,
    traits: Any = None,
    checks: Sequence[Any] = (),
    seed: int | None = None,
    cache: dict[str, ToolResult] | None = None,
) -> Run:
    """Run a plan. Mutates nothing; returns what each call produced."""
    context = RunContext(snapshot, workspace, traits, checks, seed)
    cache = cache if cache is not None else {}
    results: list[ToolResult] = []

    for call in plan.calls:
        skip = _skipped_because(call, context)
        if skip is not None:
            result = ToolResult(call.index, call.tool, Status.SKIPPED, message=skip)
            results.append(result)
            context.results[call.index] = result
            continue

        tool = registry.get(call.tool)
        if tool is None:
            result = ToolResult(
                call.index,
                call.tool,
                Status.UNSUPPORTED,
                message=f"no tool named {call.tool!r} is registered",
            )
            results.append(result)
            context.results[call.index] = result
            continue

        key = _cache_key(call, snapshot, seed)
        cached = cache.get(key)
        if cached is not None:
            result = ToolResult(
                call.index, call.tool, cached.status, cached.value, cached.message,
                cached.realization,
            )
        else:
            arguments = _resolve(call.arguments, context)
            try:
                result = tool.run(arguments, context)
            except Exception as exc:                     # a tool's failure is data
                result = ToolResult(
                    call.index, call.tool, Status.FAILED, message=str(exc)
                )
            result = ToolResult(
                call.index, result.tool or call.tool, result.status, result.value,
                result.message, result.realization,
            )
            cache[key] = result

        results.append(result)
        context.results[call.index] = result

    return Run(snapshot.hash, tuple(results))


def _skipped_because(call: ToolCall, context: RunContext) -> str | None:
    """Resolve the call's conditions. A false one skips it, and says so."""
    for condition in call.conditions:
        earlier = context.results.get(condition.call)
        if earlier is None:
            return f"call {condition.call} did not run, so {condition.attribute} is unknown"
        if not earlier.attribute(condition.attribute):
            return (
                f"condition {condition.attribute} on call {condition.call} "
                f"({earlier.tool}) resolved false"
            )
    return None


def _resolve(arguments: Mapping[str, Any], context: RunContext) -> dict:
    """Replace handles with the results they name."""
    resolved: dict[str, Any] = {}
    for key, value in arguments.items():
        if isinstance(value, Handle):
            resolved[key] = context.results.get(value.call)
        elif isinstance(value, Condition):
            earlier = context.results.get(value.call)
            resolved[key] = earlier.attribute(value.attribute) if earlier else None
        else:
            resolved[key] = value
    return resolved


# --------------------------------------------------------------------------
# The built-in tools
# --------------------------------------------------------------------------


@dataclass
class NetlistTool:
    """Compile the snapshot into a netlist."""

    name: str = "netlist"
    version: str = "1.0"

    def run(self, arguments: Mapping[str, Any], context: RunContext) -> ToolResult:
        from .netlist import compile_netlist

        netlist = compile_netlist(context.snapshot, traits=context.traits)
        return ToolResult(
            0,
            self.name,
            Status.SUCCEEDED,
            value=netlist,
            message=f"{len(netlist.components)} components, {len(netlist.nets)} nets",
            realization=Realization(
                "netlist",
                context.snapshot.hash,
                configuration={"format": "fang"},
                tools=(f"{self.name} {self.version}",),
            ),
        )


@dataclass
class CheckTool:
    """Run the registered check classes over the snapshot."""

    name: str = "check"
    version: str = "1.0"

    def run(self, arguments: Mapping[str, Any], context: RunContext) -> ToolResult:
        from .constraints import CheckStatus

        results = []
        for check in context.checks:
            results.extend(check.run(context.snapshot))

        failures = [r for r in results if r.status is CheckStatus.FAIL]
        undecided = [r for r in results if r.status is CheckStatus.UNKNOWN]
        status = Status.SUCCEEDED if not failures else Status.FAILED
        return ToolResult(
            0,
            self.name,
            status,
            value={"results": results, "failures": failures, "undecided": undecided},
            message=(
                f"{len(results)} checks, {len(failures)} failed, "
                f"{len(undecided)} undecided"
            ),
        )


@dataclass
class ExportTool:
    """Write a netlist to disk. The only tool here that touches the filesystem."""

    name: str = "export"
    version: str = "1.0"

    def run(self, arguments: Mapping[str, Any], context: RunContext) -> ToolResult:
        from .kicad import emit_netlist
        from .netlist import compile_netlist

        fmt = arguments.get("format", "kicad")
        if fmt != "kicad":
            return ToolResult(
                0,
                self.name,
                Status.UNSUPPORTED,
                message=f"no exporter for format {fmt!r}",
            )

        source = arguments.get("source", "fang")
        upstream = arguments.get("netlist") or arguments.get("layout")
        netlist = getattr(upstream, "value", None)
        if netlist is None or not hasattr(netlist, "components"):
            netlist = compile_netlist(context.snapshot, traits=context.traits)

        text = emit_netlist(netlist, source=source)
        written: str | None = None
        if context.workspace is not None:
            path = Path(context.workspace) / arguments.get("filename", "design.net")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
            written = str(path)

        return ToolResult(
            0,
            self.name,
            Status.SUCCEEDED,
            value={"text": text, "path": written},
            message=f"exported {len(netlist.components)} components",
            realization=Realization(
                "kicad_netlist",
                context.snapshot.hash,
                configuration={"format": fmt, "source": source},
                tools=(f"{self.name} {self.version}",),
            ),
        )


def default_registry() -> ToolRegistry:
    """The tools a project starts with."""
    return ToolRegistry((NetlistTool(), CheckTool(), ExportTool()))
