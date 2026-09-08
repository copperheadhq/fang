---
title: Interfaces
description: The shipped catalogue, its signals and its parameters.
sidebar:
  order: 3
---

The catalogue holds 21 interface types. Seventeen have a port class, so a
program writes `I2CPort()` rather than reaching for a factory; the remaining
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

## Roles

A pin declares a role, drawn from a fixed set: `power`, `ground`, `clock`,
`data`, `control`, `reset`, `differential_p`, `differential_n`, `analog`,
`phase`, `unknown`.

A role says what a pin is for. It classifies the pin and determines what a
single-signal surface behaves as; which pin a signal actually lands on is
decided by the `PinMap`, not by matching roles.

## Adding one

`InterfaceCatalogue.register()` adds a type to a project's catalogue. A new type
states its signals, its connection kind, its parameters and its rules. It does
not state pins, which remain a lowering result.
