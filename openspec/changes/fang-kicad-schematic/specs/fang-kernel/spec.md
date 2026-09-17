## ADDED Requirements

### Requirement: The KiCad Schematic Adapter Derives Connectivity From The Drawing

The KiCad schematic adapter SHALL import a KiCad project, with its top-level
sheets taken from the project file, or a single schematic file. It SHALL produce
kernel entities, a mapping table, presentation records, and an import report,
using the symbol definitions the schematic embeds.

It SHALL derive connectivity from the drawing, as KiCad does:

- a pin is placed at its position after the symbol's position, rotation,
  mirroring, and unit are applied;
- wire endpoints, pins, labels, power symbol pins, sheet pins, and junctions at
  one point connect;
- a label or a junction lying on a wire between its endpoints connects to that
  wire;
- local labels of one name connect within a sheet instance;
- global labels and global power symbols of one name connect across every sheet
  of the project, including every top-level sheet;
- a hierarchical label connects to the sheet pin of its name on the sheet
  instance above it.

It SHALL produce every net KiCad produces for the same sources, and each net
SHALL carry the name KiCad gives it.

#### Scenario: A pin connects where a rotated and mirrored symbol places it

- **WHEN** a symbol is placed rotated by 0, 90, 180, or 270 degrees, unmirrored or
  mirrored about either axis, with a wire ending at each of its pins
- **THEN** each pin is a member of the net its wire belongs to

#### Scenario: A wire end on another wire's middle connects only through a junction

- **WHEN** a wire's end meets another wire between that wire's endpoints with no
  junction there
- **THEN** the two wires do not connect
- **AND** with a junction at that point, they connect

#### Scenario: A label on a wire's middle connects

- **WHEN** a label sits on a wire between the wire's endpoints
- **THEN** the pins on that wire belong to the net the label names

#### Scenario: Global labels and power symbols join top-level sheets

- **WHEN** two top-level sheets of one project each carry a global label or a power
  symbol of the same name
- **THEN** the pins each one touches are members of one net

#### Scenario: A hierarchical label joins its sheet pin

- **WHEN** a sub-sheet carries a hierarchical label and the sheet symbol above it
  carries a sheet pin of the same name
- **THEN** the pins on either side of the sheet pin share one net
- **AND** a sheet used twice yields a separate net for each instance

#### Scenario: A net takes the name KiCad gives it

- **WHEN** one net carries a global label, a power symbol, and a local label
- **THEN** the net is named by the global label
- **AND** between two labels of equal priority it is named by the lower name
- **AND** a local or hierarchical label's name is prefixed with its sheet path

#### Scenario: An unnamed net and a lone pin take KiCad's generated names

- **WHEN** a net has no label and no power symbol
- **THEN** it is named from its lowest member pin in KiCad's `Net-(...)` form
- **AND** a pin connected to nothing is named in KiCad's `unconnected-(...)` form

#### Scenario: Only a multi-unit symbol's placed units contribute pins

- **WHEN** a multi-unit symbol is placed with one of its units not placed
- **THEN** the pins of the unplaced unit are not imported
- **AND** the component records the units that are placed

#### Scenario: A construct the adapter does not resolve is reported

- **WHEN** a sheet carries a bus, a bus entry, or a net class directive label
- **THEN** the import report names the construct and where it appeared
- **AND** the import still produces every entity it could recover

### Requirement: Imported Presentation State Is Stored Apart

A schematic import SHALL record presentation state:

- for every placed symbol unit, its sheet, position, rotation, mirroring, and
  unit;
- for every label, power symbol, and no-connect marker, its position and
  orientation.

Each placement SHALL be keyed by the identifier of the entity it draws, and every
coordinate SHALL carry its unit. Presentation state SHALL be stored apart from the
canonical record stream. It SHALL NOT take part in identity derivation or in the
snapshot hash. A change confined to presentation state SHALL classify as a
presentation change.

#### Scenario: Moving a symbol changes only presentation

- **WHEN** a symbol is moved on its sheet with its connections intact, and the
  project is imported again
- **THEN** every identifier and the snapshot hash are unchanged
- **AND** comparing the two presentation documents reports a presentation change
  naming the component

#### Scenario: Presentation state holds no fact the records lack

- **WHEN** an imported project's presentation document is deleted
- **THEN** its connectivity, values, and identifiers are unchanged

### Requirement: Schematic Import Fidelity Is Checked Against The CAD Tool's Netlist

The adapter SHALL compare a schematic import with a netlist KiCad exported for the
same sources. It SHALL report every difference in the component set, in a net's
pin membership, and in a net's name.

#### Scenario: A faithful import reports no difference

- **WHEN** a schematic is imported and compared with the netlist KiCad exported
  from it
- **THEN** the fidelity report is empty

#### Scenario: A difference is named

- **WHEN** the import and the netlist disagree on one net's membership or name
- **THEN** the fidelity report names the net and the pins or names that differ

## MODIFIED Requirements

### Requirement: The Part Model

A part SHALL separate its logical identity, its selected vendor part, its
package, its sourcing identity, its parameterization, and its physical instance.
A part SHALL declare a designator prefix, and a generic part SHALL carry no
vendor identity until one is selected.

A part MAY carry a symbol reference: the CAD library identifier of the symbol that
draws it, and the units it places. A symbol reference carries no electrical
meaning.

A part SHALL record its fitted state where its source states one:

- whether it is populated;
- whether it is excluded from the bill of materials, the board, the position
  files, or simulation.

A part that is not populated SHALL remain in the circuit model with its
connectivity. A part imported with value text SHALL keep that text verbatim.

#### Scenario: A generic part has no vendor identity

- **WHEN** a generic resistor is declared with only a resistance
- **THEN** its manufacturer and part number are absent rather than invented

#### Scenario: Selecting a vendor part records it as sourcing

- **WHEN** a manufacturer and part number are selected for a part
- **THEN** they attach as a sourcing trait rather than replacing the part's
  logical identity

#### Scenario: A designator prefix is declared per part type

- **WHEN** a resistor, a capacitor, and an integrated circuit are declared
- **THEN** their designator prefixes are `R`, `C`, and `U`

#### Scenario: A do-not-populate part keeps its connectivity

- **WHEN** a component marked do-not-populate is imported
- **THEN** it is a component entity whose pins remain members of their nets
- **AND** its fitted state records that it is not populated

#### Scenario: Value text is kept verbatim

- **WHEN** a component is imported with the value text `100k`
- **THEN** the component records `100k` as its value text
- **AND** no parameter is asserted from that text

### Requirement: The Pin Model

A part SHALL declare its pins with their canonical electrical roles, and SHOULD
preserve the vendor's pin names. A part SHALL declare which pins can carry which
interface signal, and MAY name several candidates for one signal.

A pin SHALL keep its number and its name as separate fields where its source
distinguishes them. A pin MAY carry the electrical type its CAD symbol declares.
The electrical type SHALL NOT be treated as the canonical role.

A pin MAY carry no-connect intent. No-connect intent SHALL be distinguishable
from a pin merely being unconnected. A pin with no-connect intent SHALL NOT share
a net with another pin, and an import that finds one doing so SHALL report it.

#### Scenario: A pin preserves its vendor name

- **WHEN** a part declares a pin named `PB8`
- **THEN** the pin entity records `PB8` as its vendor name alongside its role

#### Scenario: A signal may name several candidate pins

- **WHEN** a part declares two pins able to carry one interface signal
- **THEN** both are recorded as candidates for that signal

#### Scenario: An imported pin keeps its electrical type apart from its role

- **WHEN** a pin is imported from a symbol that declares it `power_in`
- **THEN** the pin records `power_in` as its electrical type
- **AND** no canonical role is asserted from it

#### Scenario: A no-connect marker is intent, not absence

- **WHEN** a pin under a no-connect marker and a pin with nothing attached are
  imported
- **THEN** the first records no-connect intent and the second does not
- **AND** neither shares a net with another pin

### Requirement: The External Identifier Mapping Table

An import SHALL record every external identifier in an explicit mapping table,
alongside the canonical identifier it was given. The table SHALL be part of the
persisted state, and re-importing unchanged sources SHALL reuse the same canonical
identifiers.

Where a source carries a persistent object identifier, such as a KiCad symbol
UUID, an import SHALL key the entity on that identifier rather than on a reference
designator.

#### Scenario: An external identifier maps to a canonical one

- **WHEN** a component is imported carrying the reference `R1`
- **THEN** the mapping table records `R1` against the canonical identifier
- **AND** `R1` is not used as the canonical identifier

#### Scenario: Re-importing unchanged sources reuses identifiers

- **WHEN** the same file is imported twice
- **THEN** every canonical identifier is unchanged

#### Scenario: An identifier the exporter wrote is recovered

- **WHEN** a file carries a canonical identifier written by an earlier export
- **THEN** the import reuses it rather than minting a new one

#### Scenario: Renumbering references preserves identity

- **WHEN** a schematic's components are re-annotated with new reference
  designators, and the schematic is imported again
- **THEN** every component keeps its canonical identifier
- **AND** each component's designator is its new reference

### Requirement: The Workspace Layout

A project's kernel state SHALL persist beside its sources, under a workspace
directory holding:

- the canonical record stream;
- a manifest;
- declared sources;
- cited evidence;
- presentation state;
- a cache.

The manifest SHALL record the schema version, the revision, and the snapshot
hash. Presentation state SHALL be stored apart from the canonical record stream.

#### Scenario: The workspace round-trips a design

- **WHEN** a snapshot is written and read back
- **THEN** every entity is recovered as a typed entity, with its identity,
  parameters, traits, and provenance intact
- **AND** no program is executed to read it

#### Scenario: The manifest records what produced the state

- **WHEN** a workspace is written
- **THEN** the manifest names the schema version, the revision, the compiler
  version, and the snapshot hash

#### Scenario: Deleting the cache loses no engineering fact

- **WHEN** the cache directory is deleted and the project is rebuilt
- **THEN** the resulting snapshot hash is unchanged

#### Scenario: The mapping table persists between runs

- **WHEN** a project is imported, saved, and imported again
- **THEN** the second import reuses the canonical identifiers of the first

#### Scenario: Presentation state lives apart from the design records

- **WHEN** a schematic import is persisted
- **THEN** its presentation document is written under the workspace's
  presentation directory
- **AND** the record stream and the snapshot hash are those the import produces
  without it

### Requirement: Semantic Diff Classification

The kernel SHALL support semantic change detection, and a diff SHALL classify each
change. The classification SHALL distinguish at least:

- component added, removed, or changed;
- connection added or removed;
- parameter or value changed;
- interface changed;
- pin assignment changed;
- domain changed;
- topology intent changed;
- model or trait changed;
- requirement changed;
- decision changed;
- evidence changed;
- verification status changed;
- constraint changed;
- placement, routing, or other physical change;
- rename.

#### Scenario: Presentation change is separable from electrical change

- **WHEN** a change alters only coordinates or presentation
- **THEN** the diff separates it from a change that alters electrical meaning

#### Scenario: A diff carries the impact of a change

- **WHEN** a parameter changes
- **THEN** the diff SHOULD name the calculations, requirements, and verifications
  the change invalidates

#### Scenario: A change to presentation records alone is a presentation change

- **WHEN** two presentation documents for one snapshot differ only in where a
  symbol or a label is drawn
- **THEN** the diff classifies each difference as a presentation change, naming
  the entity drawn
- **AND** it reports no electrical change

### Requirement: The Command Surface

The command line SHALL expose building, checking, exporting, and importing a
design. Each command SHALL exit non-zero when the work it names did not succeed.

#### Scenario: Building a program writes the workspace

- **WHEN** `build` runs against a Fang program
- **THEN** the workspace holds the design records and the manifest
- **AND** the command exits zero

#### Scenario: A failing check exits non-zero

- **WHEN** `check` runs against a design with a failing hard constraint
- **THEN** the command reports the failure and exits non-zero

#### Scenario: A failed elaboration reports its diagnostics

- **WHEN** a program fails to elaborate
- **THEN** the command prints each diagnostic with its code and source location
- **AND** it exits non-zero without writing a partial workspace

#### Scenario: Importing a KiCad project writes the workspace

- **WHEN** `import` runs against a KiCad project
- **THEN** the workspace holds the design records, the manifest, the mapping
  table, the import report, and the presentation document
- **AND** the command exits zero when the only findings are constructs the report
  names

#### Scenario: A fidelity difference fails the import

- **WHEN** `import` runs with a netlist KiCad exported for the same sources, and
  the two disagree
- **THEN** the command prints each difference
- **AND** it exits non-zero
