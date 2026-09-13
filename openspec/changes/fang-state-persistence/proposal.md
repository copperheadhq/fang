## Why

RFC 12 version 1.2 Section 6.6 requires that traits persist with the snapshot and
that a persisted snapshot reload into typed entities and traits without executing
any program. Fang can do neither today.

- **Traits are not saved.** `Workspace.write_snapshot` writes
  `snapshot.records()`, and traits are not in the records. Elaboration keeps them
  in a separate `TraitRegistry` returned beside the snapshot, which
  `compile_netlist`, `lower_to_spice`, the runtime, the CLI, and the MCP session
  take as a separate `traits=` argument. A footprint mapping, a sourcing record,
  or a datasheet citation therefore exists only while the program runs, which is
  what RFC 12 Section 3.2 forbids.
- **A saved design cannot be read back as typed state.** The only `from_dict` in
  the package is `Manifest`'s. `Workspace.read_snapshot` returns a snapshot with
  no entities unless the caller already holds live ones, which means running the
  program again. `fang mcp` refuses `add_entity` for the same reason: "the kernel
  has no rehydration registry".

This is the second of five changes implementing RFC 12 version 1.2, and the
changes after it depend on it: a program over imported state elaborates against
a loaded snapshot, and a schematic import persists what it imports for those
programs to read.

## What Changes

- **Traits become part of their entity.** Each entity carries its traits by
  protocol, serialized inside its record under a `traits` key, as RFC 3 version
  1.4 Section 5 specifies. Elaboration attaches them there. `TraitRegistry`
  becomes a view derived from a snapshot, so every `traits=` argument stays
  accepted and defaults to the snapshot's own traits.
- **A rehydration registry.** Every entity kind, trait protocol, and value type
  the kernel serializes gains an explicit decoder that inverts its `as_dict`, in a
  registry later changes extend with their own kinds.
- **Typed workspace reload.** `Workspace.read_snapshot()` rebuilds typed entities
  and traits from `design.jsonl` with no program run. It checks the manifest's
  schema major version, and refuses a stream whose rebuilt content hash differs
  from the snapshot hash the manifest records.
- **Nothing dropped silently.** A record of an unknown kind, a trait of an
  unknown protocol, or a known record carrying keys its decoder does not model is
  preserved verbatim, reserializes byte-identically, and is named in a load
  report. A malformed record refuses the whole load, and no partial snapshot is
  returned.
- **Trait changes diff as trait changes.** A change confined to an entity's
  traits classifies as `model_or_trait_changed`.
- **The schema minor version moves**, because records gain an optional key.
  Designs written under schema 1.1 still load.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `fang-kernel`: adds a requirement that a persisted snapshot reloads without
  running a program; extends "Traits As The Extension Mechanism" so traits
  persist with their entity; and strengthens the round-trip scenario of "The
  Workspace Layout" to typed entities, byte-identical reserialization, and the
  manifest's snapshot hash.

## Impact

- Code: `fang/entities.py` (traits on `Entity`, entity decoders), `fang/traits.py`
  (trait decoders, the registry as a view), a new `fang/rehydrate.py` (the decoder
  registry and the load report), decoders beside `as_dict` in `fang/identity.py`,
  `fang/provenance.py`, `fang/diagnostics.py`, `fang/values.py`, `fang/units.py`,
  `fang/constraints.py`, and `fang/topology.py`, RFC 3339 parsing in
  `fang/serialization.py`, a typed `read_snapshot` in `fang/workspace.py`, trait
  attachment in `fang/elaborate.py`, trait-change classification in
  `fang/diff.py`, `SCHEMA_VERSION` in `fang/__init__.py`, and the trait consumers
  in `fang/netlist.py`, `fang/simulation.py`, `fang/runtime.py`, `fang/cli.py`,
  and `fang/mcp.py`.
- Snapshot hashes change for every design whose parts carry traits, because the
  records now include them. Committed example outputs already normalize hashes
  and are regenerated only where something else moves.
- Tests: `tests/test_workspace.py`, `tests/test_serialization.py`,
  `tests/test_traits.py`, `tests/test_diff.py`, and a new
  `tests/test_rehydrate.py`.
- Not in scope: an agent adding an entity over MCP, which stays refused because
  minting an agent's identity and provenance needs a requirement of its own;
  building from a workspace in the CLI; programs over a base snapshot; and the
  fields schematic import adds.
- Coordination: open PR #4 (`fang-physical`) also moves `SCHEMA_VERSION` to 1.2
  and adds physical entity kinds, which will need decoders registered.
