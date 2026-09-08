"""The kernel graph: immutable snapshots, transactions, and the commit gate.

Spec: "Transactions Are The Only Unit Of Mutation", "Proposal Sandbox", and
"The Commit Gate".

A transaction is applied to a copy. The copy is normalized, validated, and
checked; only then does the head advance. Rejection discards the copy, which
makes "a rejected proposal leaves canonical state unchanged" true by
construction rather than by discipline.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Callable, Iterable, Mapping, Sequence

from . import SCHEMA_VERSION, __version__
from .constraints import CheckStatus, Constraint, Resolver
from .diagnostics import (
    Diagnostic,
    Severity,
    TXN_APPROVAL_REQUIRED,
    TXN_GATE_BLOCKED,
    TXN_MALFORMED_ENTITY,
    TXN_STALE_SNAPSHOT,
    TXN_UNDECIDED_BLOCKED,
    error,
)
from .diff import Diff, diff
from .entities import (
    ROOT_COLLECTIONS,
    ROOT_MAPPINGS,
    Connection,
    ConnectionKind,
    Entity,
)
from .provenance import Provenance, ProvenanceRecord
from .serialization import canonical_bytes, content_hash
from .validation import ValidationReport, validate
from .values import Parameter, Value


# --------------------------------------------------------------------------
# Snapshots
# --------------------------------------------------------------------------

#: Which root collection an entity kind belongs to.
_COLLECTION_OF: Mapping[str, str] = {
    "requirement": "requirements",
    "block": "architecture",
    "interface": "interfaces",
    "port": "ports",
    "bus": "buses",
    "domain": "domains",
    "component": "components",
    "model": "models",
    "net": "nets",
    "rail": "nets",
    "circuit": "circuits",
    "connection": "connections",
    "decision": "decisions",
    "evidence": "evidence",
    "constraint": "constraints",
    "calculation": "calculations",
    "verification": "verifications",
    "assumption": "assumptions",
    "outcome": "outcomes",
}


@dataclass(frozen=True)
class Snapshot:
    """An immutable graph state.

    The snapshot records the schema version, the compiler version, and the
    dependency lock identity, so its producer is reconstructible. It carries no
    wall-clock time, so identical inputs give byte-identical snapshots.
    """

    project_id: str
    revision_id: str
    entities: Mapping[str, Entity] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION
    compiler_version: str = __version__
    lock_id: str = "unlocked"
    extracted_upstream: tuple[str, ...] = ()

    def with_entities(self, entities: Mapping[str, Entity], revision_id: str) -> "Snapshot":
        return replace(self, entities=dict(entities), revision_id=revision_id)

    def as_dict(self) -> dict:
        """The logical root.

        Every defined key is present, including one whose collection is empty, so
        that a missing key identifies an artifact produced under an older schema
        rather than an empty layer.
        """
        root: dict = {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "revision_id": self.revision_id,
            "compiler_version": self.compiler_version,
            "lock_id": self.lock_id,
        }
        for collection in ROOT_COLLECTIONS:
            root[collection] = []
        for mapping in ROOT_MAPPINGS:
            root[mapping] = {}
        if self.extracted_upstream:
            root["extracted_upstream"] = sorted(self.extracted_upstream)

        for entity in self.entities.values():
            collection = _COLLECTION_OF.get(entity.kind)
            if collection is None:
                root.setdefault("extensions", {}).setdefault(entity.kind, []).append(
                    entity.as_dict()
                )
            else:
                root[collection].append(entity.as_dict())
        return root

    def records(self) -> list[dict]:
        """The typed entity records, for the canonical record stream."""
        return [entity.as_dict() for entity in self.entities.values()]

    @property
    def hash(self) -> str:
        return content_hash(self.as_dict())

    def resolver(self) -> Resolver:
        """Resolve an entity attribute to its value, for expression evaluation."""

        def resolve(entity_id: str, attr: str) -> Value | None:
            entity = self.entities.get(entity_id)
            if entity is None:
                return None
            value = entity.parameters.get(attr)
            return value if isinstance(value, Value) else None

        return resolve

    def __len__(self) -> int:
        return len(self.entities)


# --------------------------------------------------------------------------
# Operations
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Operation:
    """A structured operation.

    An operation carries its reason and the requirements it serves where they are
    known. An effect representable as an operation is never expressed as a file
    edit instead.
    """

    reason: str = ""
    requirement_refs: tuple[str, ...] = ()

    @property
    def op(self) -> str:
        raise NotImplementedError

    def affected(self) -> tuple[str, ...]:
        raise NotImplementedError

    def apply(self, entities: dict[str, Entity]) -> None:
        raise NotImplementedError

    def as_dict(self) -> dict:
        out: dict = {"op": self.op}
        if self.reason:
            out["reason"] = self.reason
        if self.requirement_refs:
            out["requirement_refs"] = sorted(self.requirement_refs)
        return out


@dataclass(frozen=True)
class AddEntity(Operation):
    entity: Entity | None = None

    @property
    def op(self) -> str:
        return "add_entity"

    def affected(self) -> tuple[str, ...]:
        return (self.entity.id,)

    def apply(self, entities: dict[str, Entity]) -> None:
        if self.entity.id in entities:
            raise error(
                TXN_MALFORMED_ENTITY,
                f"{self.entity.id} already exists; adding it again would make the "
                "identifier ambiguous",
                entities=[self.entity.id],
            )
        entities[self.entity.id] = self.entity

    def as_dict(self) -> dict:
        out = super().as_dict()
        out["entity"] = self.entity.as_dict()
        return out


@dataclass(frozen=True)
class RemoveEntity(Operation):
    target: str = ""

    @property
    def op(self) -> str:
        return "remove_entity"

    def affected(self) -> tuple[str, ...]:
        return (self.target,)

    def apply(self, entities: dict[str, Entity]) -> None:
        if self.target not in entities:
            raise error(
                TXN_MALFORMED_ENTITY, f"{self.target} does not exist", entities=[self.target]
            )
        del entities[self.target]

    def as_dict(self) -> dict:
        out = super().as_dict()
        out["target"] = self.target
        return out


@dataclass(frozen=True)
class Connect(Operation):
    """Connect two entities. The structured form of a connection edit."""

    connection: Connection | None = None

    @property
    def op(self) -> str:
        return "connect"

    def affected(self) -> tuple[str, ...]:
        return (self.connection.id, self.connection.source, self.connection.target)

    def apply(self, entities: dict[str, Entity]) -> None:
        entities[self.connection.id] = self.connection

    def as_dict(self) -> dict:
        out = super().as_dict()
        out.update(
            {
                "from": self.connection.source,
                "to": self.connection.target,
                "kind": self.connection.connection_kind.value,
                "id": self.connection.id,
            }
        )
        return out


@dataclass(frozen=True)
class SetParameter(Operation):
    target: str = ""
    name: str = ""
    value: Parameter | None = None

    @property
    def op(self) -> str:
        return "set_parameter"

    def affected(self) -> tuple[str, ...]:
        return (self.target,)

    def apply(self, entities: dict[str, Entity]) -> None:
        entity = entities.get(self.target)
        if entity is None:
            raise error(
                TXN_MALFORMED_ENTITY,
                f"{self.target} does not exist",
                entities=[self.target],
            )
        entities[self.target] = entity.with_parameter(self.name, self.value)

    def as_dict(self) -> dict:
        out = super().as_dict()
        out.update(
            {
                "target": f"{self.target}.{self.name}",
                "value": self.value.as_dict() if self.value is not None else None,
            }
        )
        return out


# --------------------------------------------------------------------------
# Checks and policy
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CheckResult:
    check: str
    status: CheckStatus
    subject: str
    message: str = ""
    severity: Severity = Severity.ERROR
    paths: tuple[tuple[str, ...], ...] = ()   # topology findings name their paths
    missing: tuple[str, ...] = ()             # an undecided result names its gaps
    evidence: tuple[str, ...] = ()            # the evidence entities behind the inputs

    @property
    def blocking(self) -> bool:
        return self.status is CheckStatus.FAIL and self.severity.blocking

    def as_dict(self) -> dict:
        out = {
            "check": self.check,
            "status": self.status.value,
            "subject": self.subject,
            "severity": self.severity.value,
        }
        if self.message:
            out["message"] = self.message
        if self.paths:
            out["paths"] = [list(p) for p in self.paths]
        if self.missing:
            out["missing"] = list(self.missing)
        if self.evidence:
            out["evidence"] = sorted(self.evidence)
        return out


@dataclass(frozen=True)
class CheckClass:
    """One check class. Its scope decides whether the gate requires it."""

    name: str
    run: Callable[[Snapshot], list[CheckResult]]
    scope: Callable[[Snapshot], set[str]]

    def intersects(self, snapshot: Snapshot, affected: set[str]) -> bool:
        return bool(self.scope(snapshot) & affected)


def structural_constraint_check(snapshot: Snapshot) -> list[CheckResult]:
    """Evaluate every constraint in the graph. The default electrical check."""
    resolve = snapshot.resolver()
    results = []
    for entity in snapshot.entities.values():
        if isinstance(entity, Constraint):
            status = entity.evaluate(resolve)
            results.append(
                CheckResult(
                    "constraint",
                    status,
                    entity.id,
                    message=f"{entity.constraint_kind} on {', '.join(sorted(entity.targets))}",
                )
            )
    return results


CONSTRAINT_CHECK = CheckClass(
    "constraint",
    structural_constraint_check,
    lambda snapshot: {
        target
        for entity in snapshot.entities.values()
        if isinstance(entity, Constraint)
        for target in entity.targets
    }
    | {e.id for e in snapshot.entities.values() if isinstance(e, Constraint)},
)


@dataclass(frozen=True)
class Policy:
    """The active project policy over the gate.

    A policy narrows or widens the required check set but never removes the
    structural check.
    """

    required_checks: frozenset[str] | None = None
    must_be_decided: frozenset[str] = frozenset()
    approvals_required: frozenset[str] = frozenset()
    approvals_granted: frozenset[str] = frozenset()

    def required(self, available: Sequence[CheckClass], snapshot: Snapshot, affected: set[str]) -> list[CheckClass]:
        if self.required_checks is not None:
            return [c for c in available if c.name in self.required_checks]
        # Absent a policy, the required set is structural validation together with
        # every check class whose scope intersects the affected entities.
        return [c for c in available if c.intersects(snapshot, affected)]


DEFAULT_POLICY = Policy()


# --------------------------------------------------------------------------
# Transactions and proposals
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Transaction:
    """The only unit of mutation. Atomic, and it names its base snapshot."""

    base: str                       # the content hash of the snapshot proposed against
    operations: tuple[Operation, ...]
    origin: ProvenanceRecord | None = None   # differs by mutation path; nothing else does

    def affected(self) -> set[str]:
        return {ref for op in self.operations for ref in op.affected()}

    def as_dict(self) -> dict:
        out: dict = {"base": self.base, "operations": [op.as_dict() for op in self.operations]}
        if self.origin is not None:
            out["origin"] = self.origin.as_dict()
        return out


@dataclass(frozen=True)
class Proposal:
    """The outcome of applying a transaction to a candidate branch.

    A rejected proposal still produces its diagnostics and its diff, because the
    explanation is the useful output of a rejection.
    """

    transaction: Transaction
    candidate: Snapshot | None
    validation: ValidationReport
    checks: tuple[CheckResult, ...]
    diff: Diff
    diagnostics: tuple[Diagnostic, ...]
    accepted: bool

    @property
    def rejected(self) -> bool:
        return not self.accepted

    def as_dict(self) -> dict:
        return {
            "accepted": self.accepted,
            "transaction": self.transaction.as_dict(),
            "diagnostics": [d.as_dict() for d in self.diagnostics],
            "checks": [c.as_dict() for c in self.checks],
            "diff": self.diff.as_list(),
        }


class KernelGraph:
    """The live kernel graph. Its head advances only through a committed
    transaction."""

    def __init__(
        self,
        snapshot: Snapshot,
        *,
        checks: Sequence[CheckClass] = (CONSTRAINT_CHECK,),
        policy: Policy = DEFAULT_POLICY,
        revision_counter: int = 0,
    ) -> None:
        self._head = snapshot
        self._checks = list(checks)
        self.policy = policy
        self._revision = revision_counter
        self._history: list[Snapshot] = [snapshot]

    @property
    def head(self) -> Snapshot:
        return self._head

    @property
    def history(self) -> tuple[Snapshot, ...]:
        return tuple(self._history)

    def _next_revision(self) -> str:
        self._revision += 1
        return f"REV-{self._revision:06d}"

    # -- the sandbox -------------------------------------------------------

    def propose(self, transaction: Transaction, *, policy: Policy | None = None) -> Proposal:
        """Apply a transaction to a candidate branch and run the gate.

        Canonical state is never touched here. The branch is discarded on
        rejection.
        """
        policy = policy or self.policy
        diagnostics: list[Diagnostic] = []

        # A transaction proposed against a snapshot that is no longer current is
        # rebased and re-verified, or rejected. It is never applied on the
        # assumption that the intervening change was unrelated.
        if transaction.base != self._head.hash:
            diagnostics.append(
                Diagnostic(
                    TXN_STALE_SNAPSHOT,
                    Severity.ERROR,
                    f"transaction was proposed against {transaction.base}, but the "
                    f"head is {self._head.hash}; rebase and re-verify it",
                )
            )
            return Proposal(
                transaction, None, ValidationReport(), (), Diff(), tuple(diagnostics), False
            )

        # Gate condition 1: it normalizes into well-formed entities.
        entities = dict(self._head.entities)
        try:
            for operation in transaction.operations:
                operation.apply(entities)
        except Exception as exc:
            diagnostic = getattr(exc, "diagnostic", None) or Diagnostic(
                TXN_MALFORMED_ENTITY, Severity.ERROR, str(exc)
            )
            diagnostics.append(diagnostic)
            return Proposal(
                transaction, None, ValidationReport(), (), Diff(), tuple(diagnostics), False
            )

        candidate = self._head.with_entities(entities, self._next_revision())
        changes = diff(self._head.entities, candidate.entities)

        # Gate condition 2: structural validation.
        report = validate(candidate.entities)
        diagnostics.extend(report.diagnostics)

        # Gate condition 3: every required check class has run.
        affected = transaction.affected()
        required = policy.required(self._checks, candidate, affected)
        results: list[CheckResult] = []
        for check in required:
            results.extend(check.run(candidate))

        # Gate condition 4: no required check reports a blocking severity.
        blocking = [r for r in results if r.blocking]
        for result in blocking:
            diagnostics.append(
                Diagnostic(
                    TXN_GATE_BLOCKED,
                    Severity.ERROR,
                    f"{result.check} on {result.subject} failed: {result.message}",
                    (result.subject,),
                )
            )

        # Gate condition 5: no undecided result covers a must-be-decided
        # requirement. An undecided result is neither a pass nor a failure; whether
        # it blocks is the policy's decision, made here rather than by the evaluator.
        for result in results:
            if result.status is not CheckStatus.UNKNOWN:
                continue
            constraint = candidate.entities.get(result.subject)
            source = getattr(constraint, "source", None)
            if source in policy.must_be_decided:
                diagnostics.append(
                    Diagnostic(
                        TXN_UNDECIDED_BLOCKED,
                        Severity.ERROR,
                        f"{result.subject} is undecided and covers {source}, which "
                        "the policy marks must-be-decided",
                        (result.subject, source),
                    )
                )

        # Gate condition 6: the policy's approval requirements are satisfied.
        missing_approvals = policy.approvals_required - policy.approvals_granted
        for approval in sorted(missing_approvals):
            diagnostics.append(
                Diagnostic(
                    TXN_APPROVAL_REQUIRED,
                    Severity.ERROR,
                    f"policy requires the approval {approval!r}, which is not granted",
                )
            )

        accepted = not any(d.severity.blocking for d in diagnostics)
        return Proposal(
            transaction, candidate, report, tuple(results), changes, tuple(diagnostics), accepted
        )

    def commit(self, proposal: Proposal) -> Snapshot:
        """Advance the head. Only a proposal that passed the gate may commit."""
        if not proposal.accepted or proposal.candidate is None:
            raise error(
                TXN_GATE_BLOCKED,
                "a proposal that did not pass the gate does not commit; "
                "canonical state is unchanged",
            )
        if proposal.transaction.base != self._head.hash:
            raise error(
                TXN_STALE_SNAPSHOT,
                "the head moved after this proposal was verified; rebase and "
                "re-verify it",
            )
        self._head = proposal.candidate
        self._history.append(proposal.candidate)
        return self._head

    def apply(self, transaction: Transaction, *, policy: Policy | None = None) -> Proposal:
        """Propose and, if the gate passes, commit. One call for the common path."""
        proposal = self.propose(transaction, policy=policy)
        if proposal.accepted:
            self.commit(proposal)
        return proposal


# --------------------------------------------------------------------------
# Realizations
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Realization:
    """A compiled projection naming the snapshot it came from.

    A realization is a candidate until verified, and never mutates semantic state
    as a side effect. Where a compiled result implies a semantic change, that
    change returns through a transaction.
    """

    kind: str
    parent_snapshot: str
    configuration: Mapping[str, str] = field(default_factory=dict)
    tools: tuple[str, ...] = ()
    verified: bool = False
    implied_changes: tuple[Operation, ...] = ()

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "parent_snapshot": self.parent_snapshot,
            "configuration": dict(self.configuration),
            "tools": sorted(self.tools),
            "verified": self.verified,
            "implied_changes": [op.as_dict() for op in self.implied_changes],
        }

    def to_transaction(self, base: str) -> Transaction:
        """Return the implied semantic changes as a transaction.

        This is the only way a realization's implications reach canonical state.
        """
        return Transaction(base, self.implied_changes)


def materialize(realization: Realization, committed: Snapshot) -> bytes:
    """Materialize a downstream artifact.

    Only after commit are downstream artifacts materialized, so this refuses a
    realization whose parent is not the committed snapshot.
    """
    if realization.parent_snapshot != committed.hash:
        raise error(
            TXN_GATE_BLOCKED,
            "a downstream artifact is materialized only after its parent "
            "snapshot is committed",
        )
    return canonical_bytes(realization.as_dict())


def ingest_external_results(
    graph: "KernelGraph",
    results: Sequence[CheckResult],
    *,
    snapshot_hash: str,
    activity: str = "external_rule_check",
    actor: str = "kicad-drc",
    record_time=None,
) -> Proposal:
    """Ingest external check results as evidence, after commit.

    External checks such as CAD rule checking run only once the transaction has
    committed, and their results enter as evidence entities through a
    transaction like any other mutation. Ingesting against anything but the
    committed head is refused, so the ordering cannot be inverted by accident.
    """
    from datetime import datetime, timezone

    from .entities import Evidence
    from .identity import authored as authored_identity
    from .provenance import Actor, ActorKind, Provenance, ProvenanceOrigin, ProvenanceRecord

    if snapshot_hash != graph.head.hash:
        raise error(
            TXN_GATE_BLOCKED,
            "external results are ingested against the committed head; the "
            "snapshot they were produced from is no longer current",
        )

    moment = record_time or datetime.now(timezone.utc)
    operations = []
    for index, result in enumerate(results):
        provenance = Provenance().append(
            ProvenanceRecord(
                ProvenanceOrigin.IMPORTED,
                activity,
                Actor(ActorKind.ADAPTER, actor),
                graph.head.revision_id,
                moment,
                derived_from=(result.subject,) if result.subject in graph.head.entities else (),
            )
        )
        operations.append(
            AddEntity(
                entity=Evidence(
                    authored_identity(f"EVD-{actor}-{index:03d}"),
                    claim=f"{result.check} reported {result.status.value}: {result.message}",
                    document=actor,
                    provenance=provenance,
                ),
                reason="ingest external check result as evidence",
            )
        )

    return graph.apply(Transaction(graph.head.hash, tuple(operations)))
