---
title: Examples
description: Eight programs in the repository, smallest first.
sidebar:
  order: 3
---

Every example in [`examples/`](https://github.com/copperheadhq/fang/tree/main/examples)
elaborates, passes the gate and is exercised by the test suite, so none of them
is a sketch that no longer runs.

| Example | Shows |
| --- | --- |
| [`divider/`](https://github.com/copperheadhq/fang/tree/main/examples/divider/) | The smallest real board: two resistors and a capacitor |
| [`blinky/`](https://github.com/copperheadhq/fang/tree/main/examples/blinky/) | Declared surfaces, connections and a constraint stating intent rather than the answer |
| [`equations/`](https://github.com/copperheadhq/fang/tree/main/examples/equations/) | Values chosen by equation and reuse by inheritance |
| [`sensor_board/`](https://github.com/copperheadhq/fang/tree/main/examples/sensor_board/) | Interfaces lowering to pins, a recorded decision, a check left undecided |
| [`i2c_bus/`](https://github.com/copperheadhq/fang/tree/main/examples/i2c_bus/) | A multi-drop bus, addresses as constrained parameters |
| [`usb_uart_bridge/`](https://github.com/copperheadhq/fang/tree/main/examples/usb_uart_bridge/) | Part selection: manufacturer, MPN, distributor and datasheet |
| [`buck_regulator/`](https://github.com/copperheadhq/fang/tree/main/examples/buck_regulator/) | Requirement, decision, calculations and verification beside the circuit |
| [`servo_drive/`](https://github.com/copperheadhq/fang/tree/main/examples/servo_drive/) | Composition: one `HalfBridge` block instantiated three times |

## Running one

```bash
fang build   examples/sensor_board/sensor_board.py
fang netlist examples/sensor_board/sensor_board.py
fang view    examples/sensor_board/sensor_board.py ground -o ground.svg
```

## What is in an `out/`

| File | What it is | Command |
| --- | --- | --- |
| `<name>.net` | The KiCad netlist, the artifact a layout tool opens | `fang export` |
| `netlist.txt` | The same projection as text: parts, then nets and their pads | `fang netlist` |
| `checks.txt` | Every check that ran, and every one left undecided | `fang check` |
| `graph.txt` | What the elaborated graph contains, by entity kind | `fang graph` |
| `views/*.svg` | The views worth looking at for that board | `fang view` |
| `rationale.md` | The requirements, decisions, calculations and evidence in the graph | none |

`python examples/regenerate.py` rewrites them. They are built in the project
namespace `PRJ-EXAMPLES`, which is where the identifiers in them come from; a
local `fang build` defaults to `PRJ-LOCAL` and derives its own.

## What each one is for

**`divider/`** is the smallest thing worth calling a board. Read it to learn
the shape of a program and nothing else.

**`blinky/`** adds the point about constraints. The series resistor is not
written as a number that someone computed offstage. The LED current is written
as the requirement, and the resistor value has to satisfy it.

**`equations/`** takes that further. Ohm's law is a constraint rather than a
comment, so substituting a part re-checks the arithmetic instead of trusting it.
`SenseDivider` inherits the equations and replaces the two values.

**`sensor_board/`** is the one to read to understand lowering. The MCU offers
`PB8` and `PB6` for the I2C clock. `self.mcu.i2c >> self.imu.i2c` resolves to one
of them and records a decision naming what it rejected. It also leaves a check
**undecided**, because the IMU's threshold is missing rather than assumed.

**`i2c_bus/`** connects one port several times. Two things a netlist could not
keep survive here. The device addresses are parameters, so "no two devices answer
to the same address" is a constraint the kernel decides rather than a linter
rule. And the RTC's thresholds are recorded as an assumption, which leaves that
link undecided rather than passed.

**`usb_uart_bridge/`** shows part selection landing on the instance rather
than the class template. The logical part stays "a 3.3 V regulator". Which one
was bought is a separate, cited fact.

**`buck_regulator/`** puts the reasoning in the graph. The requirement, the
part decision, the datasheet numbers behind it, two calculations and the
verification that closes the requirement are all entities beside the inductor.
`fang` can answer "why is this 4.7 µH?" without anyone writing a design
document.

**`servo_drive/`** is composition at size. A `HalfBridge` owns its interior:
its transistors, its shunt and its own constraints. The drive instantiates three
of them from one declaration.
