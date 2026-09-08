# The Part Model And Standard Library

## Why

A design is written out of parts, and nothing in the toolchain yet is one. The
language can declare a `Part`, but every project would have to spell out its own
resistor, its own capacitor, and its own two-pin lowering — which means every
project would spell them out differently, and the netlist compiler would have
nothing stable to compile.

This stage delivers the part model: designators, packages, footprints, sourcing,
and a standard library of the generic parts a board is actually made of.

## What Changes

- Add `fang.parts`: `TwoPin` and the generic passives (resistor, capacitor,
  inductor, diode, LED, fuse, crystal), active parts (transistor, regulator,
  connector, test point, mounting hole), and their pins and pin maps.
- Give every part a designator prefix and package/footprint declaration.
- Add part-level traits for footprint, sourcing, and datasheet evidence.
- Record the package as a first-class part attribute so the netlist and CAD
  stages have something to emit.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `fang-kernel` — adds the part model: designator prefixes, package
  declaration, the standard library's membership, and the rule that a generic
  part carries no vendor identity until one is selected.

## Impact

- New `fang/parts.py`; no change to existing modules beyond the unified
  lowering already in place.
