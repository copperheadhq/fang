"""The tool plan: operations a program requests are recorded, not performed.

Spec: "Tool Plan Emission". A tool call returns a handle, not a result. Reading
a handle during elaboration is an error, because a program that could observe an
operation's result would not be reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from .diagnostics import ELAB_HANDLE_READ, SourceLocation, error


@dataclass(frozen=True)
class Condition:
    """A symbolic condition on a future result.

    ``report.passed`` is one of these. It is recorded in the plan and resolved
    when the operation phase runs; it is never a value during elaboration.
    """

    call: int
    attribute: str

    def _refuse(self, *args, **kwargs):
        raise error(
            ELAB_HANDLE_READ,
            f"the condition {self.attribute!r} on call {self.call} cannot be read "
            "during elaboration; it is resolved in the operation phase",
        )

    __bool__ = _refuse
    __eq__ = _refuse
    __ne__ = _refuse
    __lt__ = _refuse
    __le__ = _refuse
    __gt__ = _refuse
    __ge__ = _refuse
    __hash__ = None  # type: ignore[assignment]

    def as_dict(self) -> dict:
        return {"call": self.call, "attribute": self.attribute}


class Handle:
    """A name for a result the operation phase will produce.

    Attribute access yields a `Condition`. Converting the handle to a boolean,
    branching on it, or comparing it is an elaboration error.
    """

    __slots__ = ("_call", "_tool")

    def __init__(self, call: int, tool: str) -> None:
        object.__setattr__(self, "_call", call)
        object.__setattr__(self, "_tool", tool)

    @property
    def call(self) -> int:
        return self._call

    def __getattr__(self, name: str) -> Condition:
        if name.startswith("_"):
            raise AttributeError(name)
        return Condition(self._call, name)

    def _refuse(self, *args, **kwargs):
        raise error(
            ELAB_HANDLE_READ,
            f"the result of {self._tool!r} cannot be read during elaboration; a "
            "program that observed an operation's result would not be reproducible",
        )

    __bool__ = _refuse
    __eq__ = _refuse
    __ne__ = _refuse
    __lt__ = _refuse
    __le__ = _refuse
    __gt__ = _refuse
    __ge__ = _refuse
    __iter__ = _refuse
    __len__ = _refuse
    __hash__ = None  # type: ignore[assignment]

    def as_dict(self) -> dict:
        return {"handle": self._call, "tool": self._tool}


@dataclass(frozen=True)
class ToolCall:
    """One recorded call. It names a versioned tool and carries its own source."""

    index: int
    tool: str
    arguments: Mapping[str, Any] = field(default_factory=dict)
    conditions: tuple[Condition, ...] = ()
    source_location: SourceLocation | None = None

    def as_dict(self) -> dict:
        out: dict = {
            "index": self.index,
            "tool": self.tool,
            "arguments": {k: _argument(v) for k, v in sorted(self.arguments.items())},
        }
        if self.conditions:
            out["conditions"] = [c.as_dict() for c in self.conditions]
        if self.source_location is not None:
            out["source_location"] = self.source_location.as_dict()
        return out


def _argument(value: Any):
    if isinstance(value, Handle):
        return value.as_dict()
    if isinstance(value, Condition):
        return value.as_dict()
    if hasattr(value, "as_dict"):
        return value.as_dict()
    if isinstance(value, Mapping):
        return {k: _argument(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_argument(v) for v in value]
    return value


@dataclass(frozen=True)
class ToolPlan:
    """The plan: the snapshot it applies to, the ordered calls, and the source map.

    The plan is data. It may be inspected, diffed, stored, and replayed without
    re-executing the program.
    """

    snapshot: str = ""
    calls: tuple[ToolCall, ...] = ()

    def as_dict(self) -> dict:
        return {
            "snapshot": self.snapshot,
            # Call order is the program's order and carries meaning.
            "calls": [call.as_dict() for call in self.calls],
            "source_map": [
                {
                    "call": call.index,
                    "source_location": call.source_location.as_dict()
                    if call.source_location
                    else None,
                }
                for call in self.calls
            ],
        }

    def with_snapshot(self, snapshot: str) -> "ToolPlan":
        return ToolPlan(snapshot, self.calls)

    def __len__(self) -> int:
        return len(self.calls)

    def __iter__(self):
        return iter(self.calls)


class PlanRecorder:
    """Records tool calls during elaboration. Performs nothing."""

    def __init__(self) -> None:
        self._calls: list[ToolCall] = []

    def record(
        self,
        tool: str,
        arguments: Mapping[str, Any],
        *,
        source_location: SourceLocation | None = None,
    ) -> Handle:
        conditions = tuple(
            value for value in arguments.values() if isinstance(value, Condition)
        )
        index = len(self._calls)
        self._calls.append(
            ToolCall(index, tool, dict(arguments), conditions, source_location)
        )
        return Handle(index, tool)

    def plan(self) -> ToolPlan:
        return ToolPlan("", tuple(self._calls))
