# fang-kernel Specification

## ADDED Requirements

### Requirement: The View Specification

A view SHALL be defined by what it includes and what it annotates, and the
compiled specification SHALL be recorded with the view so the question a diagram
answers is inspectable.

#### Scenario: A view records the specification that produced it

- **WHEN** a view is compiled
- **THEN** it carries the specification's name, its included kinds, and its
  annotations

#### Scenario: A view names the snapshot it projects

- **WHEN** a view is compiled from a snapshot
- **THEN** it records that snapshot's content hash

### Requirement: The Required Views

The implementation SHALL provide the system, interconnect, power, ground,
interfaces, and safety views, each answering one engineering question from graph
facts alone.

#### Scenario: Every required view is available by name

- **WHEN** the view registry is enumerated
- **THEN** all six required views are present

#### Scenario: The power view shows only power connectivity

- **WHEN** the power view is compiled over a design with power and signal nets
- **THEN** its edges are power edges and its signal edges are absent

#### Scenario: The ground view distinguishes intent from net equivalence

- **WHEN** the ground view is compiled over a design carrying a topology
  constraint
- **THEN** the constraint appears as an annotation distinct from the net's
  membership

### Requirement: A View Contains Nothing Absent From Its Snapshot

A view SHALL be generated only from facts in the graph, and SHALL expose the
completeness of what it shows.

#### Scenario: Every node and edge traces to an entity

- **WHEN** any view is compiled
- **THEN** every node and every edge names an entity present in the snapshot

#### Scenario: A view reports what is unknown in it

- **WHEN** a view includes an entity carrying unknown parameters
- **THEN** the view reports that incompleteness rather than hiding it

#### Scenario: Repeated generation is identical

- **WHEN** a view is compiled twice from unchanged graph state
- **THEN** the two view graphs are identical

### Requirement: The Layout Boundary

Input to layout SHALL carry only layout information: node identity, node
dimensions, ports, edges, hierarchy, and hints. It SHALL NOT carry engineering
meaning, and no engineering decision SHALL depend on layout output.

#### Scenario: The layout request carries no engineering meaning

- **WHEN** a view graph is prepared for layout
- **THEN** the request holds identity, dimensions, ports, edges, hierarchy, and
  hints, and nothing else

#### Scenario: Layout output becomes a positioned view graph

- **WHEN** layout returns positions
- **THEN** they are applied to the view graph, and rendering remains the
  kernel's own

#### Scenario: Placement seeds are presentation state

- **WHEN** a placement seed is stored
- **THEN** it is kept separately from canonical identity
- **AND** changing it classifies as a presentation change
