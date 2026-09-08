# fang-kernel Specification

## ADDED Requirements

### Requirement: Simulation Plan Validation

Plan compilation SHALL validate that every selected component has a compatible
model, that pin maps are complete, that unsupported components are explicitly
abstracted, that model distribution constraints are respected, and that
simulator options are deterministic and recorded. A plan failing any of these
SHALL be rejected with the reason.

#### Scenario: A component with no compatible model rejects the plan

- **WHEN** a selected component carries no model for the chosen backend
- **THEN** the plan is rejected naming that component
- **AND** no substitute model is used

#### Scenario: An incomplete pin map rejects the plan

- **WHEN** a model's pin map does not cover the component's pins in scope
- **THEN** the plan is rejected naming the missing pins

#### Scenario: An unsupported component may be explicitly abstracted

- **WHEN** a component without a model is explicitly listed as abstracted
- **THEN** the plan compiles and records the abstraction as an assumption

#### Scenario: A restricted model's terms are respected

- **WHEN** a model forbids redistribution and the plan would embed it
- **THEN** the plan records the restriction and references the model rather than
  inlining it

#### Scenario: Simulator options are deterministic and recorded

- **WHEN** a plan is compiled twice with the same inputs
- **THEN** the two plans are identical, including their options and seed

### Requirement: SPICE Lowering

The kernel SHALL lower a simulation plan into the simulator's native netlist
rather than binding to a wrapper library. The lowering SHALL be deterministic
for a given plan.

#### Scenario: A plan lowers to a netlist naming its nets and devices

- **WHEN** a plan over a resistor divider is lowered
- **THEN** the netlist carries a device line per component and an analysis line
  for the requested analysis

#### Scenario: Lowering is deterministic

- **WHEN** the same plan is lowered twice
- **THEN** the two netlists are byte-identical

#### Scenario: Backend assumptions stay out of component definitions

- **WHEN** a component is defined
- **THEN** it carries models and no backend-specific syntax

### Requirement: Backends Are Reached Across A Process Boundary

A simulator SHALL be reached across a process boundary, and its version SHALL be
recorded with every result. A backend that is not installed SHALL report
unsupported rather than producing a substitute result.

#### Scenario: A missing simulator reports unsupported

- **WHEN** the chosen backend is not installed
- **THEN** the run reports unsupported and names the backend
- **AND** no result is fabricated

#### Scenario: A result records the backend and its version

- **WHEN** a run completes
- **THEN** the normalized result names the backend and the version that ran

### Requirement: Normalized Simulation Results

A result SHALL record the plan, the backend and its version, the models used and
their provenance, the assumptions applied, and the coverage the run does not
provide. Sample data SHALL be referenced as an artifact rather than inlined.

#### Scenario: A result names its full context

- **WHEN** a run completes
- **THEN** its normalized form names the plan, the backend version, the models,
  the assumptions, and the coverage gaps

#### Scenario: A simulation pass is not proof of physical correctness

- **WHEN** a simulation passes its assertions
- **THEN** it is recorded as a finding with a confidence
- **AND** it is not recorded as proof

#### Scenario: Sample data is referenced, not inlined

- **WHEN** a run produces waveform samples
- **THEN** the result references them as an artifact

### Requirement: Verification Level Selection

The kernel SHOULD select the cheapest verification level that can decide a
question, over equation checks, symbolic analysis, behavioural simulation,
circuit simulation, and specialized external analysis. The selected level SHALL
be recorded with the question, so that a cheap answer is distinguishable from an
expensive one.

#### Scenario: A question an equation can decide does not run a simulator

- **WHEN** a question is decidable by calculation
- **THEN** the equation level is selected

#### Scenario: A question needing analog detail selects circuit simulation

- **WHEN** a question needs analog detail no equation covers
- **THEN** the circuit-simulation level is selected
