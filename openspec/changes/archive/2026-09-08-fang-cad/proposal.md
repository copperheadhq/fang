# CAD Import And Round Trip

## Why

The toolchain writes to KiCad but cannot read from it. That makes it useless on
every board that already exists — which is most of them — and it means the
generated file is a one-way export rather than a round trip anyone can trust.

This stage makes the adapter bidirectional and makes its losses visible.

## What Changes

- Add `fang.sexpr`: a reader for the s-expression form KiCad writes.
- Add `fang.importing`: the external-identifier mapping table and the import
  report that names every construct an adapter could not represent.
- Extend `fang.kicad` with a netlist reader producing imported entities.
- Add the round trip: import a file, change one thing through a transaction,
  emit it again, with no unrelated change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `fang-kernel` — adds the import path's identity rules, the mapping table's
  shape, the loss report, and the round-trip guarantee.

## Impact

- An imported project is usable even though it was authored entirely outside
  Fang; what could not be recovered is represented as unknown, never invented.
