# fang-kernel Specification

## ADDED Requirements

### Requirement: Declarative Module Composition

A module SHALL be declared as an ordinary Python class whose body assigns
parameters, nodes, and child modules. Each declaration is a template: every
instance of the owning module SHALL receive its own child rather than sharing
the one written in the class body.

Declaration order SHALL be the order the class body assigns, so that elaboration
does not depend on dictionary iteration or on memory address.

#### Scenario: Two instances do not share a child

- **WHEN** a module declaring a child module is instantiated twice
- **THEN** each instance owns a distinct child with a distinct identity

#### Scenario: A system is the root module of a design

- **WHEN** a design is elaborated
- **THEN** the root of the canonical semantic path is the system, and every
  entity beneath it is named by its position in the module tree

#### Scenario: Composition is connection between declared surfaces

- **WHEN** a parent connects two children
- **THEN** the connection is recorded between their declared surfaces rather
  than between internal implementation detail

### Requirement: Parameter Declaration And Reference

A parameter SHALL be declared with its unit, and a bare number SHALL NOT be
accepted as one. Reading a parameter off a module instance SHALL yield a
reference usable in a constraint expression, carrying the entity identifier, the
attribute name, and the declared dimension.

Assigning a quantity to a declared parameter SHALL record a value; assigning a
quantity of the wrong dimension SHALL be an elaboration error.

#### Scenario: A unit literal builds a quantity

- **WHEN** a program writes `3.3 * V`
- **THEN** the result is a scalar quantity of 3.3 volts whose magnitude is a
  decimal, not a binary float

#### Scenario: An undeclared parameter value is unknown, not defaulted

- **WHEN** a declared parameter is never assigned
- **THEN** its value is recorded with status `unknown`

#### Scenario: A dimensionally wrong assignment fails at elaboration

- **WHEN** a parameter declared in volts is assigned a quantity in amperes
- **THEN** elaboration fails with a `UNIT` diagnostic naming the parameter and
  its source location

### Requirement: Declared Constraints Are Not Evaluated Eagerly

`require()` SHALL record a constraint against the module that declared it rather
than evaluating it. A comparison between a parameter reference and a quantity
SHALL build an expression node rather than returning a Python boolean.

#### Scenario: A comparison builds an expression

- **WHEN** a program writes `require(self.vm.voltage <= 60 * V)`
- **THEN** a comparison expression node is constructed and stored
- **AND** no truth value is computed at declaration time

#### Scenario: A constraint that cannot yet be decided is recorded as undecided

- **WHEN** a declared constraint references a parameter whose value is unknown
- **THEN** evaluating it later yields undecided
- **AND** it is not silently treated as satisfied

### Requirement: The Connect Operator

Connecting two surfaces SHALL record a typed connection entity with provenance
naming the source location of the connection, and SHALL NOT mutate either
surface.

#### Scenario: Connecting records a typed connection

- **WHEN** a program connects a power output to a power input
- **THEN** a connection entity is recorded whose kind is `power`

#### Scenario: Connecting incompatible surface kinds is refused

- **WHEN** a program connects surfaces whose kinds cannot form a connection
- **THEN** elaboration fails with an `ELAB` diagnostic naming both surfaces

### Requirement: The Elaboration Result

Elaboration SHALL return exactly a graph snapshot, a tool plan, and the
diagnostics it produced. It SHALL NOT return the Python object graph, and the
Python object graph SHALL NOT be reachable from the snapshot.

#### Scenario: A failed elaboration returns no partial graph

- **WHEN** elaboration produces an error-severity diagnostic
- **THEN** the result carries the diagnostics and no snapshot

#### Scenario: Re-elaborating unchanged source is byte-identical

- **WHEN** the same program is elaborated twice
- **THEN** the two snapshots serialize to identical bytes

#### Scenario: Every entity carries the source location that produced it

- **WHEN** any entity is created by elaboration
- **THEN** it carries the file and line of the declaration that produced it

### Requirement: Elaboration Sandbox Enforcement

The sandbox SHALL make undeclared input unavailable rather than merely
discouraged. Network access SHALL be denied outright during elaboration, and a
file input SHALL be readable only when it was declared and hashed into the
snapshot.

#### Scenario: A network call during elaboration fails

- **WHEN** a program opens a socket during elaboration
- **THEN** the attempt raises and elaboration fails with an `ELAB` diagnostic

#### Scenario: An undeclared file input is unavailable

- **WHEN** a program reads a file it did not declare
- **THEN** the read fails rather than silently succeeding

#### Scenario: A declared input is hashed into the snapshot

- **WHEN** a program declares a file input
- **THEN** the snapshot records the input's identifier and its content hash

#### Scenario: Randomness requires a declared seed

- **WHEN** a program uses randomness without declaring a seed
- **THEN** elaboration fails
- **AND** a declared seed is recorded in the snapshot

### Requirement: Trait Registration And Enumeration

A trait SHALL declare the protocol it satisfies, and the kernel SHALL enumerate
the entities carrying a given trait without instantiating any backend.

#### Scenario: Traits are enumerable by protocol

- **WHEN** the kernel is asked for every entity carrying a simulation trait
- **THEN** it answers from recorded traits alone
- **AND** no simulator, layout engine, or renderer is constructed

#### Scenario: A trait attaches to an entity rather than widening its class

- **WHEN** a component gains a footprint, a model, and sourcing metadata
- **THEN** each attaches as a trait
- **AND** the component's class is unchanged
