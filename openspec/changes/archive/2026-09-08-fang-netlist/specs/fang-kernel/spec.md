# fang-kernel Specification

## ADDED Requirements

### Requirement: Net Inference

Nets SHALL be inferred as the equivalence classes that conductive pin
connections form, and SHALL represent logical connectivity independent of
visual labels. An inferred net SHALL carry provenance naming the connections it
was inferred from.

#### Scenario: Connected pins form one net

- **WHEN** three pins are connected in a chain
- **THEN** one net contains all three

#### Scenario: Unconnected pins form separate nets

- **WHEN** two pins are never connected
- **THEN** they belong to different nets

#### Scenario: A non-conductive connection does not merge nets

- **WHEN** two pins are joined by a dependency or containment connection
- **THEN** they remain in separate nets

#### Scenario: Net inference is reproducible

- **WHEN** the same graph is compiled twice
- **THEN** the nets, their names, and their membership are identical

### Requirement: Deterministic Designator Assignment

Designators SHALL be assigned deterministically from the canonical semantic path
so that the same design always yields the same designator for the same part.
Each part type's declared prefix SHALL be used, and numbering SHALL start at one
within each prefix.

#### Scenario: The same design yields the same designators

- **WHEN** a design is compiled twice
- **THEN** every designator is unchanged

#### Scenario: Numbering is per prefix

- **WHEN** a design holds two resistors and one capacitor
- **THEN** the designators are `R1`, `R2`, and `C1`

#### Scenario: An authored designator is preserved

- **WHEN** a part already carries a designator
- **THEN** assignment keeps it and does not renumber it

### Requirement: The Netlist Is A Projection

A netlist SHALL name the graph snapshot it was compiled from, and SHALL contain
no component, pin, or net absent from that snapshot. Compiling a netlist SHALL
NOT mutate the graph.

#### Scenario: A netlist names its parent snapshot

- **WHEN** a netlist is compiled
- **THEN** it records the content hash of the snapshot it came from

#### Scenario: Compiling does not mutate the graph

- **WHEN** a netlist is compiled from a snapshot
- **THEN** the snapshot's content hash is unchanged afterwards

#### Scenario: Emission is byte-identical for unchanged input

- **WHEN** the same netlist is emitted twice
- **THEN** the two files are byte-identical
