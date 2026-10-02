## ADDED Requirements

### Requirement: A Port May Be One Peripheral Instance

A part's interface port SHALL be able to name the peripheral instance it is,
and the instance SHALL be recorded on the port entity. Each candidate pin of a
port SHALL be able to carry the selector that routes the port's signal to that
pin, and a part that declares any selector SHALL name the evidence its
selectors were taken from. When a lowering chooses a pin that carries a
selector, the pin connection it records SHALL carry that selector and the
evidence for it. A lowering SHALL assign the signals of one connection only
from the candidates of the port that connection names. A package pad number
SHALL NOT be used as, or used to derive, a port pin index.

#### Scenario: The instance is recorded on the port

- **WHEN** a part declares an I2C port as the peripheral instance `I2C1`
- **THEN** the port entity in the snapshot names `I2C1`

#### Scenario: Two controllers are two ports

- **WHEN** a part offers I2C on two controllers, declared as two ports, and a
  connection names one of them
- **THEN** every pin the lowering assigns for that connection is a candidate
  of the named port

#### Scenario: The chosen pin's selector reaches the graph

- **WHEN** a lowering assigns `i2c1.scl` to a candidate declared with selector
  `AF4`
- **THEN** the pin connection it records carries `AF4` for that pin
- **AND** it names the evidence entity the part cited for its selectors

#### Scenario: A selector without evidence is refused

- **WHEN** a part declares selectors on its candidates and names no evidence
  for them
- **THEN** elaboration fails with an `IFACE` diagnostic naming the part

#### Scenario: Candidates without selectors lower as before

- **WHEN** a part declares its candidates as a list of pin names
- **THEN** the lowering, the pin connections and the decisions it records are
  identical to those of the previous release

### Requirement: An Addressed Bus Device Carries Its Address

The port of an addressed bus device SHALL be able to carry its address, either
as a fixed dimensionless value or as a strap: one of the device's pins together
with the address each of the device's own pins selects when the strap is tied
to it. A strapped address SHALL be resolved from the board's nets, by the
device pin that shares the strap pin's net. The compatibility check's
addressing rule SHALL read these addresses for every participant of a
multi-drop bus. A port that declares no address SHALL NOT be treated as
addressed.

#### Scenario: Two devices at one address fail

- **WHEN** two devices on one I2C bus declare the fixed address 0x48
- **THEN** the compatibility check fails and names both ports

#### Scenario: A strap tied to ground selects its address

- **WHEN** a device's strap pin shares a net with the device's own ground pin,
  and the strap maps that pin to 0x48
- **THEN** the device's address is resolved as 0x48, and the addressing rule
  compares it like a fixed address

#### Scenario: A strap on no net is reported, not resolved

- **WHEN** a device's strap pin is on no net, or on a net none of the pins in
  its strap map shares
- **THEN** the device's address is unknown
- **AND** the addressing rule returns undecided naming the strap pin

#### Scenario: An ambiguous strap is reported

- **WHEN** a device's strap pin shares a net with two pins of its strap map
- **THEN** the device's address is unknown
- **AND** the addressing rule returns undecided naming the strap pin and both
  pins

#### Scenario: A controller with no address is not reported

- **WHEN** a bus controller's port declares no address
- **THEN** the addressing rule neither fails nor returns undecided on its
  account

#### Scenario: An address is not a bare number

- **WHEN** a port is given an address as a plain integer rather than a
  dimensionless quantity or a strap
- **THEN** elaboration fails with a diagnostic naming the parameter
