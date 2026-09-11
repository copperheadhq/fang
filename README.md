<picture>
  <source media="(prefers-color-scheme: dark)"
          srcset="https://raw.githubusercontent.com/copperheadhq/fang/main/site/brand/lockup-outlined.svg">
  <img src="https://raw.githubusercontent.com/copperheadhq/fang/main/site/brand/lockup-outlined-light.svg"
       alt="fang" width="150" height="53">
</picture>

**Hardware as Code.** The language and kernel under [copperhead](https://copperhead.sh).

A code-defined electronics toolchain: a Python-embedded language for authoring
hardware, a typed kernel that holds the design and compilers that lower it into
netlists, views, simulation decks and CAD.

```python
from fang.interfaces import I2CPort, Pin, PinMap
from fang.lang import Part, System, V, kOhm, require
from fang.parts import Regulator


class MCU(Part):
    i2c = I2CPort(voh_min=2.4 * V, voltage=3.3 * V, pull_up_resistance=4.7 * kOhm)
    PB8 = Pin("PB8", role="clock")
    PB6 = Pin("PB6", role="clock")      # two candidates: choosing is a decision
    PB9 = Pin("PB9", role="data")
    PB7 = Pin("PB7", role="data")
    pinmap = PinMap({"i2c.scl": ["PB8", "PB6"], "i2c.sda": ["PB9", "PB7"]})


class IMU(Part):
    i2c = I2CPort(vih_min=2.0 * V, voltage=3.3 * V)
    SCL = Pin("SCL", role="clock")
    SDA = Pin("SDA", role="data")
    pinmap = PinMap({"i2c.scl": "SCL", "i2c.sda": "SDA"})


class SensorBoard(System):
    regulator = Regulator(output_voltage=3.3 * V, package="SOT-23-5")
    mcu = MCU(package="LQFP-64")
    imu = IMU(package="LGA-14")

    def architecture(self):
        self.mcu.i2c >> self.imu.i2c        # lowers to PB8→SCL and PB9→SDA,
                                            # recording why PB6 and PB7 lost
    def constraints(self):
        require(self.regulator.output_voltage == 3.3 * V)
```

The full version is [examples/sensor_board/](https://github.com/copperheadhq/fang/tree/main/examples/sensor_board/).

```bash
fang build   board.py     # elaborate, gate, persist, run the plan
fang check   board.py     # constraints, topology, interface compatibility
fang netlist board.py     # components and nets
fang export  board.py -o board.net   # a KiCad netlist
fang view    board.py ground -o ground.svg
fang sim     board.py --analysis transient --probe "V(1)"
fang mcp     board.py     # serve the agent surface over stdio
```

## What it does

| Stage | Capability |
| --- | --- |
| Kernel | Entity model, stable identity, units, values, constraints, transactions, the commit gate, canonical serialization, semantic diff, topology intent |
| Language | `Module`, `System`, `Part`, parameters with units, traits, `require()`, the connect operator, deterministic sandboxed elaboration |
| Interfaces | A catalogue of 17 typed interfaces, ports, buses, deterministic pin lowering, compatibility checks |
| Parts | Designators, packages, footprints, sourcing and a standard library of generic parts |
| Netlist | Net inference, designator assignment, KiCad netlist emission |
| CAD | KiCad s-expression reading, project import, the mapping table, loss reporting, one safe round trip |
| Tool plan | Handles as symbolic conditions, the tool contract, the operation phase, realizations |
| Views | Six required views, the layout boundary, SVG rendering, placement seeds |
| Simulation | Models as traits, explicit plans, SPICE lowering, the ngspice backend, normalized results |
| Rationale | Requirements, assumptions, decisions, evidence, calculations, the verification graph, impact propagation |
| CLI | The `.copperhead/` workspace, the manifest and the commands above |

## The specification

The contract is one document:
[openspec/specs/fang-kernel/spec.md](https://github.com/copperheadhq/fang/blob/main/openspec/specs/fang-kernel/spec.md).
It is self-contained and normative, covering the terminology, the design principles, the
layers of representation, the kernel architecture and the project root, followed
by 81 requirements over 217 scenarios covering the Engineering Intermediate
Representation (identity, quantities, constraints, provenance, serialization,
diff) and the kernel and language over it, with all 23 acceptance criteria.
RFC 2119 keywords in it are normative.

Delivery is staged in
[openspec/ROADMAP.md](https://github.com/copperheadhq/fang/blob/main/openspec/ROADMAP.md)
and managed with [OpenSpec](https://github.com/Fission-AI/OpenSpec).

## The package

```
fang/
  units.py          dimensions, unit algebra, decimal quantities
  values.py         value status, explicit unknowns, conflicting candidates
  identity.py       canonical semantic paths, UUIDv5 derivation, transliteration
  entities.py       the EIR entity model and the project root
  provenance.py     append-only provenance records
  constraints.py    the single registry, typed expressions, three-valued logic
  topology.py       topology intent and conductive-path enumeration
  serialization.py  canonical JSON and the canonical record stream
  validation.py     structural validation and the requirement state machine
  graph.py          snapshots, transactions, the proposal sandbox, the commit gate
  diff.py           semantic diff classification
  queries.py        rationale queries and on-demand graph analysis
  diagnostics.py    namespaced diagnostic codes and the code registry
  lang.py           the authoring surface
  sandbox.py        enforced network denial and declared, hashed inputs
  elaborate.py      program to snapshot and tool plan
  interfaces.py     the interface catalogue and the pin model
  lowering.py       deterministic interface-to-pin lowering
  compatibility.py  interface compatibility checking
  parts.py          the standard part library
  netlist.py        net inference and the netlist IR
  kicad.py          KiCad emission and import
  sexpr.py          the s-expression reader
  importing.py      the mapping table and the loss report
  toolplan.py       plan emission and handles
  runtime.py        the operation phase and the built-in tools
  views.py          the view compiler and the six required views
  layout.py         the layout boundary
  render.py         SVG rendering
  simulation.py     plans, SPICE lowering, backends, normalized results
  rationale.py      requirements, decisions, evidence, calculations, coverage
  workspace.py      the .copperhead/ workspace and its manifest
  cli.py            the fang command line
```

## Install

```bash
pip install copperhead-fang               # the toolchain and the `fang` command
pip install "copperhead-fang[analysis]"   # add NetworkX for the graph queries
pip install "copperhead-fang[mcp]"       # add the agent surface, `fang mcp`
```

The distribution is named `copperhead-fang`; the import name is `fang`.

To work on it:

```bash
git clone https://github.com/copperheadhq/fang
cd fang
pip install -e ".[dev,analysis,mcp]"
python -m pytest
```

Pure Python 3.11+, and the core install has no dependencies at all. Three things
are optional and none is required: NetworkX, an extra used for graph *analysis*;
the MCP SDK, the extra behind `fang mcp`; and ngspice, an external simulator
reached across a process boundary. When any of them is absent the toolchain says
so rather than substituting anything.

## Invariants the tests hold

- **One canonical model.** No second persisted representation of the same facts.
- **Determinism.** Identical inputs give byte-identical snapshots, verified
  across processes with differing hash seeds.
- **Explicit unknowns.** `null` never means "unknown", and an unknown operand
  makes a check undecided rather than passing.
- **Undecided is a third truth value.** Never silently a pass, never silently a
  failure; whether it blocks is the gate's decision.
- **Transactional mutation.** Every path, whether program, human, agent or import,
  passes the same gate, differing only in recorded provenance.
- **Dimensional rejection at write time.** A dimensionally invalid expression
  cannot be stored, let alone evaluated.
- **Nothing invented.** A missing model, an absent simulator, an unmodelled CAD
  construct and an uncited claim are each reported as what they are.

## Tests

```bash
python -m pytest          # 553 tests; 551 pass here, the rest skip by name
python -m pytest -rs      # names each environment-dependent skip
```

The suite includes one test per acceptance criterion (AT-R1 to AT-R13 and AT-K1
to AT-K10). **All 23 pass.** The only skips name what is missing: the NetworkX
and MCP extras, and the ngspice binary.

## Examples

Each example is a folder: the program, a document explaining it and the files
`fang` produces from it under `out/`: the KiCad netlist, the check and graph
listings, the views and the rationale where there is any. Each one builds,
checks and exports; the suite rebuilds the committed outputs and compares them
in [tests/test_examples.py](https://github.com/copperheadhq/fang/blob/main/tests/test_examples.py).

- [examples/divider/](https://github.com/copperheadhq/fang/tree/main/examples/divider/): a voltage divider with a filter cap
- [examples/blinky/](https://github.com/copperheadhq/fang/tree/main/examples/blinky/): an MCU pin, a resistor
  and an LED, showing the shape of a program with nothing else in the way
- [examples/equations/](https://github.com/copperheadhq/fang/tree/main/examples/equations/): a divider written as the ratio it
  must satisfy, reused by inheritance with different values
- [examples/i2c_bus/](https://github.com/copperheadhq/fang/tree/main/examples/i2c_bus/): one controller and three targets on a
  multi-drop bus, with address uniqueness as a constraint and one device whose
  thresholds are an assumption rather than a number
- [examples/sensor_board/](https://github.com/copperheadhq/fang/tree/main/examples/sensor_board/): a regulated board with an
  MCU and an I2C sensor, showing pin lowering and recorded decisions
- [examples/usb_uart_bridge/](https://github.com/copperheadhq/fang/tree/main/examples/usb_uart_bridge/): USB to serial, with
  chosen vendor parts, a crystal and a UART crossover named wire by wire
- [examples/buck_regulator/](https://github.com/copperheadhq/fang/tree/main/examples/buck_regulator/): 12 V to 3.3 V, with the
  requirement, the part decision, the datasheet citations, the two calculations
  and the verification in the same graph as the inductor
- [examples/servo_drive/](https://github.com/copperheadhq/fang/tree/main/examples/servo_drive/): three half-bridges, CAN and a
  quadrature encoder, from one block declaration instantiated three times
- [examples/imported/](https://github.com/copperheadhq/fang/tree/main/examples/imported/): a KiCad
  netlist the import path reads
- [examples/parity/](https://github.com/copperheadhq/fang/tree/main/examples/parity/): the divider and
  blinky built again in atopile, so the two toolchains' components and nets can be
  asserted equal

## Brand

fang is a sub-brand of [copperhead](https://copperhead.sh) rather than a
separate identity, and the name is literal: copperhead is the snake, fang is the
fang. The mark is a trace with a fang hanging from it, drawn on the same
32-unit grid and in the same copper as copperhead's via mark. The wordmark is
lowercase, always, and set in IBM Plex Mono because it names a language.

[site/BRAND.md](https://github.com/copperheadhq/fang/blob/main/site/BRAND.md) is
the identity in full — the mark's geometry and clear space, the palette in both
themes with the two values nudged for contrast and the reason recorded, the type
and the voice. The assets are in
[site/brand/](https://github.com/copperheadhq/fang/tree/main/site/brand/), and
the page they dress is [fang.copperhead.sh](https://fang.copperhead.sh).

## License

Licensed under the [Apache License, Version 2.0](https://github.com/copperheadhq/fang/blob/main/LICENSE).
