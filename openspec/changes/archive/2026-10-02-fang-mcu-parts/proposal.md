# MCU Parts: Peripheral Instances, Selectors and Bus Addresses

This change implements copperhead RFC 12, *The Copperhead Hardware Kernel and
Fang Language Standard*, version 1.3, Sections 7.3 and 7.4, and the port
elements of RFC 3 version 1.5, Section 9.3. Both revisions are open as
[copperheadhq/copperhead-rfcs#6](https://github.com/copperheadhq/copperhead-rfcs/pull/6);
the change may proceed while it is open, and claims conformance only to the
version that merges. It is the prerequisite of `fang-emulation`, and is useful
with no emulator at all.

## Why

A board records which pin of a microcontroller carries SCL and never says which
of the chip's I2C controllers that pin belongs to, or what has to be written to
route the signal there; and the address a device answers on lives only in the
firmware, so the compatibility check that already compares addresses on a bus
is never given one. Both are facts of the board, both decide whether the board
works, and both are invisible to every check fang runs today.

## What Changes

- A port can name the peripheral instance it is: `i2c1 = I2CPort(peripheral="I2C1", ...)`.
  A part offering I2C on two controllers declares two ports, so a connection
  lowers only onto one controller's pins.
- A pin candidate can carry the selector that routes the signal to it —
  `PinMap({"i2c1.scl": {"PB8": AF(4), "PB6": AF(4)}}, evidence="af_table")` —
  citing the evidence it came from. The list-of-names form stays valid for
  every part that has no selectors.
- The lowering records, on each pin connection it makes, the selector of each
  chosen pin and the evidence for it.
- An addressed bus device's port carries its address: fixed
  (`address=0x44 * addr`), or a strap pin with the address each of the device's
  own pins selects (`address=Strap("ADDR", {"GND": ..., "VDD": ..., "SDA": ...,
  "SCL": ...})`). A strapped address is resolved from the board's nets.
- The compatibility check's addressing rule reads those addresses: two devices
  at one address on one bus fail naming both, and a strap that resolves to no
  address leaves the check undecided naming the strap pin. A port that declares
  no address, such as a controller's, is not addressed and is not reported.
- A new example, `examples/sensor_node/`: an STM32F401RE (LQFP64) with I2C1 on
  PB8/PB9 or PB6/PB7 at AF4, USART2 on PA2/PA3 at AF7 to a console header, and
  a status LED on PA5; an HS3001 at its fixed address 0x44; pull-ups and
  decoupling. Every pad number and selector is cited. It is the board
  `fang-emulation` will run firmware against.
- `SCHEMA_VERSION` moves from 1.1 to 1.2: the port and connection records gain
  optional keys, which the spec calls an additive change.

## Capabilities

### New Capabilities

None. The project holds one capability and this change extends it.

### Modified Capabilities

- `fang-kernel` — adds two requirements: a port may be one peripheral instance
  whose candidate pins carry cited selectors, recorded on the lowered
  connection; and an addressed bus device carries its address, fixed or
  strapped, which the compatibility check reads. No existing requirement's text
  changes.

## Impact

- `fang/interfaces.py`: `InterfacePort` gains `peripheral`; `PinMap` accepts a
  candidate-to-selector mapping and an `evidence` name; `AF`, `Selector` and
  `Strap`; the I2C interface declares a dimensionless `address` parameter.
- `fang/entities.py`: `Port` gains optional `peripheral` and `address_strap`;
  `Connection` gains optional `selectors`. Each is omitted from `as_dict()`
  when absent, so no existing snapshot's content changes beyond its schema
  version.
- `fang/lowering.py` and `fang/elaborate.py` carry selectors and straps into the
  graph; `fang/compatibility.py` resolves strapped addresses and reports
  unresolved ones; `fang/__init__.py` moves `SCHEMA_VERSION`.
- `fang/diagnostics.py` gains two codes in the `IFACE` area; a bare-number
  address reuses the existing `UNIT` code.
- `examples/sensor_node/` with its README and `out/`, discovered by the suite.
- No new dependency. Docs: the interfaces reference page, `CLAUDE.md` and
  `CHANGELOG.md`.
