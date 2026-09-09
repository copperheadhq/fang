---
title: Three phases
description: Why elaboration, operation and commit happen in that order.
sidebar:
  order: 1
  attrs:
    data-icon: clock
---

Elaboration, operation and commit run in that order because a program that could
observe a tool's result would not be reproducible.

## Elaboration

Your program runs in a sandbox with no network access and only declared, hashed
file inputs. It builds a graph and a tool plan, calling no engine and touching
no geometry.

The prohibition on network access is absolute rather than a default, because a
declared exception would cost the reproducibility guarantee it exists to give.
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

One gate, six conditions and the same path for a human edit, a re-elaboration, a
CAD import and an agent proposal. They differ only in the provenance they
record.

A rejected proposal leaves canonical state untouched and still returns its
diagnostics and its diff.

Downstream artifacts are written only after commit, and external checks run then
and re-enter as evidence.
