"""Spec: Transactions Are The Only Unit Of Mutation; Proposal Sandbox; The
Commit Gate; Realizations Do Not Mutate Semantic State."""

import pytest

from conftest import PROJECT, REGULATOR, WATTS, conductive

from fang.constraints import CheckStatus, Constraint, Enforcement, Literal, Ref, le
from fang.diagnostics import FangError
from fang.entities import Component, ConnectionKind, Requirement, RequirementState
from fang.graph import (
    AddEntity,
    Connect,
    KernelGraph,
    Policy,
    Realization,
    RemoveEntity,
    SetParameter,
    Snapshot,
    Transaction,
    materialize,
)
from fang.identity import authored
from fang.units import Quantity
from fang.values import Value


def test_a_transaction_commits_whole(kernel):
    before = len(kernel.head)
    transaction = Transaction(
        kernel.head.hash,
        (
            AddEntity(entity=Component(authored("CMP-NEW-1")), reason="add"),
            AddEntity(entity=Component(authored("CMP-NEW-2")), reason="add"),
        ),
    )
    proposal = kernel.apply(transaction)
    assert proposal.accepted
    assert len(kernel.head) == before + 2


def test_a_transaction_that_fails_partway_commits_nothing(kernel):
    before = len(kernel.head)
    transaction = Transaction(
        kernel.head.hash,
        (
            AddEntity(entity=Component(authored("CMP-NEW-1"))),
            RemoveEntity(target="CMP-DOES-NOT-EXIST"),
        ),
    )
    proposal = kernel.propose(transaction)
    assert proposal.rejected
    assert len(kernel.head) == before
    assert "CMP-NEW-1" not in kernel.head.entities


def test_a_stale_transaction_is_rejected_rather_than_applied_optimistically(kernel):
    stale_base = kernel.head.hash
    kernel.apply(Transaction(stale_base, (AddEntity(entity=Component(authored("CMP-A"))),)))

    proposal = kernel.propose(
        Transaction(stale_base, (AddEntity(entity=Component(authored("CMP-B"))),))
    )
    assert proposal.rejected
    assert proposal.diagnostics[0].code == "TXN-0001"
    assert "CMP-B" not in kernel.head.entities


def test_a_rejected_proposal_leaves_canonical_state_unchanged_and_still_explains(kernel, power_constraint):
    head_before = kernel.head.hash
    transaction = Transaction(
        kernel.head.hash,
        (
            AddEntity(entity=power_constraint),
            SetParameter(
                target=REGULATOR,
                name="power_dissipation",
                value=Value.explicit(Quantity.scalar("0.5", "W")),
                reason="raise dissipation past the limit",
                requirement_refs=("REQ-PWR-001",),
            ),
        ),
    )
    proposal = kernel.propose(transaction)

    assert proposal.rejected
    assert kernel.head.hash == head_before
    # The explanation is the useful output of a rejection.
    assert proposal.diagnostics
    assert len(proposal.diff) > 0
    assert any(d.code == "TXN-0002" for d in proposal.diagnostics)


def test_committing_a_rejected_proposal_is_refused(kernel):
    proposal = kernel.propose(
        Transaction("sha256:not-the-head", (AddEntity(entity=Component(authored("CMP-X"))),))
    )
    with pytest.raises(FangError):
        kernel.commit(proposal)


def test_an_operation_carries_its_reason_and_the_requirements_it_serves(kernel):
    operation = SetParameter(
        target=REGULATOR,
        name="power_dissipation",
        value=Value.explicit(Quantity.scalar("0.1", "W")),
        reason="Adjust feedback divider to target 3.3 V",
        requirement_refs=("REQ-PWR-001",),
    )
    rendered = operation.as_dict()
    assert rendered["op"] == "set_parameter"
    assert rendered["reason"]
    assert rendered["requirement_refs"] == ["REQ-PWR-001"]


def test_the_default_required_set_is_every_check_whose_scope_intersects(kernel, power_constraint):
    # The constraint check's scope covers the regulator, so it runs.
    transaction = Transaction(kernel.head.hash, (AddEntity(entity=power_constraint),))
    proposal = kernel.propose(transaction)
    assert proposal.accepted
    assert any(result.check == "constraint" for result in proposal.checks)


def test_a_policy_narrows_the_required_set(kernel, power_constraint):
    transaction = Transaction(kernel.head.hash, (AddEntity(entity=power_constraint),))
    proposal = kernel.propose(transaction, policy=Policy(required_checks=frozenset()))
    assert proposal.checks == ()


def test_an_undecided_result_blocks_only_where_the_policy_says_it_must(kernel):
    unknown_rule = Constraint(
        authored("RULE-UNKNOWN"),
        constraint_kind="max_power_dissipation",
        targets=(REGULATOR,),
        expression=le(Ref(REGULATOR, "unmeasured", WATTS), Literal.of(Quantity.scalar("1", "W"))),
        source="REQ-PWR-001",
    )
    transaction = Transaction(kernel.head.hash, (AddEntity(entity=unknown_rule),))

    permissive = kernel.propose(transaction)
    assert permissive.accepted
    assert any(r.status is CheckStatus.UNKNOWN for r in permissive.checks)

    strict = kernel.propose(
        transaction, policy=Policy(must_be_decided=frozenset({"REQ-PWR-001"}))
    )
    assert strict.rejected
    assert any(d.code == "TXN-0003" for d in strict.diagnostics)


def test_policy_approvals_gate_the_commit(kernel):
    transaction = Transaction(kernel.head.hash, (AddEntity(entity=Component(authored("CMP-Y"))),))
    blocked = kernel.propose(
        transaction, policy=Policy(approvals_required=frozenset({"safety-review"}))
    )
    assert blocked.rejected
    assert any(d.code == "TXN-0004" for d in blocked.diagnostics)

    granted = kernel.propose(
        transaction,
        policy=Policy(
            approvals_required=frozenset({"safety-review"}),
            approvals_granted=frozenset({"safety-review"}),
        ),
    )
    assert granted.accepted


def test_every_mutation_path_uses_the_same_gate(kernel, power_constraint):
    """A program edit, a human edit, and an agent proposal differ only in origin."""
    from fang.provenance import Actor, ActorKind, ProvenanceOrigin, ProvenanceRecord
    from conftest import FIXED_TIME

    def origin(kind, actor_id):
        return ProvenanceRecord(
            ProvenanceOrigin.GENERATED, "edit", Actor(kind, actor_id), "REV-1", FIXED_TIME
        )

    failing = SetParameter(
        target=REGULATOR,
        name="power_dissipation",
        value=Value.explicit(Quantity.scalar("0.5", "W")),
        reason="over the limit",
    )
    outcomes = []
    for kind, actor_id in (
        (ActorKind.TOOL, "fang"),
        (ActorKind.HUMAN, "engineer"),
        (ActorKind.MODEL, "agent"),
        (ActorKind.ADAPTER, "kicad-import"),
    ):
        proposal = kernel.propose(
            Transaction(
                kernel.head.hash,
                (AddEntity(entity=power_constraint), failing),
                origin=origin(kind, actor_id),
            )
        )
        outcomes.append(proposal.accepted)
    assert outcomes == [False, False, False, False]


def test_a_downstream_artifact_is_materialized_only_after_commit(kernel):
    uncommitted = Realization("kicad", "sha256:some-other-snapshot")
    with pytest.raises(FangError):
        materialize(uncommitted, kernel.head)

    realization = Realization("kicad", kernel.head.hash, tools=("kicad-export",))
    assert materialize(realization, kernel.head).endswith(b"\n")


def test_a_realizations_implied_change_returns_through_a_transaction(kernel):
    pin_swap = SetParameter(
        target=REGULATOR,
        name="pin_assignment",
        value=Value.explicit(Quantity.scalar("2", "1")),
        reason="pin swap chosen during layout",
    )
    realization = Realization("layout", kernel.head.hash, implied_changes=(pin_swap,))
    transaction = realization.to_transaction(kernel.head.hash)
    assert isinstance(transaction, Transaction)
    # The change reaches canonical state only through the gate.
    assert kernel.apply(transaction).accepted


def test_the_snapshot_records_its_producer(kernel):
    root = kernel.head.as_dict()
    assert root["schema_version"] == "1.2"
    assert root["compiler_version"]
    assert root["lock_id"]


def test_every_root_key_is_present_even_when_empty(kernel):
    from fang.entities import ROOT_COLLECTIONS, ROOT_MAPPINGS

    root = kernel.head.as_dict()
    for key in ROOT_COLLECTIONS + ROOT_MAPPINGS:
        assert key in root, key


def test_connect_is_a_structured_operation(kernel):
    connection = conductive("CN-1", "DOM-LOGIC", "NET-MOTOR-STAR")
    proposal = kernel.apply(
        Transaction(kernel.head.hash, (Connect(connection=connection, reason="bond"),))
    )
    assert proposal.accepted
    assert kernel.head.entities["CN-1"].connection_kind is ConnectionKind.GROUND
