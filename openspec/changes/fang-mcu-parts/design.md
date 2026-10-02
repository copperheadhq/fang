# Design: MCU Parts — Peripheral Instances, Selectors and Bus Addresses

## Context

See [proposal.md](proposal.md) for motivation. The normative text is copperhead
RFC 12 version 1.3, Sections 7.3 and 7.4, and RFC 3 version 1.5, Section 9.3
([copperheadhq/copperhead-rfcs#6](https://github.com/copperheadhq/copperhead-rfcs/pull/6));
this document is informative. What exists today:

- `InterfacePort(interface, *, role, name, direction, **parameters)` turns every
  keyword it does not know into a parameter value, and
  `elaborate._port_parameters` checks a declared parameter's dimension against
  the interface's parameter table. A bare integer given for a declared
  parameter would fail that check with an `AttributeError` rather than a
  diagnostic.
- `PinMap({"i2c.scl": ["PB8", "PB6"], ...})` lives on the `Part` class. The
  snapshot does not hold the candidates; it holds the outcome — a `Connection`
  per lowered signal, `derived_from_interface` naming the interface
  connection, and a `Decision` where a choice existed.
- `lowering._choose` picks each signal's pin in declared order from the
  candidates of the port the connection names. Nothing says which of the chip's
  controllers a candidate belongs to, so a single `i2c` port whose candidates
  span I2C1 and I2C2 is expressible and indistinguishable from a correct one:
  SCL can land on one controller and SDA on the other, and the lowering
  accepts it.
- `compatibility._check_protocol` already fails a multi-drop bus on which two
  ports carry the same known `address` parameter. Nothing populates it: the
  `i2c_bus` example declares `address` as a part parameter and writes the three
  pairwise `require(a != b)` constraints by hand, and no port in the tree
  carries an address.
- Nets are not entities. They are inferred from the snapshot's conductive
  connections by `netlist.compile_netlist`, deterministically.
- `Pin("PB8", role="clock", number="61")` already keeps the vendor name and the
  package pad apart, and `Part.select(manufacturer=, mpn=)` attaches a vendor
  identity as sourcing without replacing the part's logical identity.

The defects this closes are the ones firmware meets first at bring-up: the pin
choice is recorded and never checked against what the firmware configures, and
an I2C address exists only as a `#define` in the firmware, so two devices at
one address, or a strap pin tied the wrong way, cannot be seen by any check the
kernel runs.

## Goals / Non-Goals

**Goals:**

- Put the controller instance, the selector of each chosen pin and each
  device's address in the graph, where checks — and later the emulation plan —
  read them, with no inference from pin names.
- Feed the existing addressing rule rather than add a second one.
- Leave every part without selectors or addresses, and every committed example
  output, unchanged apart from the snapshot hash.

**Non-Goals:**

- No emulator, firmware binding or platform model; that is `fang-emulation`.
- No change to `i2c_bus`. Its hand-written uniqueness constraints are the point
  that example makes; moving its addresses onto ports is a separate edit.
- No vendor parts in the standard library, whose requirement is generic parts.
- No persisting of candidate pin maps in the snapshot. RFC 12 asks that a
  lowering be re-derivable from graph state; fang re-derives it from the
  program today, and closing that is its own change.

## Decisions

### A port names its instance; two controllers are two ports

`InterfacePort` takes a `peripheral` keyword, consumed before the parameter
catch-all, and the `Port` entity gains an optional `peripheral` field. A part
whose I2C is available on two controllers declares `i2c1` and `i2c2`. Because a
lowering already draws only on the named port's candidates, the mixed
assignment is ruled out by construction once a port means one controller.

*Alternative considered:* tagging each candidate with its instance and teaching
`_choose` to pick a consistent set. It moves a fact of the part into the
lowering's search, and it still lets one port mean two controllers.

### A selector is part data, recorded on the lowered connection

A candidate mapping may be `{"PB8": AF(4), "PB6": AF(4)}`. `Selector("AF4")` is
the general form — vendors spell the routing differently — and `AF(n)` is
sugar for the STM32 family's. A `PinMap` that carries any selector names the
`Cites` declaration on the same part that its selectors come from
(`evidence="af_table"`); elaboration refuses one that does not.

The lowering records the chosen pin's selector on the `Connection` it makes, as
`selectors: {<pin id>: {"selector": "AF4", "evidence": <evidence id>}}`.

*Alternative considered:* the selector on the `Pin` entity. A pin can serve
several ports with different selectors — PB8 is I2C1's SCL at AF4 and a timer
channel at another — so the selector is a property of the assignment, not of
the pin.

*Alternative considered:* the selector on the `Decision`. A decision exists
only where a choice existed; a single candidate still has a selector.

### An address is a dimensionless port parameter, or a strap

The I2C interface declares `address` with unit `1`, so `I2CPort(address=0x44 *
addr)` is checked like any other parameter and stored as an explicit value.
`I2CPort(address=0x44)` is refused with the bare-number diagnostic the language
already gives elsewhere, naming the parameter, rather than the `AttributeError`
it would raise today.

`Strap("ADDR", {"GND": 0x48 * addr, "VDD": 0x49 * addr, "SDA": 0x4A * addr,
"SCL": 0x4B * addr})` keys each address by a pin *of the device itself*, which
is how datasheets state it. Elaboration resolves the pin names to pin
identifiers and stores the strap on the `Port` entity as `address_strap`; the
port's `address` parameter is then absent, so the strap is the one place the
fact lives.

*Alternative considered:* keying the strap by "ground", "supply" and "bus
signal". It needs a global notion of which net is ground, which fang finds
today only inside the SPICE lowering. The device's own pins answer the same
question with nothing inferred.

### A strapped address is resolved where nets exist, by one function

`resolve_address(snapshot, port)` infers the netlist, finds the strap pin's net,
and returns the address of the one strap-map pin sharing it — or an unknown
value whose reason names the strap pin, and both pins when two share it. The
addressing rule in `_check_protocol` calls it for each participant; a port with
neither a fixed address nor a strap is not addressed and is skipped, so a bus
controller is never reported. `fang-emulation` will call the same function for
its plan, so the check and the emulator cannot disagree about an address.

*Alternative considered:* resolving during elaboration and storing the value.
Elaboration does not infer nets, and storing the result beside the strap would
be the same fact held twice.

### The parts live in an example

`STM32F401RE` and `HS3001` are vendor parts and go in `examples/sensor_node/`,
as `sensor_board` keeps its MCU. The MCU declares `power`, `i2c1` (instance
`I2C1`, PB8/PB9 preferred over PB6/PB7, all at AF4), `usart2` (instance
`USART2`, PA2/PA3 at AF7) and a `status` signal on PA5, with vendor names and
LQFP64 pad numbers taken from ST's datasheet for the STM32F401xD/xE and cited by
table and page. The sensor's address is fixed at 0x44, cited from Renesas's
HS300x datasheet. Electrical thresholds not yet read off a datasheet are left
unknown or carried as an `Assumes`, never guessed. The board adds the pull-ups,
decoupling, an LED with its series resistor on PA5, a console header on USART2,
and a power header.

### Diagnostics go in the `IFACE` area

New codes, allocated with `_allocate` at the bottom of the `IFACE` block: a
selector with no evidence, and a strap naming a pin the part does not have. An
address given as a bare number reuses `UNIT_DIMENSION_MISMATCH`, the code
`Parameter` already raises for one, and so does a fixed address that is a range
or a tolerance, as a strap's non-scalar address already was: a device answers on
one address, and one the board selects is a strap. An unresolved strap is not an
elaboration error; it is an undecided check result, because the board is legal
and its answer is unknown.

### The schema version moves to 1.2

The spec's "Schema Versioning and Compatibility" makes a new optional key an
additive change that increments the minor version. `Port.peripheral`,
`Port.address_strap` and `Connection.selectors` are omitted from `as_dict()`
when absent, so no committed output changes except the snapshot hash the suite
already normalizes.

The delta carries the move as a MODIFIED "Schema Versioning and Compatibility",
which now names the version the specification defines. The `schema_version: 1.1`
line of the main spec's Project Root block sits in the preamble, outside every
requirement, so neither a delta nor `openspec archive` can reach it; archiving
this change edits that one line by hand, to agree with the requirement.

The number is fang's own, and it diverges from RFC 3's. RFC 3 version 1.5
numbers schema 1.2 as the import schema of its version 1.4 and schema 1.3 as
the one adding these port elements, the firmware binding and the verification
record. Fang cannot claim 1.3, because a 1.3 record is a 1.2 record, and two of
schema 1.2's additions are mandatory and fang does not write them: a trait MUST
be serialized inside the record of its entity, under a `traits` key (RFC 3
Section 5), and fang keeps traits in a registry beside the root; and a
provenance record that changes an existing entity MUST carry a `fields` list
(Section 14), and fang's records have none, though verification re-entry
appends one to the verification it answers. Fang's 1.2 is therefore 1.1 with
these port keys, which is neither RFC 3's 1.2 nor its 1.3. It moves to RFC 3's
numbering in the change that writes traits and the fields list.

## Implementation notes

What the decisions above left open, settled while implementing them. None
changes a decision.

- `resolve_address` returns a fixed address exactly as recorded, and a resolved
  strap as an inferred value whose `source` is the device pin that selected it,
  at confidence 1. Its unknown values carry their reason as the value's
  `rationale`, which `Value.unknown(reason)` now accepts. It takes a snapshot
  or an entity mapping.
- The addressing rule also passes, naming each address and its port, when every
  addressed participant's address is known and no two overlap, so a bus with
  one addressed device shows the rule decided. It still says nothing on a bus
  where no participant is addressed.
- Addresses are compared by overlap, not by equality, because a transaction can
  still set a range where elaboration refuses one. Two equal scalars fail; two
  overlapping intervals that are not one scalar, a range beside an address
  inside it or two equal ranges, are undecided, naming both ports, since which
  address each answers on is not known. A range is written as a datasheet
  writes it, 0x48..0x4B.
- A conflicting address is an address not yet known, never no address:
  `resolve_address` gives the resolution's chosen value, or an unknown value
  whose reason names the candidates' sources, so the rule is undecided rather
  than passing over the port. `fang-emulation`'s plan refuses an unknown
  address with that reason as it refuses any other.
- The compatibility check's scope holds, for each participant with a strap, the
  strap pin, the pins of its map, and every pin, conductive connection and
  stated net on the strap pin's net, since re-tying that pin changes an address
  without touching a port. The gate takes every check class's scope over the
  head as well as the candidate, since a removed entity is in only the head's;
  removing the strap's connection therefore runs the rule, which is undecided.
- The bare-number refusal covers every interface parameter, not only
  `address`; a bare number was never a valid value for any of them.
- `Connection.references()` includes the evidence its selectors cite, and
  `Port.references()` the pins its strap names, so a dangling one fails
  referential integrity like any other reference.
- A selector is recorded on every pin connection that lands on the candidate,
  including a single-wire connection such as a pull-up reaching `i2c1.scl`,
  because that connection is an assignment of the same port signal.
- The example's HS3001 is modelled with all six pins. Its application circuit
  needs a 0.1 uF capacitor on VC and one on VDD, so the board carries
  `env_bypass` and `vc_bypass` beside the MCU's `bypass`. The bus pull-up
  parameters sit on the sensor's port, where its datasheet requires them. The
  console header is connected port to port, passing USART2 through, so its
  pins carry the board's signal names.

## Verified datasheet facts

Read from the vendors' own PDFs on 2026-10-02. PDF page numbers equal the
printed ones in both.

ST, *STM32F401xD/xE datasheet*, DS10086 Rev 5 (February 2026; the cover still
reads "preliminary data"):

| Fact | Value | Locator |
| --- | --- | --- |
| LQFP64 pins | PA2 16, PA3 17, PA5 21, PB6 58, PB7 59, PB8 61, PB9 62, VSS 63, VDD 64 | Table 8, pp. 38-44; Figure 12, p. 35 |
| Other LQFP64 supply pins | VDD 19, 32, 48; VSS 18, 31, 47; VSSA/VREF- 12; VDDA/VREF+ 13; VCAP_1 30; VBAT 1; NRST 7; BOOT0 60 | Table 8 |
| Pin type | PA2, PA3, PA5, PB6-PB9 are FT I/O | Table 8; Table 7, p. 38 |
| I2C1 | SCL AF4 on PB6 and PB8; SDA AF4 on PB7 and PB9 | Table 9, p. 46 |
| USART2 | TX AF7 on PA2; RX AF7 on PA3 | Table 9, p. 45 |
| FT input levels | VIL max 0.3 VDD, VIH min 0.7 VDD, 1.7 V to 3.6 V | Table 54, p. 91 |
| CMOS output at 8 mA | VOL max 0.4 V, VOH min VDD - 0.4 V, 2.7 V to 3.6 V | Table 55, p. 94 |
| I2C rate | standard mode to 100 kHz, fast mode to 400 kHz | Section 6.3.19, p. 98 |
| VDD | 1.7 V to 3.6 V | Table 14, p. 60 |
| Decoupling | 6 x 100 nF + 1 x 4.7 uF across the VDD pins | Figure 18, p. 57 |
| STM32F401RET6 | R 64 pins, E 512 Kbytes, T LQFP, 6 -40 to 85 C | Table 87, p. 132; Table 88, p. 133 |

Renesas, *HS3xxx Datasheet*, R36DS0045EU0101 Rev 1.01 (17 June 2024):

| Fact | Value | Locator |
| --- | --- | --- |
| Address | 0x44, the only 7-bit address the device responds to; custom on request | Section 7.2, p. 10 |
| Package and pins | 6-LGA 3.0 x 2.41 mm: 1 SCL, 2 SDA, 3 VC, 4 VDD, 5 NC, 6 VSS | Section 1.2, Figure 1, p. 4 |
| Application circuit | pull-ups to VDD, 2.2 kOhm typical; 0.1 uF VC to ground; 0.1 uF VDD to ground | Figure 13, p. 9; Section 7, p. 10 |
| I2C rate | fSCL up to 400 kHz | Table 1, p. 10 |
| Supply | 2.3 V to 5.5 V on the cover and in Section 3; the recommended-conditions table leaves the minimum blank | p. 1; Section 2.2, p. 5 |
| I/O logic levels | not stated anywhere in the datasheet | - |
| Orderable part | `HS3001` | Section 13, p. 17 |

Not verified: a per-pin decoupling rule for LQFP64, and a VCAP_1 value or ESR
specific to one-VCAP packages; the example does not model either. Renesas's
product pages list the HS3001 as obsolete; that is lifecycle information, not
a datasheet fact, and nothing in the example depends on it.

## Risks / Trade-offs

- [A selector copied wrongly from the datasheet] → every selector cites its
  table; the example's README names the table; `fang-emulation` will compare
  the firmware's register writes against it, which turns a wrong selector into
  a visible mismatch rather than a silent one.
- [A strap map keyed by pin name diverges from the datasheet's wording] → the
  names are the part's own vendor pin names, which the part already preserves,
  and a name the part does not have is refused at elaboration.
- [Resolving straps re-infers the netlist inside the check] → inference is
  deterministic and already runs for the netlist projection; a bus has few
  strapped devices.

## Migration Plan

Additive. Existing parts, examples and snapshots are untouched except for the
schema version and the hash that covers it. `python examples/regenerate.py`
writes the new example's outputs; the suite discovers it.
