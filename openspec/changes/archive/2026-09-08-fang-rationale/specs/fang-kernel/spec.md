# fang-kernel Specification

## ADDED Requirements

### Requirement: Rationale Authored From The Program

A Fang program SHALL be able to create requirements, assumptions, decisions,
alternatives, evidence, and calculations where the engineering happens, rather
than in a separate document that drifts. Each SHALL become an entity carrying
the source location that declared it.

#### Scenario: A requirement declared in a program becomes an entity

- **WHEN** a program declares a requirement
- **THEN** a requirement entity exists carrying its statement, state, and source
  location

#### Scenario: A decision names its alternatives and the requirements it serves

- **WHEN** a program records a decision between two parts
- **THEN** the decision entity names the selection, the rejected alternatives,
  the requirements it serves, and the evidence it cites

#### Scenario: A claim without a citation is recorded as an assumption

- **WHEN** a program states a claim and cites no evidence
- **THEN** it is recorded as an assumption rather than as evidence

### Requirement: Calculations Are First-Class

A calculation SHALL be an entity recording its expression, its inputs, its
result, and the requirement it serves, so that a later change can invalidate it.

#### Scenario: A calculation records what it depends on

- **WHEN** a calculation is declared over two parameters
- **THEN** the entity names both as inputs

#### Scenario: Changing an input invalidates the calculation

- **WHEN** a parameter a calculation depends on changes
- **THEN** the semantic diff names that calculation as invalidated

### Requirement: Verification Results Form A Graph

A verification SHALL be an entity naming what it verifies, the method used, the
evidence it rests on, and its result, so that requirement coverage is answerable
from graph structure alone.

#### Scenario: A verification links a requirement to its evidence

- **WHEN** a verification is recorded against a requirement
- **THEN** the requirement's coverage is answerable without inference

#### Scenario: An uncovered requirement is visible

- **WHEN** a requirement has no verification
- **THEN** a coverage query names it as uncovered

### Requirement: Impact Propagation

A change SHALL propagate to the calculations, requirements, and verifications
that depend on what changed, and the diff SHALL name them.

#### Scenario: A parameter change names the requirement it puts at risk

- **WHEN** a parameter under a constraint that serves a requirement changes
- **THEN** the diff names that requirement as impacted

#### Scenario: A verified requirement whose evidence changed is reported

- **WHEN** evidence a verification rests on changes
- **THEN** the affected verification and requirement are named
