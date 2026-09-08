# fang-kernel Specification

## ADDED Requirements

### Requirement: The External Identifier Mapping Table

An import SHALL record every external identifier in an explicit mapping table
alongside the canonical identifier it was given. The table SHALL be part of the
persisted state, and re-importing unchanged sources SHALL reuse the same
canonical identifiers.

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

### Requirement: One Safe Round Trip

A design imported from CAD, changed through one committed transaction, and
emitted again SHALL differ only by that change. No unrelated electrical change
SHALL appear.

#### Scenario: An unchanged import re-emits unchanged

- **WHEN** a file is imported and immediately re-emitted with no transaction
- **THEN** the components and nets are unchanged

#### Scenario: One safe edit changes only what it names

- **WHEN** one component's value is changed through a transaction and the design
  is re-emitted
- **THEN** only that component's value differs
- **AND** every net and every other component is unchanged
