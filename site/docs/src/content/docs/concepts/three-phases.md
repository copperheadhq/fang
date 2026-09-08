---
title: Three phases
description: Why elaboration, operation and commit happen in that order.
sidebar:
  order: 1
---

The order is the whole point. A program that could observe a tool's result would
not be reproducible, so it never can.

## Elaboration

Your program runs in a sandbox with no network access and only declared, hashed
file inputs. It builds a graph and a tool plan. It calls no engine and touches
no geometry.

The prohibition on network access is absolute rather than a default. A declared
exception would cost exactly the reproducibility guarantee it exists to give.
External data reaches a program as a declared, hashed file produced by an
earlier tool call.

A tool call returns a **handle**, not a result. Reading one during elaboration
is an error, whether you convert it to a boolean, branch on it or compare it.

```python
def architecture(self):
    layout = tools.layout(placers=["pyplacer"], routers=["freerouting"])
    report = tools.check(profile="jlcpcb-2layer")
    tools.export(layout=layout, format="kicad", require=report.passed)
```

`report.passed` is a symbolic condition recorded in the plan and resolved later.

## Operation

The recorded plan runs against immutable snapshots. Placers, routers, checkers
and simulators are reached across a process boundary and produce candidate
realizations. Nothing here mutates canonical state.

A call whose condition resolves false is **skipped**, and the skip is recorded
along with the condition that caused it.

## Commit

One gate, six conditions and the same path for a human edit, a re-elaboration,
a CAD import and an agent proposal. They differ in their recorded provenance and
in nothing else.

A rejected proposal leaves canonical state untouched and still returns its
diagnostics and its diff. The explanation is the useful output of a rejection.

Only after commit are downstream artifacts written, and only then do external
checks run and re-enter as evidence.
