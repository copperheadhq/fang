---
title: One canonical model
description: The governing invariant and what it costs to hold.
sidebar:
  order: 2
  attrs:
    data-icon: database
---

There is exactly one canonical model: the Engineering Intermediate
Representation. The kernel graph is its live realization. Everything else is a
**lowering** of it, a **projection** of it or an **interchange encoding** of it.
That covers a netlist, a view, a SPICE deck and a KiCad file alike.

No feature may introduce a second persisted representation of the same facts.

## Why it is stated as a prohibition

Most hardware toolchains fail in the same place. The schematic knows one thing,
the BOM knows another and the simulation deck knows a third, and each was true
when it was written. Reconciliation becomes the work. The invariant exists so
that reconciliation is not a task anyone can be assigned, because there is
nothing to reconcile.

The cost is real. A downstream tool that wants its own store cannot have one. It
gets a generated `Projection` and recomputes. That is slower, and that is the
point: a cache that can go stale is a second representation wearing a different
hat.

## How it is enforced

`ConstraintRegistry` enforces it literally. Constructing a second registry for a
project raises [`ELAB-0012`](/reference/diagnostics/):

```python
ConstraintRegistry(project)   # fine
ConstraintRegistry(project)   # ELAB-0012: a second constraint registry was created
```

There is no flag to allow it.

## What the model holds

Sixteen entity kinds, each a frozen dataclass carrying identity, parameters,
provenance and a source location:

| Group | Kinds |
| --- | --- |
| Structure | `Component`, `Net`, `Rail`, `Connection`, `Domain` |
| Interfaces | `Interface`, `Port`, `Bus`, `Pin` |
| Rationale | `Requirement`, `Decision`, `Evidence`, `Calculation`, `Verification`, `Assumption` |
| Analysis | `Model` |

Every entity answers two questions. `references()` drives referential integrity,
diff impact and topology adjacency. `as_dict()` drives canonical serialization.
A new entity kind that does not answer both cannot participate in the graph.

## Identity

An identifier is a UUIDv5 over `(project namespace, "<kind>:<canonical semantic
path>")`, rendered as a prefix plus twelve hex digits. Two consequences matter
in practice.

**Re-derivation is stable.** The same design gives the same identifiers, in this
process or another one. Identifiers are not allocated from a counter, so there
is no allocation order to preserve.

**Collisions lengthen rather than renumber.** An identifier is extended four
digits at a time, only against the identifiers already in that revision, so
lengthening is itself reproducible.

Three origins exist and are distinguished: `derive()` for a fact the kernel
computed, `authored()` for one a person wrote and `imported()` for one that came
from CAD.

## Determinism

Identical inputs give byte-identical snapshots. This is verified across
processes with differing `PYTHONHASHSEED`, not merely within one run.

Two rules make that hold. Magnitudes are `Decimal` strings under a fixed
`Context(prec=34)`, never binary floats, so no value depends on rounding mode.
And canonical serialization sorts by Unicode code point, except for the
collections in `serialization.ORDERED_COLLECTIONS`, whose order carries meaning
and is preserved rather than sorted.
