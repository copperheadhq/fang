---
title: Welcome
description: The language and kernel under copperhead.
sidebar:
  order: 0
---

Fang is a Python-embedded language for circuit boards and the typed kernel that
holds what you write. You author intent. The kernel decides what is true about
it and refuses what it cannot justify.

It is the layer under [copperhead](https://copperhead.sh). Copperhead is the
agent you talk to. Fang is what it writes and what checks the writing.

## Start here

- [Introduction](/start/introduction/): what fang is and what it refuses to do
- [Installation](/start/installation/): install it and build your first board
- [Examples](/start/examples/): eight programs, smallest first

## Concepts

- [Three phases](/concepts/three-phases/): elaboration, operation and commit
- [One canonical model](/concepts/one-canonical-model/): the governing invariant
- [Values and undecided](/concepts/values-and-undecided/): the third truth value
- [The commit gate](/concepts/the-commit-gate/): six conditions, one path in
- [Interfaces and lowering](/concepts/interfaces-and-lowering/): connections to pins
- [Rationale](/concepts/rationale/): keeping the reasoning in the graph

## Reference

- [CLI](/reference/cli/): every command, option and exit code
- [Language](/reference/language/): the authoring surface
- [Interfaces](/reference/interfaces/): the catalogue
- [Parts](/reference/parts/): the standard library
- [Views](/reference/views/): the six required views
- [Simulation](/reference/simulation/): plans, lowering and backends
- [Workspace](/reference/workspace/): what `.copperhead/` holds
- [Diagnostics](/reference/diagnostics/): every code fang emits

The normative document is the
[spec](https://github.com/copperheadhq/fang/blob/main/openspec/specs/fang-kernel/spec.md).
Where these pages and the spec disagree, the spec is right and this is a bug.
