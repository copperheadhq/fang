---
title: Interfaces
description: The shipped catalogue, its signals and its parameters.
sidebar:
  order: 3
  attrs:
    data-icon: link-alt
---

The catalogue holds 21 interface types. Seventeen have a port class, so a
program writes `I2CPort()` rather than reaching for a factory. The remaining
four are the primitives the typed ones are built from.

See [Interfaces and lowering](/concepts/interfaces-and-lowering/) for how a
connection between two of these becomes pin connections.

## The catalogue

An asterisk marks an optional signal.

| Type | Port class | Signals | Kind | Rules |
| --- | --- | --- | --- | --- |
| `analog_input` | `AnalogIn` | `signal` `ref`* | electrical | none |
| `analog_output` | `AnalogOut` | `signal` `ref`* | electrical | none |
| `can` | `CANPort` | `canh` `canl` | signal | multi-drop |
| `clock` | `ClockPort` | `clk` | signal | none |
| `electrical` | none | `line` | electrical | none |
| `ground` | none | `gnd` | ground | none |
| `i2c` | `I2CPort` | `scl` `sda` | signal | multi-drop, pull-ups |
| `jtag` | `JTAGPort` | `tck` `tms` `tdi` `tdo` `trst`* | signal | none |
| `motor_phase` | `MotorPhase` | `phase` | power | none |
| `power` | none | `vcc` | power | none |
| `power_input` | `PowerIn` | `vcc` `gnd` | power | none |
| `power_output` | `PowerOut` | `vcc` `gnd` | power | multi-drop |
| `pwm` | `PWMPort` | `out` | signal | none |
| `quadrature_encoder` | `EncoderPort` | `a` `b` `index`* | signal | none |
| `reset` | `ResetPort` | `nrst` | signal | none |
| `rs485` | `RS485Port` | `a` `b` `de`* | signal | multi-drop |
| `signal` | none | `line` | signal | none |
| `spi` | `SPIPort` | `sck` `mosi` `miso` `cs` | signal | none |
| `swd` | `SWDPort` | `swclk` `swdio` | signal | none |
| `uart` | `UARTPort` | `tx` `rx` `rts`* `cts`* | signal | none |
| `usb2` | `USB2Port` | `dp` `dm` `vbus`* `gnd` | signal | none |

`spi` is not multi-drop. A second target needs its own chip select, which is a
different circuit rather than the same one connected twice.

## Parameters

Every parameter is optional. An absent one is not a default. It leaves any
check that needed it [undecided](/concepts/values-and-undecided/).

**Digital interfaces**, meaning `i2c`, `spi`, `uart`, `usb2`, `can`, `rs485`, `pwm`,
`quadrature_encoder`, `jtag`, `swd`, `clock`, `reset`:

| Parameter | Unit | Is |
| --- | --- | --- |
| `voltage` | V | The supply the interface runs at |
| `voh_min` | V | Minimum output high |
| `vol_max` | V | Maximum output low |
| `vih_min` | V | Minimum input high threshold |
| `vil_max` | V | Maximum input low threshold |
| `current_capability` | A | What a source can drive |
| `current_demand` | A | What a sink draws |
| `bit_rate` | Hz | Signalling rate |
| `pull_up_resistance` | Ohm | Pull-up value, where the protocol needs one |
| `pull_up_supply` | V | What the pull-ups are pulled to |

`i2c` also declares `address`, unit `1`: the device's bus address. See
[Addresses](#addresses) below.

**Power interfaces**, meaning `power`, `power_input`, `power_output` and
`motor_phase` (which omits `ripple`):

| Parameter | Unit |
| --- | --- |
| `voltage` | V |
| `current_capability` | A |
| `current_demand` | A |
| `ripple` | V |

**Analog interfaces**, meaning `analog_input` and `analog_output`:

| Parameter | Unit |
| --- | --- |
| `voltage` | V |
| `impedance` | Ohm |
| `bandwidth` | Hz |

## Using one

```python
from fang.interfaces import I2CPort, Pin, PinMap
from fang.lang import Part, V, kOhm

class MCU(Part):
    i2c = I2CPort(voltage=3.3 * V, voh_min=2.4 * V,
                  pull_up_resistance=4.7 * kOhm)
    PB8 = Pin("PB8", role="clock")
    PB9 = Pin("PB9", role="data")
    pinmap = PinMap({"i2c.scl": "PB8", "i2c.sda": "PB9"})
```

A single signal of a port is reachable as a surface, so a rail can meet one pad
rather than the whole interface:

```python
self.rail.vcc      >> self.pullup_scl.p1
self.pullup_scl.p2 >> self.mcu.i2c.scl
```

A signal surface keeps the nature of the wire it is. A `power` signal stays
power, a `ground` signal stays ground and anything else is plain electrical.

## Peripheral instances and selectors

A port can name the peripheral instance it is. A part with I2C on two
controllers declares two ports, and a connection to one of them lowers only
onto that controller's candidate pins:

```python
i2c1 = I2CPort(peripheral="I2C1", voltage=3.3 * V)
i2c2 = I2CPort(peripheral="I2C2", voltage=3.3 * V)
```

`peripheral` is recorded on the port entity. It is not a parameter.

A candidate pin can carry the selector that routes the port's signal to it.
`Selector("...")` takes the vendor's own spelling; `AF(n)` is the STM32
family's alternate function, and `AF(4) == Selector("AF4")`. A pin map that
carries any selector names, as `evidence`, the `Cites` declaration on the same
part that the selectors were read from:

```python
from fang.interfaces import AF, PinMap
from fang.rationale import Cites

af_table = Cites("I2C1_SCL is AF4 on PB6 and PB8, I2C1_SDA is AF4 on PB7 and PB9",
                 document="SRC-DS-STM32F401", locator="table 9")
peripherals = PinMap(
    {"i2c1.scl": {"PB8": AF(4), "PB6": AF(4)},
     "i2c1.sda": {"PB9": AF(4), "PB7": AF(4)}},
    evidence="af_table",
)
```

The mapping's order is the preference order, as a list's is, and a candidate
may map to `None` for no selector. Elaboration refuses a pin map with
selectors that names no evidence, names nothing the part declares, or names an
assumption rather than a citation (`IFACE-0003`). The list form is unchanged.

When the lowering chooses a pin that carries a selector, the pin connection it
records carries it too, keyed by the pin's identifier, with the evidence:

```json
"selectors": {"PIN-6093c2974cd4": {"evidence": "EVD-355c4bf2d94a", "selector": "AF4"}}
```

Only the side or sides whose chosen pin declared a selector appear. The
selector belongs to the assignment rather than to the pin, because one pin
serves several ports at different selectors.

## Addresses

An addressed bus device's port carries its address, as a dimensionless
quantity:

```python
addr = UnitLiteral("1")
i2c = I2CPort(address=0x44 * addr)
```

`address=0x44` is refused with `UNIT-0001` naming the parameter: a bare number
says nothing about what it counts.

Where a strap pin selects the address, `Strap` keys each address by one of the
device's own pins, which is how a datasheet states it:

```python
from fang.interfaces import Strap

i2c = I2CPort(address=Strap("ADDR", {"GND": 0x48 * addr, "VDD": 0x49 * addr,
                                     "SDA": 0x4A * addr, "SCL": 0x4B * addr}))
```

The names are the part's vendor pin names; one the part does not have is
`IFACE-0004`. The port stores the strap with the names resolved to pin
identifiers and carries no `address` parameter beside it.

`fang.compatibility.resolve_address(snapshot, port)` reads the address. A fixed
one comes back as recorded. A strap is resolved from the inferred nets: the one
pin of its map that shares the strap pin's net selects the address, returned as
an inferred value. A strap pin on no net, on a net none of those pins shares,
or on a net two of them share gives an unknown value whose reason names the
strap pin, and both pins when two share it. A port with neither, such as a
controller's, gives `None`: it is not addressed.

The compatibility check's addressing rule reads every participant of a
multi-drop bus through that function. Two devices at one address fail, naming
both. An unresolved strap leaves the rule undecided, naming the pin. A port
with no address is not reported. When every addressed device is known and no
two collide, the rule passes.

## Roles

A pin declares a role, drawn from a fixed set: `power`, `ground`, `clock`,
`data`, `control`, `reset`, `differential_p`, `differential_n`, `analog`,
`phase`, `unknown`.

A role says what a pin is for. It classifies the pin and determines what a
single-signal surface behaves as. Which pin a signal actually lands on is
decided by the `PinMap`, not by matching roles.

## Adding one

`InterfaceCatalogue.register()` adds a type to a project's catalogue. A new type
states its signals, its connection kind, its parameters and its rules. It does
not state pins, which remain a lowering result.
