---
title: Introduction
description: What fang is, and what it refuses to do.
sidebar:
  order: 1
---

Fang is a Python-embedded language for circuit boards, and the kernel that holds
what you write. You author intent — typed interfaces, parameters carrying units,
constraints. The kernel elaborates that into one canonical model, refuses
anything it cannot justify, and lowers what survives into netlists, views,
simulation decks, and KiCad.

It is the layer under [copperhead](https://copperhead.sh). Copperhead is the
agent you talk to; fang is what it writes and what checks the writing.

## The shape of it

```python
class SensorBoard(System):
    regulator = Regulator(output_voltage=3.3 * V, package="SOT-23-5")
    mcu = MCU(package="LQFP-64")
    imu = IMU(package="LGA-14")

    def architecture(self):
        self.mcu.i2c >> self.imu.i2c

    def constraints(self):
        require(self.regulator.output_voltage == 3.3 * V)
```

`self.mcu.i2c >> self.imu.i2c` is an interface connection, not a pin
assignment. The kernel lowers it — deterministically — onto `PB8 → SCL` and
`PB9 → SDA`, and because the MCU offered `PB6` and `PB7` as alternatives, the
choice becomes a decision entity naming what it rejected.

Pin assignment is a lowering result. It is never an authoring input, which is
what makes late assignment and part substitution tractable.

## What it will not do

Most of the value is in the answers the kernel declines to give.

- An unknown datasheet number makes a check **undecided** — a third truth value,
  never a quiet pass. Whether undecided blocks is the commit gate's policy
  decision, not the evaluator's.
- A dimensionally invalid expression is rejected **where it is written**, so it
  can never be stored, let alone evaluated.
- A missing simulator reports **unsupported** rather than substituting a model.
- A CAD construct the adapter does not model is **named in the import report**
  rather than dropped.
- A generic part carries **no manufacturer** until one is selected.

Nothing is invented to make an answer available.
