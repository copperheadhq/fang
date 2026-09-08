---
title: The commit gate
description: The six conditions every change passes, and why a rejection helps.
sidebar:
  order: 4
---

Nothing enters canonical state except through the gate. A human edit, a
re-elaboration, a CAD import and an agent proposal take the same path and differ
only in the provenance they record.

That is the point of having one. A second way in would be a second set of rules,
and the second set is always the one that is weaker.

## A transaction names its base

```python
proposal = graph.propose(transaction)
if proposal.accepted:
    graph.commit(proposal)
```

A `Transaction` names the snapshot it was built against and carries `Operation`s:
`AddEntity`, `RemoveEntity`, `Connect` and `SetParameter`. Naming the base is
what makes concurrent proposals safe. A transaction built against stale state is
rejected rather than merged on hope.

## The six conditions

`propose()` applies the transaction **to a copy** and runs, in order:

1. **Stale base.** The transaction's base is the committed head, or
   [`TXN-0001`](/reference/diagnostics/).
2. **Normalization.** Every operation produces a well-formed entity, or
   `TXN-0005`.
3. **Structural validation.** Identifier uniqueness, referential integrity,
   provenance traceability, prohibited cycles, contradictory mandatory
   constraints and the requirement state machine.
4. **Required checks have run.** Every `CheckClass` the policy requires has
   actually produced a result. Absent a project policy, the required set is
   structural validation plus every check class whose scope intersects the
   affected entities. A check class is therefore defined by what it covers as
   much as by what it evaluates.
5. **No blocking result.** No check reported a blocking severity, or `TXN-0002`.
6. **No undecided over a must-be-decided requirement**, or `TXN-0003`; and
   policy approvals are satisfied, or `TXN-0004`.

Only `commit()` advances the head. Rejection is correct by construction: the
candidate copy is discarded, and canonical state was never touched.

## The shipped check classes

| Check class | Evaluates |
| --- | --- |
| `constraint` | Every constraint in the registry, over interval arithmetic |
| `topology` | Topology intent, by enumerating conductive paths |
| `interface_compatibility` | Every typed link in the graph |

Structural validation is not in this list because the gate runs it regardless. A
policy can narrow or widen the required set. It cannot remove the structural
check.

## A rejection returns its reasoning

A rejected `Proposal` still carries its diagnostics **and its diff**. The
explanation is the useful output of a rejection. Saying no without the reason
would make the gate an obstacle rather than a tool.

## Two ordering rules

These are encoded in the gate and new code must not invert them.

`materialize()` refuses a `Realization` whose parent is not the committed
snapshot. A result computed against a graph that no longer exists describes a
design nobody has.

`ingest_external_results()` refuses results produced against anything but the
committed head. External check results re-enter as `Evidence`, through an
ordinary transaction, through the same gate as everything else.
