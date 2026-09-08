# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

While the major version is 0, the EIR schema version (`fang.SCHEMA_VERSION`) is
tracked separately and moves only when the serialized form changes.

## [Unreleased]

### Added

- Six worked examples beyond the divider and the sensor board: `blinky/`, `equations/`,
  `i2c_bus/`, `usb_uart_bridge/`, `buck_regulator/`, and `servo_drive/`,
  covering the ground atopile's own example set covers — a first board, design by
  equation, a multi-drop bus with addresses, chosen vendor parts, and a
  three-phase drive built from one reusable block.
- `tests/test_examples.py`, which builds every example in `examples/`: it must
  elaborate, validate, fail no check, project to a netlist that leaves no
  component unconnected, emit a KiCad netlist, and do it identically twice.
- Every example is now a folder — the program, a `README.md` explaining what it
  is for, and the files `fang` produces from it under `out/`: the KiCad netlist,
  the netlist, check and graph listings, the views worth looking at, and a
  `rationale.md` projecting the requirements, decisions, calculations and
  evidence the design records. `python examples/regenerate.py` rewrites them,
  and `tests/test_examples.py` rebuilds and compares them, so a committed output
  cannot drift from the program beside it.
- `examples/README.md`, indexing the eight programs and saying what is in an
  `out/` and how it got there.
- A regression test that two hard constraints bounding *different* parameters of
  one target are not read as a contradiction — the grouping this relies on has
  always been keyed by parameter, and nothing said so.
- [site/docs/](site/docs/), an Astro + Starlight documentation site for
  `fang.copperhead.sh`, pinned to the versions `docs.copperhead.sh` runs.

### Changed

- Views are drawn to be read. A node carries the name it has in the program
  rather than its class — `bridge_u.high`, not a third box saying `Transistor` —
  with the class underneath; rows within a layer are ordered to reduce crossings
  and columns are centred; a node this view connects to nothing is packed into a
  grid below a rule that says so, instead of lengthening the first column; edges
  leave the side of the box they are heading for and curve to it rather than
  cutting through whatever is between, and parallel edges fan out so that three
  connections do not read as one. Each diagram now carries the question it
  answers, a key for the edge colours, and its own incompleteness.
- Interface compatibility now checks a link only over the parameters every party
  to it declares, and treats a port whose interface declares none — a passive
  pad, a test point — as a wire on the link rather than a participant in it.
  A 22 Ohm resistor in series with a USB pair was previously asked for its logic
  levels, bit rate and voltage domain, and answered undecided to all three.
- An interface link now continues through a part that declares it bridges its
  own terminals, so the two ends of a series path are compared with each other.
  On [examples/usb_uart_bridge/](examples/usb_uart_bridge/) the receptacle
  and the bridge IC were never compared at all, because two series resistors
  stood between them; the same file went from 46 undecided results to 7, and the
  one check that matters now runs.
- `Part.bridges` declares which of a part's surfaces it conducts between;
  `TwoPin` and everything built on it bridge their two terminals, `Transistor`
  and `Connector` bridge nothing. The fact reaches the component entity as an
  extension, because a component's body is not a connection and nothing else in
  the graph said current entering one terminal leaves at the other.
- `DIGITAL_PARAMETERS` gained `voltage`, which the voltage-domain check has
  always read and the catalogue never declared.

### Fixed

- `examples/sensor_board/` declared a bulk capacitor and two pull-up resistors
  and never connected them.

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
