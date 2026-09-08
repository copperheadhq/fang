---
title: Diagnostics
description: Every code fang emits, by area.
sidebar:
  order: 8
  attrs:
    data-icon: warning
---

Diagnostic codes are stable. They are **allocated, never reused and retired
rather than deleted**, so a code in an old log means today what it meant then,
and searching for one never lands on a different problem.

Seven areas exist: `ELAB`, `IFACE`, `TOPO`, `UNIT`, `TXN`, `SIM`, `IMPORT`.

## UNIT: units and dimensions

| Code | Means |
| --- | --- |
| `UNIT-0001` | Operands of unequal dimension combined |
| `UNIT-0002` | Unit symbol not recognized |
| `UNIT-0003` | Exponent is not a dimensionless rational |
| `UNIT-0004` | Unit conversion rounded |

`UNIT-0001` is raised where the expression is **constructed**, not where it is
evaluated. A dimensionally invalid expression cannot be stored.

## ELAB: elaboration and structure

| Code | Means |
| --- | --- |
| `ELAB-0001` | Canonical semantic path is not well formed |
| `ELAB-0002` | Two entities share a canonical semantic path |
| `ELAB-0003` | Identifier is not unique within the revision |
| `ELAB-0004` | Entity traceable to neither a source location nor an import |
| `ELAB-0005` | Connection has no kind |
| `ELAB-0006` | Required reference names no entity |
| `ELAB-0007` | Requirement state transition outside the permitted table |
| `ELAB-0008` | Tool handle read during elaboration |
| `ELAB-0009` | Artifact declares an unimplemented major schema version |
| `ELAB-0010` | Cycle where one is prohibited |
| `ELAB-0011` | Contradictory mandatory constraints |
| `ELAB-0012` | A second constraint registry was created |

`ELAB-0012` is the [governing invariant](/concepts/one-canonical-model/) as an
error code. There is no flag that permits it.

`ELAB-0008` is the [three-phase rule](/concepts/three-phases/) as an error code:
a program that could observe a tool's result would not be reproducible.

## IFACE: interfaces

| Code | Means |
| --- | --- |
| `IFACE-0001` | A required interface signal has no pin |
| `IFACE-0002` | Two interfaces disagree on membership |

An optional signal with no pin is not an error. `IFACE-0001` is about signals
the interface says it requires.

## TXN: transactions and the gate

| Code | Means |
| --- | --- |
| `TXN-0001` | Transaction proposed against a snapshot that is no longer current |
| `TXN-0002` | A required check reported a blocking severity |
| `TXN-0003` | An undecided result covers a must-be-decided requirement |
| `TXN-0004` | Policy approval requirements unsatisfied |
| `TXN-0005` | Operation did not normalize into a well-formed entity |

These are the [gate conditions](/concepts/the-commit-gate/). A rejection carries
its code, its message and the diff it would have applied.

## IMPORT: CAD interchange

| Code | Means |
| --- | --- |
| `IMPORT-0001` | Adapter could not represent a construct |

Reported in `import-report.json` rather than raised, because an import that
stopped at the first unrepresentable construct would be less useful than one
that says what it could not carry.

## Adding a code

New codes are allocated through `_allocate` at the bottom of the relevant area
block in `fang/diagnostics.py`. Never renumber and never reuse a retired
number.
