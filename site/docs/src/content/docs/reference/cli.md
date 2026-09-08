---
title: CLI
description: Every fang command.
sidebar:
  order: 1
---

Every command exits non-zero when the work it names did not succeed, so a build
script can rely on the exit code rather than parsing output.

| Command | Does |
| --- | --- |
| `fang init` | Create a `.copperhead/` workspace |
| `fang build` | Elaborate, pass the gate, persist, run the tool plan |
| `fang check` | Run the constraint, topology and compatibility checks |
| `fang netlist` | Print the compiled components and nets |
| `fang export` | Write a KiCad netlist |
| `fang view` | Compile a view; render it to SVG with `-o` |
| `fang sim` | Compile a simulation plan, lower it, run it |
| `fang graph` | Summarize the kernel graph |
| `fang diff` | Diff a program against the persisted workspace |

Shared options: `--project` sets the project identifier, `--system` picks a
system when a file defines several, and `-C` sets the project directory.

## Views

```bash
fang view --list
fang view board.py ground -o ground.svg
```

The six views are `system`, `interconnect`, `power`, `ground`, `interfaces` and
`safety`. Each answers one engineering question, is generated only from facts in
the graph, and reports its own incompleteness rather than hiding it — a node
carrying unknown parameters is drawn with a dashed border.

## Simulation

```bash
fang sim board.py --analysis transient --stop 10ms --probe "V(1)" -o deck.cir
```

If a selected component has no compatible model and is not explicitly
abstracted, the plan is **rejected with the reason** rather than run with a
substitute. If ngspice is not installed, the plan still compiles and the command
says no run was made.
