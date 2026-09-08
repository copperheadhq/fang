# Typed Interfaces And Pin Lowering

## Why

System-level authoring operates on typed interfaces, and pin assignment is a
lowering result rather than an authoring input. Today the language has only
single-signal surfaces: an engineer cannot write `controller.i2c >> imu.i2c`,
and nothing decides which pin carries which signal.

This stage delivers the interface catalogue, the deterministic lowering to pins,
and the compatibility checks — the three things that make late pin assignment,
part substitution, and honest compatibility reporting tractable.

## What Changes

- Add `fang.interfaces`: the interface type model, the shipped catalogue, the
  multi-signal `InterfacePort` surface, and `Pin` / `PinMap` on parts.
- Add `fang.lowering`: deterministic interface-to-pin lowering, with a decision
  recorded where a choice existed and an explicit failure where none can be made.
- Add `fang.compatibility`: the compatibility check class, returning undecided
  and naming the missing input rather than passing by default.
- Extend elaboration to emit interface entities, ports, pins, and the lowered
  pin connections carrying provenance back to the interface connection.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `fang-kernel` — adds the interface catalogue's concrete membership, the pin
  model, the lowering algorithm's determinism and failure behaviour, and the
  compatibility check's inputs.

## Impact

- Existing single-signal surfaces (`Power`, `Ground`, `Electrical`, `Signal`)
  become interface types in the same catalogue, so nothing written against
  stage 2 breaks.
