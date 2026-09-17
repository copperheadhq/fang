## Why

RFC 12 version 1.2 Section 14.4 requires Fang to import a KiCad schematic and to
derive its connectivity from the drawing itself, with the identity, fitted state,
and presentation that the drawing carries. Fang can only import a netlist today,
and that falls short in two ways.

- **A netlist has lost what the schematic knew.** A KiCad netlist keys a part on
  its reference designator, not on the symbol's persistent UUID, so renumbering
  the schematic changes every identity. It drops:
  - the symbol library identifier and the unit;
  - do-not-populate and the exclusions from the bill of materials and the board;
  - the no-connect markers;
  - the pins' electrical types;
  - which sheet each part sits on;
  - where every symbol, label, and marker was drawn.

  RFC 12 Sections 11.7 and 14.4, and RFC 3 version 1.4 Sections 8.1, 9.1, 9.2,
  16, and 17.3, require each of these carried into state or reported.
- **For some projects there is no netlist to import.** `kicad-cli sch export
  netlist` loads only the first sheet of a project that declares several
  top-level sheets. PCBGolf, the project that scopes RFC 12's Phase 9, is such a
  project: exported from the command line it has 35 of its 245 components. The
  importer has to resolve connectivity itself, across every top-level sheet.

This is the third of five changes implementing RFC 12 version 1.2. It depends on
`fang-state-persistence`, because an imported design is only useful once it
persists and reloads typed. The two changes after it build on an imported
snapshot:
- programs over imported state, with single ownership of each fact;
- the drafting projection.

## What Changes

- **A KiCad schematic adapter.** It reads a KiCad project, taking the top-level
  sheets from `.kicad_pro`, or a single `.kicad_sch`, and produces kernel
  entities, a mapping table, presentation records, and an import report.
- **Connectivity from the drawing.** The adapter resolves:
  - each pin's position after the symbol's position, rotation, mirroring, and
    unit are applied;
  - wires, including a pin, a label, or a wire end that meets a wire between its
    endpoints;
  - junctions, and local, global, and hierarchical labels;
  - power symbols, and hierarchical sheets with their sheet pins;
  - several top-level sheets joined by global labels and power symbols.
- **Nets named as KiCad names them.** This includes a net no label names, which
  gets KiCad's `Net-(...)` name, and a lone pin, which gets its
  `unconnected-(...)` name. The CAD name is kept as an alias, and the net class
  is recorded.
- **Identity on the persistent identifier.** A component's canonical identifier
  is keyed on its symbol UUID, qualified by the sheet instance path for a sheet
  used more than once, and not on its reference designator. The mapping table
  records the UUID and the reference, so renumbering the schematic preserves
  every identifier.
- **New record fields, as RFC 3 version 1.4 defines them.**
  - A component gains a symbol reference (library identifier and unit), its value
    text verbatim, and its fitted state (do-not-populate, excluded from the bill
    of materials, excluded from the board).
  - A pin gains its electrical type and no-connect intent.
  - A net gains its net class.
  - Every component records its sheet.
  - The footprint and the fields the adapter models travel as traits. Every other
    field is reported.
- **Presentation records.** For every placed symbol, the sheet, position,
  rotation, mirroring, and unit are recorded. For every label, power symbol, and
  no-connect marker, the position and orientation are recorded. They are:
  - keyed by entity identifier;
  - stored under `.copperhead/presentation/`, apart from the canonical records;
  - excluded from identity derivation;
  - classified as a presentation change when they alone change.
- **A fidelity check.** An import is compared with a netlist KiCad exported for
  the same sources. Every difference in the component set, in a net's pin
  membership, or in a net's name is reported.
- **`fang import`**, which imports a project into its workspace and writes the
  mapping table, the import report, and the presentation records.
- **The schema minor version moves**, because records gain optional fields.
  Earlier designs still load.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `fang-kernel`:
  - adds a requirement that the KiCad schematic adapter derives connectivity and
    net names from the drawing;
  - adds a requirement that imported presentation state is stored apart from the
    canonical records;
  - adds a requirement that schematic import fidelity is checked against the CAD
    tool's own netlist;
  - extends "The Part Model" with the symbol reference, verbatim value text, and
    fitted state;
  - extends "The Pin Model" with the electrical type and no-connect intent;
  - extends "The External Identifier Mapping Table" to key on a persistent object
    identifier;
  - extends "The Workspace Layout" with the presentation directory;
  - extends "Semantic Diff Classification" to presentation records;
  - extends "The Command Surface" with `fang import`.

## Impact

- **Code:**
  - a new schematic adapter module, beside `fang/kicad.py`, for geometry,
    connectivity, and net naming;
  - a new presentation module for presentation records;
  - the new fields and their decoders in `fang/entities.py` and
    `fang/rehydrate.py`;
  - identifier keying in `fang/importing.py`;
  - the presentation directory in `fang/workspace.py`;
  - presentation classification in `fang/diff.py`;
  - `fang import` in `fang/cli.py`;
  - `SCHEMA_VERSION` in `fang/__init__.py`.
- **Fixtures:** small schematics written for these tests in KiCad 10's format.
  Each is paired with the netlist `kicad-cli` 10.0.4 exports from it as the
  oracle, so every fixture is ours to license. PCBGolf's sheets serve only as a
  local check and are not committed, because that design carries no license. Its
  end-to-end harness belongs in the PCBGolf fork.
- **Not in scope:**
  - parsing value text into inferred parameters, which RFC 12 permits but does
    not require;
  - drafting a schematic back out;
  - importing a board, and linking footprints to symbols by UUID;
  - programs elaborated against the imported snapshot;
  - KiCad's legacy `.sch` format;
  - buses, which are reported rather than resolved.
- **Coordination:** open PR #4 (`fang-physical`) and PR #6
  (`fang-state-persistence`) each move `SCHEMA_VERSION` to 1.2. This change takes
  the next free minor version after whichever of them merges last.
