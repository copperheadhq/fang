# fang-kernel Specification

## ADDED Requirements

### Requirement: The Workspace Layout

A project's kernel state SHALL persist beside its sources under a workspace
directory holding the canonical record stream, a manifest, declared sources,
cited evidence, and a cache. The manifest SHALL record the schema version, the
revision, and the snapshot hash.

#### Scenario: The workspace round-trips a design

- **WHEN** a snapshot is written and read back
- **THEN** every entity is recovered with its identity intact

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

### Requirement: The Command Surface

The command line SHALL expose building, checking, and exporting a design, and
each command SHALL exit non-zero when the work it names did not succeed.

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
- **AND** exits non-zero without writing a partial workspace
