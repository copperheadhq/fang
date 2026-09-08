# fang-kernel Specification

## ADDED Requirements

### Requirement: The Shipped Interface Catalogue

The kernel SHALL ship interface definitions covering at least I2C, SPI, UART,
USB 2, CAN, RS-485, PWM, quadrature encoder, power input, power output, analog
input, analog output, motor phase, JTAG, serial wire debug, clock, and reset.
Each definition SHALL own its member signals, their roles, its electrical
parameters, and its compatibility rules, and a project SHALL be able to define
its own.

#### Scenario: Every named interface is present with its signals

- **WHEN** the catalogue is enumerated
- **THEN** each named interface is present
- **AND** each carries at least one required signal with a role

#### Scenario: A project defines its own interface

- **WHEN** a project declares an interface type the catalogue does not carry
- **THEN** it participates in lowering and compatibility exactly as a shipped one

### Requirement: The Pin Model

A part SHALL declare its pins with their canonical electrical roles, and SHOULD
preserve the vendor's pin names. A part SHALL declare which pins can carry which
interface signal, and MAY name several candidates for one signal.

#### Scenario: A pin preserves its vendor name

- **WHEN** a part declares a pin named `PB8`
- **THEN** the pin entity records `PB8` as its vendor name alongside its role

#### Scenario: A signal may name several candidate pins

- **WHEN** a part declares two pins able to carry one interface signal
- **THEN** both are recorded as candidates for that signal

### Requirement: Deterministic Pin Assignment

Lowering an interface connection SHALL assign pins deterministically for a given
graph state and part selection: the same graph SHALL always produce the same
assignment, independent of iteration order or the order connections were
written.

#### Scenario: The same graph lowers identically every time

- **WHEN** the same design is elaborated twice
- **THEN** every pin assignment is identical

#### Scenario: One pin does not carry two signals

- **WHEN** two signals name the same candidate pin
- **THEN** the assignment gives the pin to exactly one of them and finds another
  for the other, or fails explicitly if none remains

#### Scenario: A lowered connection names the interface connection it came from

- **WHEN** an interface connection lowers to pin connections
- **THEN** each pin connection carries provenance naming the interface connection
- **AND** the lowering is re-derivable from the same graph state

### Requirement: A Pin Choice Is A Recorded Decision

Where a part offers alternative pin assignments and the lowering selects one, the
choice SHALL be recorded as a design decision entity naming the alternatives it
rejected.

#### Scenario: An alternative assignment becomes a decision

- **WHEN** a signal has more than one candidate pin and one is chosen
- **THEN** a decision entity records the choice, its rationale, and the rejected
  alternatives

#### Scenario: A single candidate is not a decision

- **WHEN** a signal has exactly one candidate pin
- **THEN** no decision entity is created, because no choice existed

### Requirement: An Incomplete Lowering Fails Explicitly

A lowering that cannot be completed SHALL fail with a diagnostic naming the
unsatisfiable signal, and SHALL NOT produce a partial pin mapping.

#### Scenario: A required signal with no pin fails the lowering

- **WHEN** a required interface signal has no candidate pin on one side
- **THEN** lowering fails with `IFACE-0001` naming that signal
- **AND** no pin connection from that lowering is recorded

#### Scenario: Interfaces disagreeing on membership fail the lowering

- **WHEN** two connected interfaces do not share the required signal set
- **THEN** lowering fails with `IFACE-0002` naming the disagreement

### Requirement: Interface Compatibility Evaluation

The compatibility check SHALL evaluate logic-level margin, current capability,
voltage-domain agreement across every participant, pull-up supply validity,
open-drain requirements, and protocol, rate, and addressing agreement. A check
whose inputs are unknown SHALL return undecided naming the missing input.

#### Scenario: A logic-level shortfall fails

- **WHEN** a source's VOH minimum is below the sink's VIH minimum plus margin
- **THEN** the check fails and names both parameters

#### Scenario: An unknown input returns undecided naming what is missing

- **WHEN** a sink's VIH minimum is unknown
- **THEN** the check returns undecided and names `vih_min` as the missing input
- **AND** it does not pass by default

#### Scenario: A bus checks every participant

- **WHEN** three participants share a bus and one is in a different voltage domain
- **THEN** the check reports the mismatch and names the participant

#### Scenario: An open-drain bus without a pull-up fails

- **WHEN** an open-drain interface has no pull-up declared on the bus
- **THEN** the check fails naming the missing pull-up

#### Scenario: A datasheet-sourced input cites its evidence

- **WHEN** a compatibility input came from a datasheet
- **THEN** the result cites the evidence entity that supplied it
