# fang-kernel Specification

## ADDED Requirements

### Requirement: The Part Model

A part SHALL separate its logical identity, its selected vendor part, its
package, its sourcing identity, its parameterization, and its physical instance.
A part SHALL declare a designator prefix, and a generic part SHALL carry no
vendor identity until one is selected.

#### Scenario: A generic part has no vendor identity

- **WHEN** a generic resistor is declared with only a resistance
- **THEN** its manufacturer and part number are absent rather than invented

#### Scenario: Selecting a vendor part records it as sourcing

- **WHEN** a manufacturer and part number are selected for a part
- **THEN** they attach as a sourcing trait rather than replacing the part's
  logical identity

#### Scenario: A designator prefix is declared per part type

- **WHEN** a resistor, a capacitor, and an integrated circuit are declared
- **THEN** their designator prefixes are `R`, `C`, and `U`

### Requirement: The Standard Part Library

The kernel SHALL ship generic parts covering at least resistor, capacitor,
inductor, diode, LED, fuse, crystal, transistor, voltage regulator, connector,
test point, and mounting hole. Each SHALL declare its pins, its pin map, and the
parameters its type carries.

#### Scenario: A two-pin passive lowers to its two pins

- **WHEN** two generic two-pin parts are connected
- **THEN** the connection lowers to a pin connection on each part

#### Scenario: Each library part declares the parameters its type carries

- **WHEN** a capacitor is declared
- **THEN** it carries capacitance, and a voltage rating it may leave unknown

#### Scenario: A part with no electrical function still participates

- **WHEN** a mounting hole is declared
- **THEN** it is a part with a mechanical surface and no electrical pins
