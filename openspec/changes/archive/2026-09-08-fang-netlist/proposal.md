# Net Inference And Netlist Emission

## Why

The graph holds pins and the connections between them, but a board house, a
simulator, and KiCad all want nets: the equivalence classes those connections
form, with stable names and stable designators. Nothing in the toolchain yet
turns one into the other, so a Fang program cannot become anything a person can
open.

This stage closes the loop from a program to a KiCad netlist.

## What Changes

- Add `fang.netlist`: net inference by equivalence over pin connections,
  deterministic designator assignment, and the netlist IR.
- Add `fang.kicad`: the KiCad netlist emitter, written through the canonical
  s-expression writer.
- Record inferred nets as net entities in the graph, with provenance naming the
  connections they were inferred from.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `fang-kernel` — adds net inference, designator assignment, and the netlist
  projection's rules.

## Impact

- A netlist is a projection: it names the snapshot it was compiled from and is
  never a place engineering facts are first recorded.
