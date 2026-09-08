# Fang Language Surface

## Why

The kernel holds a graph but nothing writes one. Every requirement in the
combined spec that begins "a Fang program" is currently unreachable, and the
toolchain has no authoring surface at all — an engineer cannot yet express a
design, only construct entities by hand.

This stage delivers the language: the declarative surface an engineer or an
agent writes, and the elaborator that turns it into a graph snapshot and a tool
plan.

## What Changes

- Add `fang.lang`: `Module`, `System`, `Parameter`, `Electrical`, the connect
  operator, `require()`, and the unit literals that make `3.3 * V` a quantity.
- Add `fang.traits`: trait registration and enumeration without instantiating
  any backend.
- Add `fang.toolplan`: plan emission, handles as symbolic conditions, and the
  elaboration-time handle-read error.
- Add `fang.sandbox`: enforced network denial, declared-and-hashed file inputs,
  and a declared seed for any randomness.
- Add `fang.elaborate`: the elaborator that walks a system, derives identity
  from the module path, attaches a source location to every entity, and returns
  a snapshot and a plan.

## Capabilities

### New Capabilities

None. This stage implements requirements the `fang-kernel` spec already carries.

### Modified Capabilities

- `fang-kernel` — adds the language-surface requirements that refine the
  existing standard-level ones: the declaration model, parameter references,
  the connect operator, the elaboration result, and sandbox enforcement.

## Impact

- New modules under `fang/`; no change to the kernel core's public API.
- Elaboration output feeds the existing transaction gate unchanged, so the
  language gets no privileged path into canonical state.
