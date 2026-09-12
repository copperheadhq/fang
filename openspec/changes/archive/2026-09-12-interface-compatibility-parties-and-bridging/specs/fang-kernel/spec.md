# fang-kernel Specification

## MODIFIED Requirements

### Requirement: Typed Interfaces, Ports, Buses, and Domains

An interface SHALL be a first-class entity representing a typed connection
surface: a named group of signals with roles, electrical parameters, a
direction where one applies, and compatibility rules. A port is an interface
instance owned by a component, module, or architecture block. A bus is an
interface whose participants are many rather than two. A domain groups entities
sharing a voltage, ground, isolation, or timing reference.

A link is one interface connection together with the ports that participate in
it. A port is a party to the link when its interface declares at least one
electrical parameter; a port whose interface declares none — a passive pad, a
test point — is a wire on the link rather than a party to it. A link SHALL
continue through a part that declares it bridges the terminals in the path,
and SHALL stop at a part that declares no such bridge. A link over a bus SHALL
merge every connection whose ports share a member into one link, so every
port on the bus is a party to the same link rather than to a separate one per
connection.

The kernel SHALL ship a catalogue of typed interfaces and SHALL allow projects
to define their own. The catalogue SHALL cover at least I2C, SPI, UART, USB 2,
CAN, RS-485, PWM, quadrature encoder, power input, power output, analog input,
analog output, motor phase, JTAG, serial wire debug, clock, and reset.

#### Scenario: System-level connectivity is recorded between interfaces

- **WHEN** an architecture-level or system-level connection is authored
- **THEN** it is recorded between interfaces rather than between pins

#### Scenario: Same-type interfaces are not automatically compatible

- **WHEN** two interfaces of the same catalogue type are connected
- **THEN** compatibility is decided by the compatibility checks, not by the
  type match alone

### Requirement: Interface Compatibility Checks

Interface compatibility SHALL be a deterministic check class, run only over the
parameters every party to the link declares. The kernel SHALL evaluate at
least: source VOH(min) against sink VIH(min) plus margin; source VOL(max)
against sink VIL(max) less margin; source current capability against sink
demand; bus voltage domain compatibility across every party; pull-up supply
validity for every party; open-drain and open-collector requirements; and
protocol, rate, and addressing compatibility.

#### Scenario: A check with unknown inputs returns undecided

- **WHEN** an input to a compatibility check has value status `unknown`
- **THEN** the check returns an undecided result naming the missing input
- **AND** the check does not pass by default

#### Scenario: A datasheet-sourced check cites its evidence

- **WHEN** a compatibility check reads an input that came from a datasheet
- **THEN** the check cites the evidence entity supporting it, so that the
  result is reproducible when the datasheet claim is revised

### Requirement: Interface Compatibility Evaluation

The compatibility check SHALL evaluate logic-level margin, current capability,
voltage-domain agreement, pull-up supply validity, open-drain requirements, and
protocol, rate, and addressing agreement, over the parameters every party to
the link declares. A check whose inputs are unknown SHALL return undecided
naming the missing input. A link with fewer than two parties has nothing to
compare and yields no result.

#### Scenario: A logic-level shortfall fails

- **WHEN** a source's VOH minimum is below the sink's VIH minimum plus margin
- **THEN** the check fails and names both parameters

#### Scenario: An unknown input returns undecided naming what is missing

- **WHEN** a sink's VIH minimum is unknown
- **THEN** the check returns undecided and names `vih_min` as the missing input
- **AND** it does not pass by default

#### Scenario: A bus checks every participant

- **WHEN** three parties share a bus and one is in a different voltage domain
- **THEN** the check reports the mismatch and names the party

#### Scenario: An open-drain bus without a pull-up fails

- **WHEN** an open-drain interface has no pull-up declared on the bus
- **THEN** the check fails naming the missing pull-up

#### Scenario: A datasheet-sourced input cites its evidence

- **WHEN** a compatibility input came from a datasheet
- **THEN** the result cites the evidence entity that supplied it

#### Scenario: A non-party is not asked for a fact it doesn't declare

- **WHEN** a resistor pad sits on a link whose other end declares logic
  levels and a voltage domain
- **THEN** the resistor is not asked for those parameters, because its
  interface declares none
- **AND** the link has only one party, so the check yields no result at all

#### Scenario: A series part joins the two interfaces it stands between

- **WHEN** two ports of the same interface type are joined only through parts
  that each declare they bridge the terminals in the path
- **THEN** the two ports are treated as the two ends of one link
- **AND** they are compared with each other, not with the parts between them

#### Scenario: A mismatch carries through a series part

- **WHEN** the two ends of a series-bridged link disagree on a checked
  parameter, such as their voltage domain
- **THEN** the check reports the mismatch between the two ends
- **AND** the parts bridging the path between them are not asked about it

#### Scenario: A part that declares no bridge ends the link

- **WHEN** two ports of the same interface type are joined only through a
  part that declares no bridge between the terminals in the path, such as a
  transistor
- **THEN** the interface does not continue through that part
- **AND** the two ports are not treated as ends of one link

### Requirement: The Part Model

A part SHALL separate its logical identity, its selected vendor part, its
package, its sourcing identity, its parameterization, and its physical instance.
A part SHALL declare a designator prefix, and a generic part SHALL carry no
vendor identity until one is selected. A part SHALL declare which pairs of its
own terminals it bridges — conducts between — if any; nothing else in the
graph records conduction through a part's own body.

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

#### Scenario: A part records what it bridges

- **WHEN** a two-terminal part such as a resistor is declared
- **THEN** the component entity records that its two terminals are bridged
- **AND** a part such as a transistor or a connector that declares no bridge
  records none

### Requirement: The Shipped Interface Catalogue

The kernel SHALL ship interface definitions covering at least I2C, SPI, UART,
USB 2, CAN, RS-485, PWM, quadrature encoder, power input, power output, analog
input, analog output, motor phase, JTAG, serial wire debug, clock, and reset.
Each definition SHALL own its member signals, their roles, its electrical
parameters, and its compatibility rules, and a project SHALL be able to define
its own. Every digital interface SHALL declare a voltage-domain parameter,
which the bus voltage-domain check depends on for that family.

#### Scenario: Every named interface is present with its signals

- **WHEN** the catalogue is enumerated
- **THEN** each named interface is present
- **AND** each carries at least one required signal with a role

#### Scenario: A project defines its own interface

- **WHEN** a project declares an interface type the catalogue does not carry
- **THEN** it participates in lowering and compatibility exactly as a shipped one
