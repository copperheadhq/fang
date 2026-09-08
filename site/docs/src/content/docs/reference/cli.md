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

## Options

Every command that reads a program takes the same four:

| Option | Default | Does |
| --- | --- | --- |
| `program` | required | The Fang program to elaborate |
| `--system` | first found | Which system, when a file defines several |
| `--project` | `PRJ-LOCAL` | The project identifier |
| `-C`, `--directory` | `.` | The project directory |

`--project` is the namespace identifiers are derived in, so changing it changes
every identifier in the design. It is not a label.

`fang init` takes only `-C`. `fang --version` reports the version.

## Exit codes

| Code | Means |
| --- | --- |
| `0` | The work succeeded |
| `1` | The work failed: a rejected gate, a failed check or a missing model |
| `2` | Usage error |

A rejected commit is exit `1`, and the diagnostics that explain it go to output.
The rejection is the answer, not a crash.

## Views

```bash
fang view --list
fang view board.py ground -o ground.svg
```

The six views are `system`, `interconnect`, `power`, `ground`, `interfaces` and
`safety`. `interconnect` is the default when none is named.

Each answers one engineering question and is generated only from facts in the
graph. Each also reports its own incompleteness rather than hiding it: a node
carrying unknown parameters is drawn with a dashed border.

## Simulation

```bash
fang sim board.py --analysis transient --stop 10ms --step 1us --probe "V(1)"
fang sim board.py -o deck.cir
```

| Option | Default |
| --- | --- |
| `--analysis` | `op` (or `transient`) |
| `--backend` | `ngspice` |
| `--stop` | `1ms` |
| `--step` | `1us` |
| `--probe` | none; repeatable |
| `-o`, `--output` | write the SPICE deck here |

If a selected component has no compatible model and is not explicitly
abstracted, the plan is **rejected with the reason** rather than run with a
substitute. If ngspice is not installed, the plan still compiles and the command
says no run was made.
