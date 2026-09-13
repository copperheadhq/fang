## ADDED Requirements

### Requirement: The KiCad Netlist Adapter Uses KiCad's Own Form

The KiCad netlist adapter SHALL read the netlist form KiCad writes, in which every
field of the export, design, component, net, and node elements is a nested
`(key "value")` list, and SHALL write that same form. It SHALL continue to read
the flat `"key" "value"` form earlier Fang releases wrote. A netlist KiCad
exported SHALL import with every component, net, and node the file carries, and
each net SHALL keep the name the file gives it.

#### Scenario: A netlist KiCad exported imports whole

- **WHEN** a netlist written by `kicad-cli sch export netlist` is imported
- **THEN** every component, net, and node in the file is recovered
- **AND** every net carries the name the file gives it

#### Scenario: A netlist in the earlier flat form still imports

- **WHEN** a netlist in the flat key-value form an earlier Fang release wrote is
  imported
- **THEN** it yields the components, nets, and nodes the file carries

#### Scenario: An emitted netlist nests every field as KiCad does

- **WHEN** a netlist is emitted
- **THEN** the version, every design field, and every field of a component, a
  component field, a property, a net, and a node is written as a nested
  `(key "value")` list
- **AND** no element carries its fields as flat key-value atoms

#### Scenario: An emitted netlist reads back whole

- **WHEN** an emitted netlist is imported
- **THEN** every component, net, and node it carries is recovered

#### Scenario: A source-named single-pin net survives the round trip

- **WHEN** an imported netlist names a net that has exactly one node
- **AND** the import is compiled back into a netlist with no transaction between
- **THEN** that net is emitted with its name and its one node

#### Scenario: An inferred single-pin net is still not a net

- **WHEN** a program leaves a pin connected to nothing
- **THEN** the compiled netlist contains no net for that pin

## MODIFIED Requirements

### Requirement: Imports Report What They Could Not Represent

An adapter SHALL report every construct it could not represent and SHALL NOT
silently discard semantics. The report SHALL name the construct and where it
appeared.

#### Scenario: An unsupported construct is reported

- **WHEN** a file carries a construct the adapter does not model
- **THEN** the import report names it
- **AND** the import still produces the entities it could recover

#### Scenario: A lossless import reports no loss

- **WHEN** a file contains only constructs the adapter models
- **THEN** the report is empty

#### Scenario: Missing semantics are unknown rather than invented

- **WHEN** an imported component has no value in the file
- **THEN** its value is recorded as unknown
- **AND** no intent is fabricated for it

#### Scenario: A construct accepted but not stored is reported

- **WHEN** a file carries a component field, a datasheet, a component property
  other than the identifier an earlier export wrote, a net class, or a node's pin
  function or pin type
- **AND** the adapter does not store that construct
- **THEN** the import report names the construct and where it appeared
