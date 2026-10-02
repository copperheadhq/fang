---
title: Diagnostics
description: Every code fang emits, by area.
sidebar:
  order: 10
  attrs:
    data-icon: warning
---

Diagnostic codes are stable. They are **allocated, never reused and retired
rather than deleted**, so a code in an old log means today what it meant then,
and searching for one never lands on a different problem.

Eight areas exist: `ELAB`, `IFACE`, `TOPO`, `UNIT`, `TXN`, `SIM`, `IMPORT`, `MCP`.

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
| `IFACE-0003` | A pin selector cites no evidence the part declares |
| `IFACE-0004` | An address strap names a pin the part does not have |

An optional signal with no pin is not an error. `IFACE-0001` is about signals
the interface says it requires.

`IFACE-0003` refuses a `PinMap` whose [selectors](/reference/interfaces/#peripheral-instances-and-selectors)
name no `Cites` declaration on the same part. An address given as a bare
number is `UNIT-0001`, as any bare-number parameter is. A strap that resolves
to no address is not a diagnostic at all: the board is legal, and the
compatibility check reports the address as undecided.

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

## SIM: simulation and verification

| Code | Means |
| --- | --- |
| `SIM-0001` | A question measures into a parameter its module does not declare |
| `SIM-0002` | A question states its own result |
| `SIM-0003` | A question names a surface or part that resolves to no pins |
| `SIM-0004` | A circuit question names no bench |
| `SIM-0005` | A load is neither a current nor a resistance |
| `SIM-0006` | A model port the part's pin map does not reach |
| `SIM-0007` | A frequency outside a model's range |
| `SIM-0008` | A rule-check exclusion gives no reason |
| `SIM-0009` | An emulation model names a descriptor fang does not ship |
| `SIM-0010` | A component an emulation touches has neither a model nor an abstraction |
| `SIM-0011` | A fault the device's emulation model does not support |
| `SIM-0012` | A stimulus names an input its model lacks, or a value of the wrong dimension |
| `SIM-0013` | A pin the emulation platform does not map |
| `SIM-0014` | An emulation names no run duration |
| `SIM-0015` | No firmware is bound, or it was built for another target |
| `SIM-0016` | A bus device's controller or address cannot be resolved |

`SIM-0001`, `SIM-0002`, `SIM-0003`, `SIM-0005` and `SIM-0008` fail where the
question is written or elaborated. The others are a question
[`fang verify`](/reference/verification/) reports as not runnable, naming what
is missing, rather than running it with something assumed in its place.
`SIM-0009` to `SIM-0016` are an emulation plan refused before anything runs;
[Emulation](/reference/emulation/) has the detail.

## IMPORT: CAD interchange

| Code | Means |
| --- | --- |
| `IMPORT-0001` | Adapter could not represent a construct |

Reported in `import-report.json` rather than raised, because an import that
stopped at the first unrepresentable construct would be less useful than one
that says what it could not carry.

## MCP: the agent surface

| Code | Means |
| --- | --- |
| `MCP-0001` | A path outside the bound project root was named |
| `MCP-0002` | No tool by that name is exposed |
| `MCP-0003` | An argument did not parse |
| `MCP-0004` | Commit named a proposal the gate did not accept |
| `MCP-0005` | The protocol dependency is not installed |
| `MCP-0006` | The operation kind is not one the commit gate evaluates |

A refusal at the protocol boundary is its own area: it describes the boundary,
not the transaction the boundary was asked about.

## Adding a code

New codes are allocated through `_allocate` at the bottom of the relevant area
block in `fang/diagnostics.py`. Never renumber and never reuse a retired
number.
