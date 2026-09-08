"""The agent surface.

Spec: "The Agent Surface", "Agent Mutation Passes The Commit Gate",
"Deterministic Agent Responses", "The Agent Session Is Bound To One Project",
"Undecided Crosses The Agent Boundary Intact", and "The Agent Surface Refuses
With A Code".

The module is two layers. Everything above `build_server` is the projection: it
maps kernel state to canonical-JSON-ready dictionaries and imports nothing from
the protocol SDK, so the surface's behaviour is testable without a client and
the core install stays free of the dependency. `build_server` is the
registration layer, and is the only place that knows the protocol exists.

The mutation path here is the ordinary one. `propose` calls `KernelGraph.propose`
and `commit` calls `KernelGraph.commit`; there is no route around the gate,
because the gate is what makes the agent's path the same path as everyone
else's.
"""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from . import __version__
from .checks import DEFAULT_CHECKS
from .constraints import CheckStatus
from .diagnostics import (
    MCP_MALFORMED_ARGUMENT,
    MCP_PATH_OUTSIDE_ROOT,
    MCP_UNACCEPTED_PROPOSAL,
    MCP_UNKNOWN_OPERATION,
    MCP_UNKNOWN_TOOL,
    Diagnostic,
    FangError,
    error,
)
from .elaborate import elaborate
from .entities import Connection, ConnectionKind
from .graph import (
    DEFAULT_POLICY,
    Connect,
    KernelGraph,
    Operation,
    Policy,
    Proposal,
    RemoveEntity,
    SetParameter,
    Snapshot,
    Transaction,
)
from .lang import System
from .netlist import compile_netlist
from .queries import (
    causing_requirements,
    decisions_on_changed_evidence,
    dependents,
    lost_verification,
    supporting_evidence,
    unverified_assumptions,
)
from .serialization import canonical_bytes
from .units import Quantity
from .values import Value
from .views import REGISTRY as VIEW_REGISTRY, REQUIRED_VIEWS, view
from .workspace import Workspace

#: The default page of an entity read. The whole snapshot is a resource an agent
#: asks for deliberately; it is never the incidental payload of a question.
PAGE = 50


class ElaborationFailed(Exception):
    """The bound program did not elaborate.

    Carries the diagnostics rather than a partial snapshot, because a partial
    snapshot is the thing the surface must never hand back.
    """

    def __init__(self, diagnostics: Sequence[Diagnostic]) -> None:
        super().__init__(f"{len(diagnostics)} diagnostic(s)")
        self.diagnostics = tuple(diagnostics)


# --------------------------------------------------------------------------
# Loading the bound program
# --------------------------------------------------------------------------


def _load_system(path: Path, name: str | None = None) -> type[System]:
    """Import a Fang program and find the system it defines.

    A failure here is a refusal with a code, not a `SystemExit`: the surface is
    answering a client, not running a command.
    """
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise error(MCP_MALFORMED_ARGUMENT, f"{path} could not be imported")
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
        raise error(MCP_MALFORMED_ARGUMENT, f"{path} defines no system named {name!r}")
    if not systems:
        raise error(MCP_MALFORMED_ARGUMENT, f"{path} defines no System subclass")
    if len(systems) > 1:
        names = ", ".join(sorted(s.__name__ for s in systems))
        raise error(
            MCP_MALFORMED_ARGUMENT,
            f"{path} defines more than one system ({names}); name one when binding",
        )
    return systems[0]


# --------------------------------------------------------------------------
# The session
# --------------------------------------------------------------------------


class Session:
    """One session, bound to one project root and one program inside it.

    The root is named when the server starts, never by the client. Every path a
    client can reach goes through `resolve`, which is the whole of the
    containment story at this layer; below it is the elaboration sandbox, which
    already exists and which this module never disables.
    """

    def __init__(
        self,
        root: Path | str,
        program: Path | str | None,
        *,
        system: str | None = None,
        project_id: str = "PRJ-LOCAL",
        policy: Policy = DEFAULT_POLICY,
        checks: Sequence = DEFAULT_CHECKS,
    ) -> None:
        self.root = Path(root).resolve()
        self.system = system
        self.project_id = project_id
        # The policy the project set. The surface never constructs a more
        # permissive one, because the gate's approval condition is the control
        # for an unattended commit and widening it here would move that control
        # out of the gate.
        self.policy = policy
        self.checks = tuple(checks)
        self.program = self.resolve(program) if program is not None else None

        #: How many times the program has actually been executed. A sequence of
        #: read-only questions elaborates once.
        self.elaborations = 0
        self._cache_key: str | None = None
        self._cache: Any = None
        self._graph: KernelGraph | None = None
        self._proposals: dict[str, Proposal] = {}
        self._proposal_count = 0

    @classmethod
    def over(
        cls,
        snapshot: Snapshot,
        *,
        root: Path | str = ".",
        policy: Policy = DEFAULT_POLICY,
        checks: Sequence = DEFAULT_CHECKS,
    ) -> "Session":
        """A session over a snapshot already in hand.

        The embedded case: a caller that has elaborated for itself binds the
        graph directly rather than handing over a program to re-execute. There
        is no program, so there is nothing to reload and nothing to sandbox.
        """
        session = cls(root, None, policy=policy, checks=checks)
        session._graph = KernelGraph(snapshot, checks=session.checks, policy=policy)
        return session

    # -- containment -------------------------------------------------------

    def resolve(self, path: Path | str) -> Path:
        """The one gate every client-named path passes through."""
        candidate = Path(path)
        candidate = candidate if candidate.is_absolute() else self.root / candidate
        candidate = candidate.resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise error(
                MCP_PATH_OUTSIDE_ROOT,
                f"{path} resolves outside the bound project root {self.root}; "
                "the session reads and executes nothing outside it",
            )
        return candidate

    # -- state -------------------------------------------------------------

    def elaboration(self):
        """Elaborate the bound program, once per content hash.

        The sandbox is enforced — `elaborate` enforces it by default and this
        module never passes `enforce_sandbox=False`.
        """
        if self.program is None:
            raise error(
                MCP_MALFORMED_ARGUMENT,
                "this session was bound to a snapshot, not to a program; there "
                "is nothing to elaborate",
            )
        key = hashlib.sha256(self.program.read_bytes()).hexdigest()
        if self._cache_key == key and self._cache is not None:
            return self._cache
        system = _load_system(self.program, self.system)
        result = elaborate(system, project_id=self.project_id)
        self.elaborations += 1
        self._cache_key, self._cache = key, result
        return result

    def snapshot(self) -> Snapshot:
        """The committed head, or a refusal carrying every diagnostic."""
        return self.graph().head

    def graph(self) -> KernelGraph:
        if self._graph is None:
            result = self.elaboration()
            if not result.ok:
                raise ElaborationFailed(result.diagnostics)
            self._graph = KernelGraph(
                result.snapshot, checks=self.checks, policy=self.policy
            )
        return self._graph

    def traits(self):
        if self.program is None:
            from .traits import TraitRegistry

            return TraitRegistry()
        return self.elaboration().traits

    def workspace(self) -> Workspace | None:
        """The persisted workspace, where one exists beside the sources."""
        workspace = Workspace(self.root)
        return workspace if workspace.exists else None

    def reload(self, program: Path | str | None = None) -> None:
        """Re-bind and re-elaborate. A named program is contained like any path."""
        if program is not None:
            self.program = self.resolve(program)
        self._cache_key, self._cache, self._graph = None, None, None
        self._proposals.clear()

    # -- proposals ---------------------------------------------------------

    def hold(self, proposal: Proposal) -> str:
        self._proposal_count += 1
        handle = f"proposal-{self._proposal_count:04d}"
        self._proposals[handle] = proposal
        return handle

    def held(self, handle: str) -> Proposal:
        proposal = self._proposals.get(handle)
        if proposal is None:
            raise error(
                MCP_MALFORMED_ARGUMENT, f"no proposal is held under {handle!r}"
            )
        return proposal


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def render(payload: Mapping[str, Any]) -> str:
    """Canonical JSON text.

    Determinism is inherited from the one serializer rather than re-derived, so
    identical state gives identical bytes on any machine and in any process.
    """
    return canonical_bytes(payload).decode("utf-8")


def _answer(session: Session, payload: Mapping[str, Any]) -> dict:
    """Every answer names the snapshot it was computed against."""
    out = dict(payload)
    out["snapshot"] = session.graph().head.hash
    return out


def _refusal(diagnostics: Iterable[Diagnostic]) -> dict:
    return {"ok": False, "diagnostics": [d.as_dict() for d in diagnostics]}


def guarded(call, *args, **kwargs) -> dict:
    """Run a projection, turning any refusal into a coded diagnostic payload.

    Nothing is fabricated in place of the work that was not done: a refusal
    carries its code and says so.
    """
    try:
        return call(*args, **kwargs)
    except ElaborationFailed as failure:
        return _refusal(failure.diagnostics)
    except FangError as exc:
        return _refusal([exc.diagnostic])


# --------------------------------------------------------------------------
# The projection
# --------------------------------------------------------------------------


def project_summary(session: Session) -> dict:
    snapshot = session.graph().head
    counts: dict[str, int] = {}
    for entity in snapshot.entities.values():
        counts[entity.kind] = counts.get(entity.kind, 0) + 1
    return _answer(
        session,
        {
            "ok": True,
            "project_id": snapshot.project_id,
            "revision_id": snapshot.revision_id,
            "schema_version": snapshot.schema_version,
            "compiler_version": snapshot.compiler_version,
            "entity_count": len(snapshot),
            "kinds": counts,
            "program": session.program.name if session.program else None,
        },
    )


def project_entities(
    session: Session,
    *,
    kind: str | None = None,
    offset: int = 0,
    limit: int = PAGE,
) -> dict:
    """A scoped, paginated page of entity records."""
    snapshot = session.graph().head
    if offset < 0 or limit < 1:
        raise error(
            MCP_MALFORMED_ARGUMENT, "offset is not negative and limit is at least one"
        )
    matching = sorted(
        (e for e in snapshot.entities.values() if kind is None or e.kind == kind),
        key=lambda e: e.id,
    )
    page = matching[offset : offset + limit]
    return _answer(
        session,
        {
            "ok": True,
            "total": len(matching),
            "offset": offset,
            "limit": limit,
            "entities": [entity.as_dict() for entity in page],
        },
    )


def project_entity(session: Session, entity_id: str) -> dict:
    """One entity.

    A parameter that was set to an explicit unknown is present and carries the
    unknown status; a parameter that was never set is simply absent. The two are
    different facts and the projection keeps them different.
    """
    snapshot = session.graph().head
    entity = snapshot.entities.get(entity_id)
    if entity is None:
        raise error(MCP_MALFORMED_ARGUMENT, f"no entity {entity_id!r} in this snapshot")
    return _answer(
        session,
        {"ok": True, "entity": entity.as_dict(), "references": list(entity.references())},
    )


def project_manifest(session: Session) -> dict:
    """The persisted workspace's manifest, where a workspace exists."""
    workspace = session.workspace()
    if workspace is None or not workspace.manifest_path.exists():
        return _answer(session, {"ok": True, "workspace": None})
    return _answer(
        session, {"ok": True, "workspace": workspace.read_manifest().as_dict()}
    )


def workspace_entity_ids(session: Session) -> list[str]:
    """The identifiers the workspace persisted, for comparison with the program."""
    workspace = session.workspace()
    if workspace is None:
        return []
    return sorted(record["id"] for record in workspace.read_records())


def project_netlist(session: Session) -> dict:
    snapshot = session.graph().head
    netlist = compile_netlist(snapshot, traits=session.traits())
    return _answer(session, {"ok": True, "netlist": netlist.as_dict()})


def project_checks(session: Session) -> dict:
    """Every check result, with undecided kept as a third status.

    An undecided result is neither a pass nor a failure, so it is counted and
    reported as itself. Whether it blocks is the gate's decision, not this
    projection's.
    """
    snapshot = session.graph().head
    results = []
    for check in session.checks:
        results.extend(check.run(snapshot))
    # Every status the kernel can report gets a count, so none is folded into
    # another on the way out. Undecided is one of them, and stays one of them.
    counts = {status.value: 0 for status in CheckStatus}
    for result in results:
        counts[result.status.value] += 1
    return _answer(
        session,
        {
            "ok": True,
            "total": len(results),
            "counts": counts,
            "results": [r.as_dict() for r in results],
        },
    )


def project_views(session: Session) -> dict:
    return _answer(
        session,
        {
            "ok": True,
            "views": [
                {"name": name, "question": VIEW_REGISTRY[name].question}
                for name in REQUIRED_VIEWS
            ],
        },
    )


def project_view(session: Session, name: str) -> dict:
    """One view, with the notes recording what it left out."""
    if name not in VIEW_REGISTRY:
        raise error(
            MCP_MALFORMED_ARGUMENT,
            f"no view named {name!r}; the required views are "
            f"{', '.join(REQUIRED_VIEWS)}",
        )
    snapshot = session.graph().head
    graph = view(snapshot, name)
    return _answer(
        session,
        {
            "ok": True,
            "view": graph.as_dict(),
            "completeness": graph.completeness(),
        },
    )


#: The rationale questions, each answered from graph structure alone.
RATIONALE_QUESTIONS = (
    "causing_requirements",
    "supporting_evidence",
    "dependents",
    "unverified_assumptions",
    "decisions_on_changed_evidence",
    "lost_verification",
)


def project_rationale(
    session: Session,
    question: str,
    *,
    entity: str | None = None,
    parameter: str | None = None,
    evidence: Sequence[str] = (),
    proposal: str | None = None,
) -> dict:
    """Answer one rationale question.

    Every answer is computed from recorded structure — provenance, decisions,
    references — with no inference step.
    """
    snapshot = session.graph().head

    def needs(name: str, value):
        if value is None:
            raise error(
                MCP_MALFORMED_ARGUMENT, f"{question!r} needs {name!r}"
            )
        return value

    if question == "causing_requirements":
        answer = causing_requirements(snapshot, needs("entity", entity))
    elif question == "supporting_evidence":
        answer = supporting_evidence(
            snapshot, needs("entity", entity), needs("parameter", parameter)
        )
    elif question == "dependents":
        answer = dependents(snapshot, needs("entity", entity))
    elif question == "unverified_assumptions":
        answer = unverified_assumptions(snapshot)
    elif question == "decisions_on_changed_evidence":
        answer = decisions_on_changed_evidence(snapshot, evidence)
    elif question == "lost_verification":
        # The only query over a change rather than a state, so it is asked
        # against the diff a held proposal would make.
        held = session.held(needs("proposal", proposal))
        answer = lost_verification(snapshot, held.diff)
    else:
        raise error(
            MCP_UNKNOWN_TOOL,
            f"no rationale question named {question!r}; the questions are "
            f"{', '.join(RATIONALE_QUESTIONS)}",
        )
    return _answer(session, {"ok": True, "question": question, "answer": answer})


def project_snapshot(session: Session) -> dict:
    """The whole logical root. A resource, asked for deliberately."""
    return session.graph().head.as_dict()


def project_records(session: Session) -> str:
    """The canonical record stream of the head."""
    from .serialization import canonical_record_stream

    return canonical_record_stream(session.graph().head.records()).decode("utf-8")


# --------------------------------------------------------------------------
# The mutation path
# --------------------------------------------------------------------------


def _quantity(payload: Mapping[str, Any]) -> Quantity:
    unit = payload.get("unit")
    if unit is None:
        raise error(MCP_MALFORMED_ARGUMENT, "a quantity names its unit")
    if "magnitude" in payload:
        return Quantity.scalar(str(payload["magnitude"]), unit)
    if "tolerance" in payload and "nominal" in payload:
        return Quantity.with_tolerance(
            str(payload["nominal"]), str(payload["tolerance"]), unit
        )
    if payload.get("minimum") is not None and payload.get("maximum") is not None:
        return Quantity.range(
            str(payload["minimum"]), str(payload["maximum"]), unit
        )
    raise error(
        MCP_MALFORMED_ARGUMENT,
        "a quantity is a magnitude, a nominal with a tolerance, or a range",
    )


def _value(payload: Mapping[str, Any]) -> Value:
    """Build a value from its status.

    An unknown is a status, never an absent quantity, so it is constructed
    explicitly rather than inferred from a missing field.
    """
    status = payload.get("status")
    if status == "unknown":
        return Value.unknown()
    quantity = _quantity(payload.get("quantity") or {})
    if status == "explicit":
        return Value.explicit(quantity, payload.get("source"))
    if status == "inferred":
        source, confidence = payload.get("source"), payload.get("confidence")
        if source is None or confidence is None:
            raise error(
                MCP_MALFORMED_ARGUMENT,
                "an inferred value names its source and its confidence",
            )
        return Value.inferred(quantity, source, str(confidence))
    if status == "assumed":
        rationale = payload.get("rationale")
        if rationale is None:
            raise error(MCP_MALFORMED_ARGUMENT, "an assumed value names its rationale")
        return Value.assumed(quantity, rationale)
    raise error(
        MCP_MALFORMED_ARGUMENT,
        f"{status!r} is not a value status; it is explicit, inferred, assumed, "
        "or unknown",
    )


def build_operation(payload: Mapping[str, Any]) -> Operation:
    """Build one operation the gate evaluates.

    Only the gate's own operation kinds are constructible here. An unrecognized
    kind is refused rather than approximated, because an operation the gate does
    not evaluate is not a mutation the surface may offer.
    """
    if not isinstance(payload, Mapping):
        raise error(MCP_MALFORMED_ARGUMENT, "an operation is an object")
    kind = payload.get("op")

    if kind == "remove_entity":
        target = payload.get("target")
        if not isinstance(target, str) or not target:
            raise error(MCP_MALFORMED_ARGUMENT, "remove_entity names a target")
        return RemoveEntity(reason=str(payload.get("reason", "agent")), target=target)

    if kind == "set_parameter":
        target, name = payload.get("target"), payload.get("name")
        if not isinstance(target, str) or not isinstance(name, str):
            raise error(
                MCP_MALFORMED_ARGUMENT, "set_parameter names a target and a name"
            )
        return SetParameter(
            reason=str(payload.get("reason", "agent")),
            target=target,
            name=name,
            value=_value(payload.get("value") or {}),
        )

    if kind == "connect":
        source, to = payload.get("from"), payload.get("to")
        identifier, connection_kind = payload.get("id"), payload.get("kind")
        if not all(isinstance(v, str) and v for v in (source, to, identifier)):
            raise error(
                MCP_MALFORMED_ARGUMENT, "connect names from, to, and an id"
            )
        try:
            resolved = ConnectionKind(connection_kind)
        except ValueError:
            kinds = ", ".join(sorted(k.value for k in ConnectionKind))
            raise error(
                MCP_MALFORMED_ARGUMENT,
                f"{connection_kind!r} is not a connection kind; they are {kinds}",
            ) from None
        from .identity import authored

        return Connect(
            reason=str(payload.get("reason", "agent")),
            connection=Connection(
                authored(identifier),
                connection_kind=resolved,
                source=source,
                target=to,
            ),
        )

    if kind == "add_entity":
        # The gate does evaluate this one. What is missing is a way to build a
        # typed entity from a document: identity, provenance, and a source
        # location all have to be minted, and the kernel has no rehydration
        # registry to mint them with. Saying so is better than approximating it.
        raise error(
            MCP_UNKNOWN_OPERATION,
            "add_entity is evaluated by the gate but is not constructible here: "
            "an entity carries identity, provenance, and a source location, and "
            "there is no rehydration of those from a document yet. Author new "
            "entities in the Fang program and reload.",
        )

    raise error(
        MCP_UNKNOWN_OPERATION,
        f"{kind!r} is not an operation the commit gate evaluates; they are "
        "add_entity, remove_entity, connect, and set_parameter",
    )


def propose(session: Session, operations: Sequence[Mapping[str, Any]]) -> dict:
    """Submit a transaction to the gate.

    The response is the whole proposal — accepted or rejected, with its
    diagnostics and the diff it would have made — because the explanation is the
    useful output of a rejection.
    """
    graph = session.graph()
    if not isinstance(operations, Sequence) or isinstance(operations, (str, bytes)):
        raise error(MCP_MALFORMED_ARGUMENT, "operations is a list")
    if not operations:
        raise error(MCP_MALFORMED_ARGUMENT, "a transaction carries at least one operation")

    built = tuple(build_operation(payload) for payload in operations)
    proposal = graph.propose(Transaction(graph.head.hash, built))
    handle = session.hold(proposal)
    return _answer(
        session,
        {
            "ok": True,
            "handle": handle,
            "proposal": proposal.as_dict(),
            "head": graph.head.hash,
        },
    )


def commit(session: Session, handle: str) -> dict:
    """Advance the head.

    Only a proposal the gate accepted may commit, and the response names the
    revision the head moved to, so the movement is never silent.
    """
    graph = session.graph()
    proposal = session.held(handle)
    if not proposal.accepted:
        raise error(
            MCP_UNACCEPTED_PROPOSAL,
            f"{handle} did not pass the gate; canonical state is unchanged. "
            "Its diagnostics say what to fix.",
            entities=[d.code for d in proposal.diagnostics],
        )
    before = graph.head.hash
    head = graph.commit(proposal)
    return {
        "ok": True,
        "committed": True,
        "handle": handle,
        "from": before,
        "revision_id": head.revision_id,
        "snapshot": head.hash,
    }


# --------------------------------------------------------------------------
# The registration layer
# --------------------------------------------------------------------------
#
# The only place that imports the protocol SDK. Everything above is reachable,
# and tested, without it.


REQUIREMENT = (
    "the protocol dependency is not installed; install it with "
    "'pip install \"copperhead-fang[mcp]\"'"
)


def build_server(session: Session, *, name: str = "fang"):
    """Register the projection as tools and resources over the protocol.

    Every tool returns canonical JSON text rather than a structure the SDK
    reserializes, so the bytes an agent reads are the bytes this kernel
    produced.
    """
    from mcp.server import MCPServer          # noqa: PLC0415 - the one SDK import

    server = MCPServer(name=name, version=__version__)

    def text(call, *args, **kwargs) -> str:
        return render(guarded(call, *args, **kwargs))

    @server.tool(description="Summarize the committed snapshot.", structured_output=False)
    def summary() -> str:
        return text(project_summary, session)

    @server.tool(
        description="Read a scoped, paginated page of entity records.",
        structured_output=False,
    )
    def entities(kind: str | None = None, offset: int = 0, limit: int = PAGE) -> str:
        return text(project_entities, session, kind=kind, offset=offset, limit=limit)

    @server.tool(description="Read one entity by identifier.", structured_output=False)
    def entity(id: str) -> str:
        return text(project_entity, session, id)

    @server.tool(
        description="Read the persisted workspace manifest.", structured_output=False
    )
    def manifest() -> str:
        return text(project_manifest, session)

    @server.tool(description="Compile and read the netlist.", structured_output=False)
    def netlist() -> str:
        return text(project_netlist, session)

    @server.tool(
        description="Run the check classes. Undecided is a third status.",
        structured_output=False,
    )
    def checks() -> str:
        return text(project_checks, session)

    @server.tool(description="List the required views.", structured_output=False)
    def views() -> str:
        return text(project_views, session)

    @server.tool(
        name="view",
        description="Compile one view, with the notes recording what it omitted.",
        structured_output=False,
    )
    def view(name: str) -> str:
        return text(project_view, session, name)

    @server.tool(
        description=(
            "Ask a rationale question: " + ", ".join(RATIONALE_QUESTIONS) + "."
        ),
        structured_output=False,
    )
    def rationale(
        question: str,
        entity: str | None = None,
        parameter: str | None = None,
        evidence: list[str] | None = None,
        proposal: str | None = None,
    ) -> str:
        return text(
            project_rationale,
            session,
            question,
            entity=entity,
            parameter=parameter,
            evidence=tuple(evidence or ()),
            proposal=proposal,
        )

    @server.tool(
        description=(
            "Submit a transaction to the commit gate. Returns the whole "
            "proposal — accepted or rejected — with its diagnostics and diff."
        ),
        name="propose",
        structured_output=False,
    )
    def propose(operations: list[dict]) -> str:
        return text(propose, session, operations)

    @server.tool(
        name="commit",
        description="Advance the head with a proposal the gate accepted.",
        structured_output=False,
    )
    def commit(handle: str) -> str:
        return text(commit, session, handle)

    @server.tool(
        name="reload",
        description="Re-elaborate the bound program, optionally naming another "
        "program inside the project root.",
        structured_output=False,
    )
    def reload(program: str | None = None) -> str:
        def run() -> dict:
            session.reload(program)
            return project_summary(session)

        return render(guarded(run))

    @server.resource(
        "fang://snapshot", mime_type="application/json", name="snapshot",
        description="The whole logical root of the committed snapshot.",
    )
    def snapshot_resource() -> str:
        return render(guarded(project_snapshot, session))

    @server.resource(
        "fang://records", mime_type="application/x-ndjson", name="records",
        description="The canonical record stream of the committed snapshot.",
    )
    def records_resource() -> str:
        try:
            return project_records(session)
        except ElaborationFailed as failure:
            return render(_refusal(failure.diagnostics))
        except FangError as exc:
            return render(_refusal([exc.diagnostic]))

    return server


def serve(session: Session) -> None:
    """Serve one session over stdio.

    stdio only: the session is bound to a local project root and a local
    workspace, and a network listener would widen the trust boundary for no gain.
    """
    build_server(session).run(transport="stdio")
