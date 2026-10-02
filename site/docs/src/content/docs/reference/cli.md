---
title: CLI
description: Every fang command.
sidebar:
  order: 1
  attrs:
    data-icon: forward-slash
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
| `fang schematic` | Compile a KiCad schematic; render it with `--svg`, or have copperhead draft it |
| `fang sim` | Compile a simulation plan, lower it, run it |
| `fang verify` | Route and run every declared question; persist only with `--commit` |
| `fang emulate` | Run the firmware in Renode and print what each emulation question measured |
| `fang graph` | Summarize the kernel graph |
| `fang diff` | Diff a program against the persisted workspace |
| `fang mcp` | Serve the kernel to an agent over the Model Context Protocol, on stdio |

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
| `1` | The work failed: a rejected gate, a failed check, a missing model or a failed verification |
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

## Schematic

```bash
fang schematic board.py -o board.kicad_sch --svg board.svg
fang schematic board.py --drafter copperhead -o board.kicad_sch
```

| Option | Default | Does |
| --- | --- | --- |
| `-o`, `--output` | stdout | Where to write the `.kicad_sch` |
| `--svg` | none | Also render the sheet here, with `kicad-cli` |
| `--drafter` | `fang` | Who draws the sheet: `fang`, a grid joined by labels, or `copperhead`, placed and wired |

fang's own sheet needs no tool; `--svg` needs `kicad-cli`. A copperhead draft
needs `copperhead` and `kicad-cli`: the sheet is read back with KiCad and
returned only if its nets are exactly the design's, and refused, naming the
difference, otherwise. A part with no KiCad symbol, or a net left with fewer
than two drawn pins, is reported as a loss rather than dropped silently.

## Agent surface

```bash
fang mcp board.py
```

Serves the kernel over the Model Context Protocol on stdio, bound to the
project directory, with the agent's changes going through the same commit gate
as everything else. It needs the `mcp` extra, `pip install "copperhead-fang[mcp]"`,
and refuses with `MCP-0005` without it.

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

`fang sim` is the low-level command: it runs a deck and reports the run, and
nothing it finds reaches the graph. To answer a question and decide the
constraint over it, declare the question and use `fang verify`.

## Verification

```bash
fang verify board.py              # route and run every question
fang verify board.py --commit     # and persist the measurements
```

| Option | Default | Does |
| --- | --- | --- |
| `--commit` | off | Persist the new head into the existing workspace |

Each declared question is routed to the cheapest level that decides it and
printed with its level, its tool, its measurements and its result, or the
reason it did not run. A failed verification exits `1`, and so does a question
the program left unrunnable; a tool that is not installed is reported
unsupported, by name, and is not by itself a failure. A program with no
question says there is nothing to verify and exits `0`.

Without `--commit` nothing is written, not even a scratch deck. `--commit`
needs a workspace, so run `fang build` first. See
[Verification](/reference/verification/).

## Emulation

```bash
fang emulate board.py
fang emulate board.py -o bundles
fang emulate board.py --bundle-only -o bundles
```

| Option | Does |
| --- | --- |
| `-o`, `--output` | Write each question's bundle into a folder of its own here |
| `--bundle-only` | Write the bundles and run nothing |

`fang emulate` is the low-level command, as `fang sim` is for SPICE: it prints
what each measure read and takes nothing through the gate, and it changes no
workspace. `fang verify` answers emulation questions with every other kind and
takes the measurements back through the gate. Without Renode 1.17.0 on the
path, each question is reported unsupported and nothing is fabricated. See
[Emulation](/reference/emulation/).
