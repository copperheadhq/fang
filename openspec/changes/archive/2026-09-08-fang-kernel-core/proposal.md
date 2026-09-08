# Fang Kernel Core

## Why

The Fang standards exist as prose (the EIR and kernel standards) with no executable
kernel behind them. Every downstream Copperhead subsystem — schematic
generation, layout, checking, simulation, agent workflows — depends on one
canonical typed engineering graph that does not yet exist in code. Until the
graph, its identity rules, its units, its constraint registry, and its
transaction gate are real and tested, nothing above them can be built on solid
ground.

This change combines the Engineering Intermediate Representation and the
hardware kernel and Fang language standards into a single normative
`fang-kernel` capability, and implements the kernel core that the delivery plan's Appendix
B.2 calls Phase 1.

## What Changes

- Introduce the `fang-kernel` capability: one combined spec carrying identity,
  canonical semantic paths, quantities and units, value status and unknowns,
  typed connections, interfaces and their lowering, the single constraint
  registry and its expression language, topology intent, transactions and the
  commit gate, semantic diff, deterministic serialization, provenance,
  diagnostics, the tool plan, views, simulation, adapters, security boundaries,
  and every conformance requirement and acceptance test from both RFCs.
- Implement the kernel core in Python 3.11+ as the `fang` package:
  - `fang.units` — dimension vectors, unit algebra, decimal-string quantities.
  - `fang.values` — value records with explicit/inferred/assumed/unknown status.
  - `fang.identity` — UUIDv5 derivation, canonical semantic paths,
    transliteration, deterministic collision lengthening, explicit keys.
  - `fang.entities` — the EIR entity model and the project root.
  - `fang.provenance` — append-only provenance records.
  - `fang.constraints` — the single registry, the constraint record, and the
    typed expression evaluator with three-valued logic.
  - `fang.serialization` — canonical JSON and the canonical record stream.
  - `fang.validation` — structural validation and requirement state transitions.
  - `fang.graph` — the kernel graph, snapshots, transactions, the proposal
    sandbox, and the commit gate.
  - `fang.diff` — semantic diff classification.
- Add an acceptance test suite mapping one test per acceptance criterion in the
  spec, so conformance is measured rather than asserted.

Not in this change, and deferred to their own later changes: interface lowering
to pins and compatibility checking (Phase 4), topology verification (Phase 4),
CAD import and round trip (Phase 2), views (Phase 3), simulation (Phase 6), and
the public Fang language surface (Phase 7). The spec carries their requirements
now because the combined spec is the whole standard; the tasks in this change
cover the kernel core only.

## Capabilities

### New Capabilities

- `fang-kernel` — the combined Fang kernel and representation standard.

### Modified Capabilities

None. This is the first capability in the project.

## Impact

- New `fang/` Python package and `tests/` suite; no existing code to migrate.
- The RFC markdown files remain the source documents and are not edited; the
  spec is derived from them and becomes the working contract.
- Establishes the invariants every later change must hold: one canonical model,
  transactional mutation, explicit unknowns, and deterministic output.
