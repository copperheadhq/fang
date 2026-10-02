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
`Parameter` already raises for one. An unresolved strap is not an elaboration
error; it is an undecided check result, because the board is legal and its
answer is unknown.

### The schema version moves to 1.2

The spec's "Schema Versioning and Compatibility" makes a new optional key an
additive change that increments the minor version. `Port.peripheral`,
`Port.address_strap` and `Connection.selectors` are omitted from `as_dict()`
when absent, so no committed output changes except the snapshot hash the suite
already normalizes.

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
