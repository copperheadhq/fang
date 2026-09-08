# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

While the major version is 0, the EIR schema version (`fang.SCHEMA_VERSION`) is
tracked separately and moves only when the serialized form changes.

## [Unreleased]

## [0.1.0] - 2026-09-08

The first packaged release. All eleven roadmap stages are delivered and all 23
acceptance criteria (AT-R1..AT-R13, AT-K1..AT-K10) are demonstrated by tests.

### Added

- **Kernel** — the EIR entity model, UUIDv5 identity derivation, dimension
  vectors over the seven SI bases, decimal quantities, value status with
  explicit unknowns, the single constraint registry with three-valued logic,
  topology intent, content-hashed snapshots, transactions, and the six-condition
  commit gate.
- **Language** — `Module`, `System`, `Part`, unit-carrying parameters, traits,
  `require()`, the connect operator, and deterministic sandboxed elaboration
  with network denial and declared, hashed inputs.
- **Interfaces** — a catalogue of 17 typed interfaces, the pin model,
  deterministic interface-to-pin lowering, and compatibility checking.
- **Parts** — designators, packages, footprints, sourcing, and a standard
  library of generic parts.
- **Netlist** — net inference, designator assignment, and KiCad netlist
  emission.
- **CAD** — an s-expression reader, KiCad project import, the mapping table,
  loss reporting, and one safe round trip.
- **Tool plan** — handles as symbolic conditions, the tool contract, the
  operation phase, and realizations.
- **Views** — the view compiler, the six required views, the layout boundary,
  SVG rendering, and placement seeds.
- **Simulation** — models as traits, explicit simulation plans, SPICE lowering,
  the optional ngspice backend, and normalized results.
- **Rationale** — requirements, assumptions, decisions, evidence, calculations,
  the verification graph, and impact propagation.
- **CLI** — the `fang` command (`build`, `check`, `netlist`, `export`, `view`,
  `sim`) over a `.copperhead/` workspace and its manifest.
- Canonical JSON serialization and the canonical record stream, byte-identical
  across processes with differing hash seeds.
- A namespaced diagnostic code registry over `ELAB IFACE TOPO UNIT TXN SIM
  IMPORT`, with codes allocated and retired rather than reused.
- `py.typed`: the package ships its inline type information.

### Notes

- The distribution is published as `copperhead-fang`; the import name is `fang`.
- Pure Python 3.11+ with no required dependencies. NetworkX (the `analysis`
  extra) backs optional graph queries; ngspice is an optional external
  simulator. When either is absent the toolchain says so rather than
  substituting anything.

[Unreleased]: https://github.com/copperheadhq/fang/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/copperheadhq/fang/releases/tag/v0.1.0
