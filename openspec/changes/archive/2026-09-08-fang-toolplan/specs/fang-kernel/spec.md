# fang-kernel Specification

## ADDED Requirements

### Requirement: Tool Terminal Statuses

Every tool call SHALL end in exactly one terminal status: succeeded, failed,
unsupported, skipped, or cancelled. A plan requesting an operation no tool
supports SHALL return unsupported rather than a degraded attempt.

#### Scenario: An unregistered tool returns unsupported

- **WHEN** a plan names a tool the registry does not carry
- **THEN** the call ends unsupported
- **AND** no substitute is attempted

#### Scenario: A failing tool ends failed and stops dependents

- **WHEN** a tool raises
- **THEN** its call ends failed
- **AND** a later call conditioned on its success is skipped rather than run

### Requirement: Conditions Resolve In The Operation Phase

A symbolic condition recorded during elaboration SHALL be resolved when the
operation phase runs. A call whose condition resolves false SHALL be skipped,
and the skip SHALL be recorded rather than silently dropped.

#### Scenario: A false condition skips the call

- **WHEN** an export is conditioned on a check passing and the check failed
- **THEN** the export is skipped and the run records why

#### Scenario: A true condition runs the call

- **WHEN** the check passes
- **THEN** the export runs

### Requirement: Tool Calls Are Idempotent

A tool call SHALL be idempotent for the same graph snapshot, content-addressed
inputs, configuration, and seed. Running the same plan against the same snapshot
twice SHALL produce the same results.

#### Scenario: The same plan against the same snapshot repeats its result

- **WHEN** a plan is executed twice against one snapshot
- **THEN** every result is identical

#### Scenario: A different snapshot is a different run

- **WHEN** the snapshot changes
- **THEN** the run is not served from the previous one's results

### Requirement: The Operation Phase Does Not Mutate Canonical State

Operations SHALL execute against immutable snapshots and SHALL NOT mutate the
graph. A realization implying a semantic change SHALL return it through a
transaction.

#### Scenario: Running a plan leaves the graph unchanged

- **WHEN** a plan runs to completion
- **THEN** the graph's head is unchanged

#### Scenario: An implied semantic change returns through the gate

- **WHEN** a tool produces a realization implying a parameter change
- **THEN** that change reaches canonical state only as a committed transaction
