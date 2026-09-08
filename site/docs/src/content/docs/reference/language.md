---
title: Language
description: The authoring surface, in full.
sidebar:
  order: 2
  attrs:
    data-icon: pencil
---

A Fang program is ordinary Python. What makes it a design is the declarations in
a class body, which the kernel collects in the order they were written.

## Modules

| Class | Is |
| --- | --- |
| `Module` | A reusable unit owning parameters, surfaces, constraints and children |
| `System` | The root module of a design |
| `Part` | A leaf module that becomes a component rather than a block |

```python
from fang.lang import Part, System, V, kOhm, require

class Board(System):
    ...
```

A `Module` is instantiated with keyword overrides, as in
`Regulator(output_voltage=5 * V)`. A `Part` also accepts `package=`.

### The two hooks

```python
class Board(System):
    def architecture(self):
        """Connections. Runs first."""

    def constraints(self):
        """require() calls. Runs second."""
```

Both are optional. `architecture()` runs before `constraints()`, so a constraint
may refer to anything the architecture created.

## Parameters

```python
Parameter(unit, *, default=None, description="")
```

A parameter is declared with its unit. **A bare number is not a parameter.**
The unit is not decoration. It is what makes the value checkable.

```python
class Regulator(GenericPart):
    output_voltage = Parameter("V", description="the rail it makes")
```

## Units

Unit literals multiply a number into a `Quantity`:

```python
3.3 * V      10 * kOhm      100 * uF      1.25 * MHz      10 * ms
```

| Domain | Literals |
| --- | --- |
| Voltage | `V` `mV` `uV` `kV` |
| Current | `A` `mA` `uA` `nA` |
| Power | `W` `mW` |
| Resistance | `Ohm` `mOhm` `kOhm` `MOhm` |
| Capacitance | `F` `uF` `nF` `pF` |
| Inductance | `H` `mH` `uH` |
| Frequency | `Hz` `kHz` `MHz` |
| Time | `s` `ms` `us` `ns` |
| Length | `m` `mm` |
| Other | `degC` `percent` |

Two helpers build non-scalar quantities:

```python
between(3.0 * V, 3.6 * V)              # a range, optional typical= third argument
tolerance(10 * kOhm, "1%")             # a nominal and a tolerance
```

Combining unequal dimensions raises [`UNIT-0001`](/reference/diagnostics/) at the
point the expression is constructed.

## Surfaces

A surface is somewhere a connection can land.

| Surface | For |
| --- | --- |
| `Electrical` | An untyped electrical connection |
| `Power` | A power connection |
| `Ground` | A ground connection |
| `Signal` | A signal connection |
| `Mechanical` | A non-electrical attachment |

Typed [interface ports](/reference/interfaces/) are surfaces too, and they
carry more: their signals, their parameters and their rules.

## Connections

```python
self.top.p2 >> self.bottom.p1          # the connect operator
connect(self.top.p2, self.bottom.p1)   # the same thing, spelled out
```

`>>` is not directional in the electrical sense; it reads left to right and
records a connection between two surfaces. A connection with no kind is
[`ELAB-0005`](/reference/diagnostics/).

## Constraints

```python
def constraints(self):
    require(self.regulator.output_voltage == 3.3 * V)
    require(self.led.forward_current <= 20 * mA)
```

`require()` records the expression; it does not evaluate it there. Evaluation
happens against a snapshot, over interval arithmetic, with an unknown operand
producing [undecided](/concepts/values-and-undecided/).

## Pins and pin maps

```python
class MCU(Part):
    i2c = I2CPort(voltage=3.3 * V)
    PB8 = Pin("PB8", role="clock")
    PB9 = Pin("PB9", role="data")
    pinmap = PinMap({"i2c.scl": "PB8", "i2c.sda": "PB9"})
```

In `Pin(name, *, role="unknown", number=None)`, `number` records the physical
pin number when it differs from the name.

A `PinMap` value is one pin name or a list of candidates. Candidates are what
make a recorded [decision](/concepts/interfaces-and-lowering/) possible.

Roles are drawn from a fixed set: `power`, `ground`, `clock`, `data`, `control`,
`reset`, `differential_p`, `differential_n`, `analog`, `phase`, `unknown`.

## Selecting a vendor part

```python
def __init__(self, **overrides):
    super().__init__(**overrides)
    self.controller.select(
        "Texas Instruments", "TPS62130RGTR",
        distributor_ids={"digikey": "296-35088-1-ND"},
        datasheet="SRC-DS-TPS62130",
        evidence=("absolute_maximum",),
    )
```

`select()` attaches sourcing to the **instance**, not the class template. The
part's logical identity is unchanged: the design still says "a 3.3 V regulator"
and separately says which one was bought. `part.selected` reports whether one
was.

## Tools

```python
def architecture(self):
    layout = tools.layout(placers=["pyplacer"], routers=["freerouting"])
    report = tools.check(profile="jlcpcb-2layer")
    tools.export(layout=layout, format="kicad", require=report.passed)
```

Every `tools.*` call records an operation in the plan and returns a **handle**.
Nothing runs during elaboration. Reading a handle is
[`ELAB-0008`](/reference/diagnostics/), whether you branch on it, compare it or
convert it to a boolean.
`report.passed` is a symbolic condition resolved in the
[operation phase](/concepts/three-phases/).

Calls take named arguments only. A positional argument is rejected, because a
stored and replayed plan cannot depend on argument order.

## Rationale

Declared in the class body. See [Rationale](/concepts/rationale/) for the full
set: `Requires`, `Assumes`, `Cites`, `Chooses`, `Calculates`, `Verifies`.
