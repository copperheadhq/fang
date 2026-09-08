---
title: Interfaces and lowering
description: A connection says what it carries. Pins are a result.
sidebar:
  order: 5
---

```python
self.mcu.i2c >> self.imu.i2c
```

That is not a pin assignment. It is a claim that two typed interfaces are
joined, and the kernel works out which pads carry it.

## Pin assignment is a lowering result

It is never an authoring input. This is the load-bearing decision of the whole
interface layer, and everything else follows from it.

- **Late assignment is tractable.** Pins can be decided after placement, or
  changed because routing wants them changed, without editing the design.
- **Substitution is tractable.** A part with a different pinout satisfies the
  same connection.
- **The choice is explainable**, because the kernel made it and recorded why.

## Lowering is deterministic

A part declares its pins and a `PinMap` saying which pins can carry which
interface signal:

```python
class MCU(Part):
    i2c = I2CPort(voltage=3.3 * V, pull_up_resistance=4.7 * kOhm)
    PB8 = Pin("PB8", role="clock")
    PB6 = Pin("PB6", role="clock")       # a second candidate
    PB9 = Pin("PB9", role="data")
    PB7 = Pin("PB7", role="data")
    pinmap = PinMap({"i2c.scl": ["PB8", "PB6"], "i2c.sda": ["PB9", "PB7"]})
```

Given candidates, lowering picks one and produces the same answer every time, in
this process and the next. Determinism here is not a convenience. A pinout that
shifted between runs would make every downstream artifact unstable.

## A choice becomes a decision entity

`PB8` won and `PB6` lost, so a `Decision` is written into the graph naming the
alternative it rejected. Ask later why the clock is on `PB8` and the answer is a
fact in the model, not an inference from the result.

Where there is only one candidate there is no decision to record, and none is
recorded. The graph does not accumulate ceremony.

## If a signal cannot be placed

A required signal with no pin able to carry it is
[`IFACE-0001`](/reference/diagnostics/). It is not deferred, and no pin is
invented to satisfy it.

Optional signals are genuinely optional. `uart` names `rts` and `cts`, and a
part that omits them is not incomplete.

## Compatibility is checked, not assumed

Joining two ports checks that the join makes electrical sense: voltages,
thresholds, drive against demand and pull-ups where the protocol needs them.

The check obeys the rule that governs everything else. A missing datasheet
number makes the result **undecided**, never a pass.

```python
class IMU(Part):
    i2c = I2CPort(voltage=3.3 * V)   # no vih_min: not known
```

Connect that to a 3.3 V controller and the compatibility check reports undecided
and names the parameter it needed. Supplying `vih_min` decides it. Assuming one
would have hidden the question.

Two interfaces that disagree about membership are `IFACE-0002`.

## Buses

A multi-drop interface can be connected several times, and lowering resolves the
whole set into one net per signal. `i2c`, `can`, `rs485` and `power_output` are
multi-drop. `spi` is not, because a second target needs its own chip select, and
that is a different circuit rather than the same one twice.
