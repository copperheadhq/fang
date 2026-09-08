---
title: Examples
description: Eight programs in the repository, smallest first.
sidebar:
  order: 3
---

Every example in [`examples/`](https://github.com/copperheadhq/fang/tree/main/examples)
elaborates, passes the gate, and is exercised by the test suite, so none of them
is a sketch that no longer runs.

| Example | Shows |
| --- | --- |
| [`divider.py`](https://github.com/copperheadhq/fang/blob/main/examples/divider.py) | The smallest real board: two resistors and a capacitor |
| [`blinky.py`](https://github.com/copperheadhq/fang/blob/main/examples/blinky.py) | Declared surfaces, connections, and a constraint stating intent rather than the answer |
| [`equations.py`](https://github.com/copperheadhq/fang/blob/main/examples/equations.py) | Values chosen by equation, and reuse by inheritance |
| [`sensor_board.py`](https://github.com/copperheadhq/fang/blob/main/examples/sensor_board.py) | Interfaces lowering to pins, a recorded decision, a check left undecided |
| [`i2c_bus.py`](https://github.com/copperheadhq/fang/blob/main/examples/i2c_bus.py) | A multi-drop bus, addresses as constrained parameters |
| [`usb_uart_bridge.py`](https://github.com/copperheadhq/fang/blob/main/examples/usb_uart_bridge.py) | Part selection: manufacturer, MPN, distributor, datasheet |
| [`buck_regulator.py`](https://github.com/copperheadhq/fang/blob/main/examples/buck_regulator.py) | Requirement, decision, calculations and verification beside the circuit |
| [`servo_drive.py`](https://github.com/copperheadhq/fang/blob/main/examples/servo_drive.py) | Composition: one `HalfBridge` block instantiated three times |

## Running one

```bash
fang build   examples/sensor_board.py
fang netlist examples/sensor_board.py
fang view    examples/sensor_board.py ground -o ground.svg
```

## What each one is for

**`divider.py`** is the smallest thing worth calling a board. Read it to learn
the shape of a program and nothing else.

**`blinky.py`** adds the point about constraints. The series resistor is not
written as a number that someone computed offstage; the LED current is written
as the requirement, and the resistor value has to satisfy it.

**`equations.py`** takes that further: Ohm's law is a constraint rather than a
comment, so substituting a part re-checks the arithmetic instead of trusting it.
`SenseDivider` inherits the equations and replaces the two values.

**`sensor_board.py`** is the one to read to understand lowering. The MCU offers
`PB8` and `PB6` for the I2C clock; `self.mcu.i2c >> self.imu.i2c` resolves to
one of them and records a decision naming what it rejected. It also leaves a
check **undecided**, because the IMU's threshold is missing rather than assumed.

**`i2c_bus.py`** connects one port several times. Two things a netlist could not
keep survive here: the device addresses are parameters, so "no two devices answer
to the same address" is a constraint the kernel decides rather than a linter
rule; and the RTC's thresholds are recorded as an assumption, which leaves that
link undecided rather than passed.

**`usb_uart_bridge.py`** shows part selection landing on the instance rather
than the class template. The logical part stays "a 3.3 V regulator"; which one
was bought is a separate, cited fact.

**`buck_regulator.py`** puts the reasoning in the graph: the requirement, the
part decision, the datasheet numbers behind it, two calculations, and the
verification that closes the requirement are all entities beside the inductor.
`fang` can answer "why is this 4.7 µH?" without anyone writing a design
document.

**`servo_drive.py`** is composition at size. A `HalfBridge` owns its interior —
its transistors, its shunt, its own constraints — and the drive instantiates
three of them from one declaration.
