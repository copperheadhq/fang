# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

While the major version is 0, the EIR schema version (`fang.SCHEMA_VERSION`) is
tracked separately and moves only when the serialized form changes.

## [Unreleased]

### Added

- Verification questions (`fang-verification`, copperhead RFC 12 version 1.3,
  Sections 12.7 to 12.10). `Simulates`, `Checks` and `Evaluates` declare a
  question beside the requirement it serves: the parameters it measures into,
  the measures that produce them, and for a circuit question the bench in full.
  Each elaborates to a `Verification` whose result is `UNKNOWN`, and none
  accepts a result; a program that gives a measured parameter a value is
  refused (`SIM-0002`). `route()` answers at the equation level only when every
  measured parameter holds a value and every constraint over them is decided,
  and otherwise picks the first registered tool at the level the method names;
  a missing tool is reported unsupported, by name, and nothing stands in for
  it.
- Measurements re-enter through the commit gate: each measured parameter set to
  an inferred value whose source is the run's `Evidence`, that evidence
  carrying the measurement record of RFC 3 version 1.5 Section 14, and the
  verification replaced under its own identifier with its result, level and
  tool. A measured value that fails a hard constraint never reaches the head;
  the failure is recorded as evidence and a `FAIL` verification instead.
  Re-elaborating a program keeps what runs measured while it is current, that
  is while preparing the same question again gives the same job: a changed
  circuit, model file or firmware drops the measurement and the question runs
  again. A run already recorded for the same job and tool version is not run
  again; its recorded measurements go back through the gate, so a relaxed or
  tightened constraint is judged afresh. Every record says where it ran.
- Four tools behind one protocol: ngspice (operating point, transient and AC,
  measured through a `.control` block), Xyce (the same circuit with `.MEASURE`
  lines, unsupported where not installed), KiCad's electrical rules check over
  the schematic fang draws, with exclusions declared and recorded with their
  reasons, and Touchstone models read in-tree for return loss through a
  matching network, in closed form. Model and Touchstone files are named in a
  run's bundle by their relative path, or by their content where two different
  files share one; two models declaring one subcircuit, pins on different nets
  reaching one model port (`SIM-0006`), an ERC report of another schema, and
  matching parts that do not form the ladder a return loss names are refused
  rather than run.
- `fang verify`, which routes and runs every declared question and persists
  the measurements only with `--commit`, through the gate; `--commit` refuses a
  program changed since its last build, which is `fang build`'s to persist.
- `examples/rc_filter/` and `examples/antenna_match/`, and `verification.txt`
  among the outputs an example with a question ships. `buck_regulator/`'s
  hand-asserted `Verifies(..., result="PASS")` is now a question ngspice
  answers under full load, on an ideal power stage whose provenance is an
  assumption.
- A provenance record that changes an existing entity names the fields it
  changes (RFC 3 Section 14): `parameters.<name>.value` on the part a
  measurement sets, and `evidence`, `level`, `result` and `tool` on a replaced
  verification.
- Diagnostic codes `SIM-0001` to `SIM-0008`, a `dB` unit, and the `GHz`, `nH`
  and `dB` literals. A decibel compares and converts only with decibels, and a
  return loss measures only into a parameter declared in dB (`UNIT-0001`).

- Six worked examples beyond the divider and the sensor board: `blinky/`, `equations/`,
  `i2c_bus/`, `usb_uart_bridge/`, `buck_regulator/`, and `servo_drive/`,
  covering the ground atopile's own example set covers — a first board, design by
  equation, a multi-drop bus with addresses, chosen vendor parts, and a
  three-phase drive built from one reusable block.
- `tests/test_examples.py`, which builds every example in `examples/`: it must
  elaborate, validate, fail no check, project to a netlist that leaves no
  component unconnected, emit a KiCad netlist, and do it identically twice.
- A parity harness against atopile. `examples/parity/` is an atopile project
  whose boards mirror `divider/` and `blinky/` instance for instance, and
  `tests/test_parity.py` asserts that both toolchains produce the same
  components and the same partition of pads into nets. Designators, net names,
  and part identity are deliberately not compared — each is the toolchain's own
  business. The atopile artifact is checked in, so the suite needs neither
  atopile nor a network; the parts are atomic so that refreshing it needs no
  account either.
- Every example is now a folder — the program, a `README.md` explaining what it
  is for, and the files `fang` produces from it under `out/`: the KiCad netlist,
  the netlist, check and graph listings, the views worth looking at, and a
  `rationale.md` projecting the requirements, decisions, calculations and
  evidence the design records. `python examples/regenerate.py` rewrites them,
  and `tests/test_examples.py` rebuilds and compares them, so a committed output
  cannot drift from the program beside it.
- `examples/README.md`, indexing the programs and saying what is in an
  `out/` and how it got there.
- A regression test that two hard constraints bounding *different* parameters of
  one target are not read as a contradiction — the grouping this relies on has
  always been keyed by parameter, and nothing said so.
- [site/docs/](site/docs/), an Astro + Starlight documentation site for
  `fang.copperhead.sh`, pinned to the versions `docs.copperhead.sh` runs.
- A port can name the peripheral instance it is,
  `I2CPort(peripheral="I2C1")`, recorded on the port entity. A part with I2C on
  two controllers declares two ports, and a connection lowers only onto the
  named one's pins.
- A candidate pin can carry the selector that routes the signal to it:
  `PinMap({"i2c1.scl": {"PB8": AF(4), "PB6": AF(4)}}, evidence="af_table")`,
  with `Selector(text)` as the general form. A map with selectors names the
  `Cites` declaration they were read from, or elaboration refuses it
  (`IFACE-0003`). The lowering records the chosen pin's selector and the
  evidence on the pin connection, as `selectors`.
- An addressed bus device's port carries its address: a dimensionless `address`
  on the I2C interface, or `Strap(pin, {device pin: address})`, whose pin names
  are resolved at elaboration (`IFACE-0004` for one the part does not have).
  `fang.compatibility.resolve_address` reads either, resolving a strap from the
  inferred nets, and the addressing rule now uses it for every participant and
  compares addresses by overlap: two devices at one address fail naming both,
  overlapping addresses and an unresolved strap or conflict are undecided, a
  controller with no address is not reported, and a bus passes only when every
  address is known and none overlap. A fixed address given as a range or a
  tolerance is refused (`UNIT-0001`), and the rule's scope covers the strap
  pin's net, so re-tying a strap brings the rule into the gate.
- [examples/sensor_node/](examples/sensor_node/): an STM32F401RE reading an
  HS3001 on I2C1, with a console on USART2 and an LED on PA5. Every pad number,
  alternate function and address is cited by table and page from ST's and
  Renesas's datasheets.
- Firmware emulation in Renode (`fang.emulation`, `fang.renode`). `Emulates`
  declares a question beside its requirement: a run's virtual duration,
  stimuli (`At`), faults (`Absent`), abstracted parts and measures (`FirstAt`,
  `Count`, `Latency`, `UartValue`, `PinConfig` over `I2CRead`, `I2CWrite`,
  `Rises`, `Falls` and `UartLine`), routed at the behavioural level to the
  `renode` tool. Its plan resolves every bus, pin, alternate function and
  address from the graph before anything runs; the lowering writes Renode's own
  platform description and script; C# probes record what devices, pins and
  UARTs were observed doing; and the measurements re-enter through the commit
  gate. `EmulationModel` and `Firmware` bind the models and the ELF, whose
  digest is recorded on evidence and never in the snapshot; the path resolves
  against the program that declares the part. Refusals are `SIM-0009` to
  `SIM-0016`, among them a pin configuration over a port with no bus, a match
  detail nothing reads, a window that is not a time or is reversed, an
  observation of a device a fault removes, a stimulus outside the run, a run of
  no time or less, an address that is not a whole number, a pin selector the
  platform does not read, a model descriptor fang does not ship (naming the
  part), and two probes that would share a name. A model warning is matched
  only against the expected warnings of the descriptor of the model that
  raised it. A Renode installed at a version the lowering was not checked
  against, or a temporary directory whose path has a space, is reported
  unsupported, by reason.
- `fang emulate`, the low-level emulation command, with `-o` and
  `--bundle-only`, which fails when a run times out or crashes; `fang verify` reports a verification whose evidence names a
  firmware the bound file no longer is as stale, and runs it again. Under
  `fang verify --commit` each run keeps its bundle, events, log and outcome in
  the workspace.
- `fang schematic --drafter copperhead`, a second schematic lowering:
  `fang.copperhead` writes copperhead's netlist intent from a snapshot and runs
  `copperhead draft schematic` across a process boundary, and the sheet is read
  back with `kicad-cli` and returned only if its nets are exactly the design's.
  A part is drawn with the symbol it declares as `symbol = "library:name"`
  (which also reaches the netlist as its `libsource`), else the one its part
  type names (op amps, diodes, meters, lamps), else `power:GND` for a ground
  marker, else the one its designator prefix names; each symbol says where the
  part's pins go when its numbering differs, so pins are placed by name. The
  ground net's name, terminal names, short values and the title-block date are
  explicit options. A part with no symbol, a pin its symbol has no place for,
  or a net with fewer than two drawn pins is reported as a loss.
  `noninverting_amp/` ships its draft, and `examples/draw_figures.py` draws
  every textbook figure through the same `compile_intent`, which reproduces
  each committed figure intent byte for byte.
- `examples/sensor_node/firmware/`: bare-metal firmware for the board, with
  three deliberately broken builds, committed with the toolchain that builds
  them byte for byte. The board's two requirements are decided by running it.
- Acceptance tests AT-F1 and AT-F2, run where Renode 1.17.0 is installed.

### Changed

- The gate takes a check class's scope over the head as well as the candidate
  when deciding which checks a transaction requires, so a removal still brings
  in the check that covered what it removed. Condition 5 does not count a
  constraint undecided only because a declared verification question has not
  yet measured, or failed to measure, its parameter.
- `SCHEMA_VERSION` is 1.2. Port records gain optional `peripheral` and
  `address_strap` keys and connection records an optional `selectors` key, each
  omitted when absent, which the spec counts as an additive change.
- An interface parameter given as a bare number is refused with `UNIT-0001`
  naming the parameter, as a module parameter already was, rather than raising
  `AttributeError`.
- `Value.unknown` takes an optional reason, kept as the value's rationale.
- The constraint check's scope includes every entity a constraint's expression
  reads, not only its targets, so setting a parameter that another module
  constrains brings the check into the gate.
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

- Renode's bundle no longer carries the snapshot hash, so a change elsewhere
  in the design leaves an emulation job current (RFC 12 Section 12.8). The plan
  schema is `fang.emulation/v2` for it; a v1 plan still reads, and a consumer of
  v1 refuses v2 by its label rather than failing on the missing field.
- A statistic window (`PeakToPeak`, `Average`, `Maximum`, `Minimum`) that does
  not start before it ends is refused where it is written (`SIM-0003`).
- A rebuild carries a measurement that a since-tightened constraint now breaks
  as that failure, the verification `FAIL` and the value withheld, so `build`
  and `verify --commit` no longer stop until the design changes (RFC 12
  Section 12.9).
- Xyce aborts an AC deck that sets `TIMEINT METHOD`, so every AC question
  routed to Xyce failed; AC decks no longer set it, and the dialect has run
  against Xyce 7.10.
- `examples/buck_regulator/`'s controller EN pin was floating; it is tied to
  the input, as the TPS62130 datasheet shows.
- The copperhead lowering drew diodes and LEDs backwards: KiCad numbers the
  cathode 1 and fang the anode. Pins are now placed by name, and
  `--drafter copperhead` draws the handbook's op amps, which it used to drop
  as a loss.
- `examples/sensor_board/` declared a bulk capacitor and two pull-up resistors
  and never connected them.
- `fang sim` reported every run as failed: it handed ngspice a relative
  workspace, and ngspice, run from inside it, looked for the deck relative to
  itself. The
  backend now resolves the workspace first.

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
