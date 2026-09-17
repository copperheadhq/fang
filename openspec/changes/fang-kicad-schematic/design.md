## Context

**What imports today.** `read_netlist` in `fang/kicad.py` reads a KiCad netlist. It keys each component on its reference designator, names pins by number, and names each net as the file does. Everything else the schematic knew is gone before the file reaches it:
- the symbol UUID;
- the library identifier and unit;
- do-not-populate and the exclusions;
- no-connect markers;
- pin electrical types;
- sheet membership;
- where anything was drawn.

For a project that declares several top-level sheets, `kicad-cli sch export netlist` loads only the first sheet, so there is often no netlist to read at all.

**The KiCad 10 schematic format, as read from real files.**
- **Parsing.** `fang.sexpr.parse` reads PCBGolf's largest sheet, with 780 top-level items, in 0.11 s.
- **Symbol definitions.** Every schematic embeds `lib_symbols`, a full definition of each symbol it places, with derived symbols flattened. No library lookup is needed.
- **Placed symbols.** A placed symbol carries:
  - `lib_id`, `(at x y angle)`, an optional `(mirror x|y)`, `unit`, and `body_style`;
  - `exclude_from_sim`, `in_bom`, `on_board`, `in_pos_files`, and `dnp`;
  - `uuid`;
  - properties: `Reference`, `Value`, `Footprint`, `Datasheet`, and any others;
  - one `(pin "n" (uuid))` per pin;
  - `(instances (project (path "/…" (reference) (unit))))`.
- **Library pins.** A library pin carries an electrical type, `(at x y angle)` in symbol coordinates with y pointing up, a name, and a number. Pins sit in sub-symbols named `<name>_<unit>_<body style>`, where unit 0 is common to every unit.
- **Power symbols.** A power symbol's definition is flagged `(power)`, `(power global)`, or `(power local)`, and its net name is its `Value`.
- **Top-level sheets.** `.kicad_pro` lists them under `schematic.top_level_sheets` as filename, name, and uuid. A symbol on a top-level sheet has the instance path `/<top-level sheet uuid>`.
- **Boards.** On PCBGolf's board, every one of 245 footprints has the one-segment path `/<symbol uuid>`, and the sheet recorded as `/Power/`, `/Channels/`, and so on.
- **Hierarchical sheets.** A hierarchical sheet symbol carries `(at)`, `(uuid)`, `Sheetname`, `Sheetfile`, sheet pins, and instance pages.

**KiCad's connectivity rules.** These were established by exporting netlists with `kicad-cli` 10.0.4 from schematics generated to isolate each rule. They are not written down by KiCad in a form a reader can rely on.

1. **Pin placement.** A pin's sheet position is the symbol's `at` plus the library point `(px, −py)`, rotated counter-clockwise as drawn by the symbol's angle, then mirrored:
   - rotation is `(x, y) → (x·cos θ + y·sin θ, −x·sin θ + y·cos θ)`;
   - `mirror x` negates y, and `mirror y` negates x.

   Of four candidate conventions, only this one placed every pin correctly across the twelve orientations, and it also holds for each unit of a multi-unit symbol.
2. **Coincident points.** Wire endpoints, pins, labels, junctions, and power pins at the same point connect.
3. **Points on a wire's middle.**
   - A label or a junction on a wire, between its endpoints, connects to the wire.
   - A wire end or a pin on a wire's middle does not connect without a junction.
   - Crossing wires do not connect.
4. **Joins by name.**
   - Local labels of one name connect within a sheet instance.
   - Global labels and power symbols of one name connect across the whole project; a global label `GND` joins power `GND`.
   - A hierarchical label connects to the sheet pin of its name on the sheet instance above.
5. **Unplaced units.** The pins of a multi-unit symbol's unplaced units are not in the netlist.
6. **Name priority.** A net's name comes from the highest-priority source it carries: a global label, then a power symbol, then a local label, then a hierarchical label. A tie goes to the lowest name, wherever each label sits. A local or hierarchical name is prefixed with its sheet path:
   - `/NAME` on the root sheet;
   - `/sheet/NAME` in a sub-sheet;
   - `/Power/NAME` on a top-level sheet of a project with several.

   Global and power names are bare.
7. **Unnamed nets and lone pins.**
   - A net with no name source takes a pin-derived name: `Net-(D2-A)` when the pin has a name, `Net-(R115-Pad2)` when it does not.
   - A lone pin is named `unconnected-(J3-RX1+-PadB11)` or `unconnected-(R117-Pad1)`. A multi-unit reference can carry its unit letter, as in `unconnected-(U2A-+-Pad3)`.
   - A `/` in a pin name is written `{slash}`, and a repeated name gets `_1`.
   - A no-connect pin keeps its `unconnected-` name, with the pin type `passive+no_connect`.

**The RFC wording differs from KiCad.** RFC 12 Section 14.4 counts "a pin, a label, or a wire end that meets another wire between its endpoints" as connecting. KiCad connects only a label or a junction there. Fidelity is measured against KiCad's own netlist, so KiCad's rule governs. See Open Questions.

## Goals / Non-Goals

**Goals:**

- Import a KiCad 10 project, including one with several top-level sheets, with every component, pin membership, and net name matching KiCad's own netlist, and report every difference.
- Key component identity on the symbol UUID, so renumbering preserves it and a later board import can link footprints to the same identifiers.
- Carry into state the fields RFC 3 version 1.4 adds:
  - the symbol reference, verbatim value text, fitted state, and sheet;
  - each pin's electrical type and no-connect intent;
  - each net's class.
- Record presentation state apart from the canonical records.
- Import through the commit gate, persist the result, and reload it typed.

**Non-Goals:**

- Parsing value text into inferred parameters.
- Resolving buses, bus entries, bus aliases, net class directive labels, or rule areas. Each is reported.
- Board import and footprint linking.
- Drafting a schematic back out.
- Programs elaborated against the imported snapshot.
- KiCad's legacy `.sch` format, and files older than format version 20231120 (KiCad 8). Those are reported and not read.

## Decisions

### D1. A drawing reader and a net resolver, in separate modules

- **`fang/kicad_schematic.py`** reads files into a typed drawing model. The model holds sheet instances, placed symbol units with their pins in sheet coordinates, wires, junctions, labels, power symbols, no-connect markers, and sheet pins. The module reports every construct the model does not hold, and holds `read_schematic`.
- **`fang/schematic_nets.py`** resolves nets and their names over that model.

The two are tested separately. Connectivity rules are tested on small drawing models built in code, with no files involved. The reader is tested against files, with no nets resolved.

Alternative considered: one module. Rejected: it would run past a thousand lines mixing parsing with graph resolution, and a connectivity test would need a file to exist.

### D2. Exact geometry

Coordinates are parsed as `Decimal` millimetres and compared exactly. Rotation uses integer sines and cosines, since a placed symbol's angle is a multiple of 90. A symbol at any other angle is reported and its pins are not placed. A point lies on a segment when the exact cross product is zero and the point falls within the segment's bounds.

Alternative considered: floats compared within a tolerance. Rejected: tolerance makes the tie cases depend on the rounding, where KiCad's integer internal units give exact answers.

### D3. Connectivity is a union of points

For each sheet instance:
- every wire endpoint, pin, label anchor, junction, power pin, no-connect marker, and sheet pin is a node;
- nodes at one point are joined;
- a label or a junction lying on a segment is joined to the segment.

Name joins follow:
- local labels within a sheet instance;
- global labels and global power symbols across the project;
- local power symbols within their sheet instance;
- each hierarchical label to its parent's sheet pin.

A pin under a no-connect marker records the intent. If it is also joined to another pin, that is reported.

Checking every label against every wire is quadratic, but PCBGolf has about a thousand wires, so no spatial index is added.

### D4. Net naming reproduces KiCad's

Each net collects candidate names by the priority in Context rule 6:
- the lowest name at the highest priority wins;
- a local or hierarchical name is prefixed with its sheet name path;
- a net with no candidate is named from its lowest member pin, in the forms of rule 7;
- a name already taken gets `_1`, `_2`, and so on.

Every rule has a fixture whose oracle netlist fixes it. Two details are not settled by the probes. Their first implementation is the ordering fixtures show; where a later case differs, the fidelity check reports it, and the importer never silently chooses:
- how "lowest reference" orders, by code point or naturally (`R9` against `R10`);
- when a unit letter joins a reference.

### D5. Sheet instances and paths

**The roots.** Top-level sheets come from `.kicad_pro`, in the order listed there:
- each top-level sheet's instance path is `/<uuid>` and its name path is `/<name>/`;
- a lone `.kicad_sch` is its own root, with instance path `/<file uuid>` and name path `/`.

**Hierarchical sheets.** A sheet symbol extends the instance path with its uuid and the name path with its `Sheetname`. A sheet file used by several sheet symbols is imported once per instance.

**References and units.** A placed symbol's reference and unit come from its `instances` entry for the current instance path. A missing entry is reported, and the `Reference` property is used instead.

### D6. Identity on the persistent identifier

**Components.** A component is the set of placed units sharing one reference.
- **External identifier:** the path KiCad writes on the board's footprint: the sheet-symbol uuids below the top-level sheet, then the symbol uuid of its lowest placed unit. For a symbol on a top-level sheet that is `/<symbol uuid>`, as PCBGolf's board shows.
- **Canonical path:** built from the same uuids, as `kicad.<uuid hex>…`. Renumbering references therefore moves no identifier, even without a mapping table.
- **Names:** the reference is the designator and the display name.

**Pins.** A pin's external identifier is `<component external identifier>:<number>`.

**Nets.**
- A named net keys on its name.
- An unnamed net keys on the external identifier of its lowest member pin, ordered by persistent identifier rather than reference. Renumbering leaves it where it is, and a change to its membership moves it only when the lowest pin changes.
- KiCad's name is always an alias.

Alternative considered: key on the reference, as the netlist adapter does. Rejected by RFC 12 Section 14.4, because re-annotation would re-mint every identifier.

### D7. The new record fields

These fields follow RFC 3 version 1.4. Each is written only when set, so existing records are byte for byte unchanged. Each has a decoder in `fang/rehydrate.py`.

- **Component:**
  - `symbol`: the library identifier and the sorted units placed;
  - `value_text`, kept verbatim;
  - `fitted`: `do_not_populate`, `exclude_from_bom`, `exclude_from_board`, `exclude_from_position_files`, and `exclude_from_simulation`, which are all five of KiCad's flags;
  - `sheets`: the name paths the units sit on.
- **Pin:** `electrical_type`, and `no_connect`, which is written only when true.
- **Net:** `net_class`, from the project's net class assignments and patterns.

**Fields that become traits.**
- The `Footprint` property `library:name` becomes a `Footprint` trait.
- The `Manufacturer` and `MPN` fields become a `Sourcing` trait.

**The remaining fields.** Every other field, `Datasheet` included, is stored verbatim under the component's `kicad` extension, as `fields`. A field value that differs between the units of one component is reported.

Alternative considered: report each unstored field, as the netlist adapter does. Rejected: PCBGolf carries about five hundred field occurrences, which would bury the losses that matter. Storing them is lossless, and it is what RFC 12 Section 14.4 means by "carry into state".

### D8. Presentation records, apart

`fang/presentation.py` defines four placements, following RFC 3 Section 17.3:

| Placement | Entity it draws | Fields |
|---|---|---|
| Symbol | component | sheet, unit, position, rotation, mirroring |
| Label | net | sheet, kind, position, rotation, shape |
| Power | net | sheet, position, rotation, library identifier |
| No-connect | pin | sheet, position |

**Storage.**
- Positions carry `unit: mm`, and magnitudes are decimal strings.
- The document holds `schema_version`, the `snapshot` it was imported against, and the placements grouped by sheet and ordered by entity.
- It is written canonically to `.copperhead/presentation/schematic.json`.

**What reads it.**
- It is not in the snapshot hash, and identity derivation never reads it.
- `diff_presentation(before, after)` reports a `presentation_changed` for every placement that moved.

**Not recorded.** Wires and junctions follow from connectivity, as RFC 12 Section 11.7 allows.

Alternative considered: presentation inside entity records. Rejected by RFC 3 Section 17.3, and it would put a symbol's drag into the snapshot hash.

### D9. Fidelity against KiCad's netlist

`compare_with_netlist(result, netlist_text)` produces a fidelity report.

**How nets match.** Nets are matched by membership, as sets of reference and pin.

**What it lists:**
- components present on only one side;
- nets whose membership has no match, each with the differing pins;
- matched nets whose names differ.

**Where it runs.** The tests run it on every fixture. `fang import --netlist` runs it and exits non-zero on any difference.

### D10. Import passes the gate

`fang import` does the following:
1. reads the project, reusing the workspace's mapping table when one exists;
2. adds the entities as transactions through the commit gate, as `fang build` does;
3. persists the snapshot, the mapping table, the import report, and the presentation document.

Re-importing unchanged sources lands on the same identifiers and the same snapshot hash.

### D11. What is reported

**Reported one by one**, because each is electrical or identity-bearing:
- buses, bus entries, and bus aliases;
- net class directive labels and rule areas;
- a symbol at an angle that is not a right angle;
- a pin using an alternate function;
- a missing instance entry;
- a `lib_id` with no embedded definition;
- a format version older than 20231120.

**Reported once per kind per sheet**, with a count, because they are drawing only: text, text boxes, polylines, rectangles, circles, arcs, images, and tables.

### D12. Fixtures are ours

**Generation.** `tests/fixtures/kicad_schematic/generate.py` writes small schematics from symbols it defines itself, never from KiCad's libraries. One fixture isolates each rule:
- orientations;
- junctions;
- label priority and ties;
- power symbols;
- multi-unit symbols;
- no-connect markers;
- a hierarchy with a reused sheet;
- several top-level sheets.

**Oracles.** Beside each fixture sits the netlist `kicad-cli` 10.0.4 exports from it. The suite compares imports with the committed oracles, so CI needs no KiCad. Regenerating needs `kicad-cli` and is skipped without it.

**Several top-level sheets.** `kicad-cli` cannot export a project with several top-level sheets, so that fixture's oracle comes from the same design written as one root holding each sheet as a sub-sheet. The comparison checks membership, and names other than the sheet-path prefix of local names.

PCBGolf's design carries no license, so its sheets are used only as a local, uncommitted check.

### D13. Schema version

Records gain optional fields, so the minor version moves. This change takes the next free minor after PR #4 and PR #6 land.

## Risks / Trade-offs

- **A naming edge case the fixtures miss.** Fidelity reports it rather than hiding it, and the PCBGolf check runs the whole project against the board's 302 net names.
- **Format drift across KiCad versions.** The reader checks `version` and reports an unsupported one. Fixtures pin KiCad 10.0.4.
- **Multi-unit footprint linking.** That the board links a multi-unit part through its lowest unit's uuid is an inference; PCBGolf has no multi-unit part to confirm it. It is asserted by a fixture only once a board fixture exists, and flagged until then.
- **Presentation and records drifting apart.** The presentation document names the snapshot it was imported against, and a consumer given a document for another snapshot refuses it.
- **RFC wording.** The implementation follows KiCad where RFC 12 Section 14.4 reads otherwise, and the difference is recorded below.

## Migration Plan

No migration. Earlier records carry none of the new fields and load unchanged. A project imported with the netlist adapter keeps its identifiers keyed on references. Re-importing it from the schematic mints UUID-keyed identifiers, and the import report says so.

## Open Questions

- **RFC 12 Section 14.4 wording.** It should say that a label or a junction on a wire's middle connects, and that a pin or a wire end there does not. Raise this as an erratum on copperhead-rfcs.
- **Reference ordering.** Is "lowest reference" in a pin-derived name ordered naturally or by code point? A fixture with `R9` and `R10` settles it during implementation.
- **Multi-unit footprint link.** Which unit's uuid links a multi-unit part to its footprint? This is confirmed once a board fixture exists.
- **Local power symbols.** Does a local power symbol (`(power local)`) name its net with a sheet prefix? A fixture settles it.
