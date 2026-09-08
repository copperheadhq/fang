# The View Compiler

## Why

A schematic is one view among many, and the toolchain currently has none. An
engineer cannot see the ground topology, the power tree, or the interconnect
without reading the graph by hand — and a diagram drawn by hand is exactly the
"attractive diagram over incomplete data" the standard warns against.

This stage delivers views as deterministic projections of graph state.

## What Changes

- Add `fang.views`: the view specification, the view graph, and the compiler
  that projects a snapshot into one.
- Add the six required views: system, interconnect, power, ground, interfaces,
  and safety.
- Add the layout boundary: a request carrying only layout information, a
  deterministic layered layout behind it, and a positioned view graph back.
- Add the SVG renderer and stable placement seeds.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `fang-kernel` — adds the view specification's shape, the required views'
  membership, and the layout boundary's contract.

## Impact

- Views are generated only from facts in the graph, and expose the completeness
  of what they show rather than hiding it.
