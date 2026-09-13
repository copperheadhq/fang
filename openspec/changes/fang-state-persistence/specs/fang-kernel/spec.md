## ADDED Requirements

### Requirement: A Persisted Snapshot Reloads Without Running A Program

The kernel SHALL rebuild a snapshot from its record stream and manifest into typed
entities and their traits without executing any program. Every entity kind, trait
protocol, and value type the kernel serializes SHALL have a registered decoder
that inverts its serialization, so that a reloaded snapshot reserializes
byte-identically and has the content hash its manifest records. A record the
kernel cannot type SHALL be preserved verbatim and reported rather than dropped,
and a malformed record SHALL refuse the whole load.

#### Scenario: A reloaded snapshot has the hash it was saved with

- **WHEN** a snapshot is written to a workspace and read back with no program
  executed
- **THEN** the rebuilt snapshot's content hash equals the snapshot hash in the
  manifest
- **AND** its record stream is byte-identical to the design file

#### Scenario: Every entity kind round-trips through its decoder

- **WHEN** an entity of any kind the kernel defines is serialized and then decoded
- **THEN** the decoded entity serializes to the same canonical bytes

#### Scenario: A netlist compiled from a reloaded snapshot matches the elaboration

- **WHEN** a program's snapshot is written, read back, and compiled into a netlist
  with no traits passed beside it
- **THEN** the netlist equals the one compiled from the elaboration, footprints
  and sourcing included

#### Scenario: Traits are enumerable from a reloaded snapshot

- **WHEN** a reloaded snapshot is asked for every entity carrying a protocol
- **THEN** it answers from the reloaded traits
- **AND** no program is executed and no backend is constructed

#### Scenario: An unknown record is preserved and reported

- **WHEN** the record stream carries an entity of a kind no decoder is registered
  for, a trait of an unregistered protocol, or a known record with a key its
  decoder does not model
- **THEN** that record is kept verbatim and reserializes byte-identically
- **AND** the load report names it

#### Scenario: A malformed record refuses the whole load

- **WHEN** a record cannot be decoded, such as one missing a required field
- **THEN** the load fails with a diagnostic naming the record
- **AND** no partial snapshot is returned

#### Scenario: A stream that does not match its manifest is refused

- **WHEN** the rebuilt snapshot's content hash differs from the manifest's
  snapshot hash
- **THEN** the load fails with a diagnostic naming both hashes

#### Scenario: A design written before traits were persisted still loads

- **WHEN** a workspace written under schema version 1.1 is read
- **THEN** it loads, and its entities carry no traits

## MODIFIED Requirements

### Requirement: Traits As The Extension Mechanism

Behaviour SHALL attach to entities through traits rather than through
progressively wider classes. A trait SHALL declare the protocol it satisfies,
and the kernel SHALL be able to enumerate the entities carrying a given trait
without instantiating any backend. A trait SHALL be state: it SHALL persist inside
the record of the entity that carries it, named by its protocol, and SHALL NOT
exist only beside a snapshot.

#### Scenario: Traits supplying models carry their own provenance

- **WHEN** a trait supplies a simulation, behaviour, thermal, cost, supply, or
  reliability model
- **THEN** the trait carries its own provenance, because a model's applicability
  is an engineering claim rather than a fact about the component

#### Scenario: A model result is not evidence beyond its declared conditions

- **WHEN** a consumer reads a model result
- **THEN** it does not treat the result as evidence beyond the conditions the
  model declares

#### Scenario: A trait persists inside its entity's record

- **WHEN** a snapshot whose entities carry traits is persisted
- **THEN** each entity's record carries its traits under `traits`, keyed by
  protocol
- **AND** the snapshot's content hash covers them

#### Scenario: A trait change is classified as a trait change

- **WHEN** a change alters only the traits of an entity
- **THEN** the semantic diff classifies it as a model or trait change

### Requirement: The Workspace Layout

A project's kernel state SHALL persist beside its sources under a workspace
directory holding the canonical record stream, a manifest, declared sources,
cited evidence, and a cache. The manifest SHALL record the schema version, the
revision, and the snapshot hash.

#### Scenario: The workspace round-trips a design

- **WHEN** a snapshot is written and read back
- **THEN** every entity is recovered as a typed entity with its identity,
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
