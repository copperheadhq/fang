---
title: Examples
description: Fourteen programs in the repository, smallest first.
sidebar:
  order: 3
  attrs:
    data-icon: list-format
---

Every example in [`examples/`](https://github.com/copperheadhq/fang/tree/main/examples)
elaborates and passes the gate. The test suite rebuilds each one and compares
what it produces, so none of these is a sketch that no longer runs. Each has a
page here carrying its program, the views it renders and the files it writes.
Those pages are generated from the folder itself. A page cannot describe a
program that has since changed.

| Example | Shows |
| --- | --- |
| [`divider/`](/examples/divider/) | The smallest real board: two resistors and a capacitor |
| [`rc_filter/`](/examples/rc_filter/) | One question, answered by ngspice and then at the equation level |
| [`antenna_match/`](/examples/antenna_match/) | A Touchstone model through an L match, answered in closed form |
| [`blinky/`](/examples/blinky/) | Declared surfaces, connections and a constraint stating intent rather than the answer |
| [`equations/`](/examples/equations/) | Values chosen by equation and reuse by inheritance |
| [`sensor_board/`](/examples/sensor_board/) | Interfaces lowering to pins, a recorded decision, a check left undecided |
| [`i2c_bus/`](/examples/i2c_bus/) | A multi-drop bus, addresses as constrained parameters |
| [`sensor_node/`](/examples/sensor_node/) | Ports that name their controller, cited pin selectors, an address the check reads |
| [`buck_regulator/`](/examples/buck_regulator/) | Requirement, decision, calculations, and a question ngspice answers under load |
| [`usb_uart_bridge/`](/examples/usb_uart_bridge/) | Part selection: manufacturer, MPN, distributor and datasheet |
| [`servo_drive/`](/examples/servo_drive/) | Composition: one `HalfBridge` block instantiated three times |
| [`jee_advanced/problem_1/`](/examples/jee_advanced/problem_1/) | Not a board: four claimed currents, all four decided |
| [`jee_advanced/problem_2/`](/examples/jee_advanced/problem_2/) | Not a board either: one claimed current, and the two branches that carry none |
| [`noninverting_amp/`](/examples/noninverting_amp/) | Not a board: two midband answers, and the reading of the figure they rest on |

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
| `<name>.kicad_sch` | The KiCad schematic, the sheet Eeschema opens | `fang schematic` |
| `schematic.svg` | KiCad's own render of that sheet | `fang schematic --svg` |
| `netlist.txt` | The same projection as text: parts, then nets and their pads | `fang netlist` |
| `checks.txt` | Every check that ran, and every one left undecided | `fang check` |
| `graph.txt` | What the elaborated graph contains, by entity kind | `fang graph` |
| `views/*.svg` | The views worth looking at for that board | `fang view` |
| `rationale.md` | The requirements, decisions, calculations and evidence in the graph | none |
| `verification.txt` | What each declared question's tool found, at three significant figures | `fang verify` |

`python examples/regenerate.py` rewrites them. They are built in the project
namespace `PRJ-EXAMPLES`, which is where the identifiers in them come from. A
local `fang build` defaults to `PRJ-LOCAL` and derives its own.

## What each one is for

**`divider/`** is the smallest thing worth calling a board. Read it to learn
the shape of a program and nothing else.

**`rc_filter/`** is the smallest board with a question on it. The corner is a
parameter with no value and the constraint over it is undecided, until ngspice
measures it in an AC sweep and the number comes back through the gate. Asked
again on the committed head, the same question is answered at the equation
level and nothing runs.

**`antenna_match/`** carries its antenna as data: a Touchstone file, synthetic
and saying so. Its return loss through the L match is read and composed in
closed form, with the matching values the graph holds, and the confidence is
halved because the model is an assumption.

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

**`sensor_node/`** puts on the board what the firmware otherwise holds alone.
The STM32F401RE's `i2c1` port names I2C1, and each candidate pin carries the
alternate function that routes the signal to it, cited from ST's table. The
lowered pin connections carry AF4. The HS3001's port carries its address,
0x44, and the compatibility check decides the addressing rule from it.

**`usb_uart_bridge/`** shows part selection landing on the instance rather
than the class template. The logical part stays "a 3.3 V regulator". Which one
was bought is a separate, cited fact.

**`buck_regulator/`** puts the reasoning in the graph. The requirement, the
part decision, the datasheet numbers behind it and two calculations are all
entities beside the inductor, so `fang` can answer "why is this 4.7 µH?"
without anyone writing a design document. The requirement is verified by a
question rather than asserted: ngspice runs the rail under full load on an
ideal power stage whose provenance is an assumption, and measures 3.29 V and
1.90 mV of ripple.

**`servo_drive/`** is composition at size. A `HalfBridge` owns its interior:
its transistors, its shunt and its own constraints. The drive instantiates three
of them from one declaration.
