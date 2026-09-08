---
title: Parts
description: The standard library and what a generic part deliberately lacks.
sidebar:
  order: 4
---

```python
from fang.parts import Capacitor, Resistor
from fang.lang import V, kOhm, uF

top = Resistor(resistance=10 * kOhm, package="R_0603_1608Metric")
cap = Capacitor(capacitance=100 * uF, voltage_rating=16 * V)
```

## A generic part has no manufacturer

Everything in the library is a `GenericPart`: a part with no vendor identity.
That is a deliberate absence, not an unfinished state. A design that says "a
10 kΩ resistor" is complete at the stage it is at; attaching a manufacturer
before one has been chosen would be inventing a fact.

[`select()`](/reference/language/#selecting-a-vendor-part) attaches the vendor
identity later, to the instance, without replacing the logical part.

## The library

| Part | Parameters | Surfaces |
| --- | --- | --- |
| `Resistor` | `resistance`, `power_rating`, `tolerance_pct` | `p1`, `p2` |
| `Capacitor` | `capacitance`, `voltage_rating`, `tolerance_pct` | `p1`, `p2` |
| `Inductor` | `inductance`, `current_rating`, `dc_resistance` | `p1`, `p2` |
| `Diode` | `forward_voltage`, `forward_current`, `reverse_voltage` | `p1`, `p2` |
| `LED` | the `Diode` set, plus `luminous_intensity` | `p1`, `p2` |
| `Fuse` | `current_rating`, `voltage_rating` | `p1`, `p2` |
| `Crystal` | `frequency`, `load_capacitance`, `tolerance_ppm` | `p1`, `p2` |
| `Transistor` | `vds_max`, `id_max`, `rds_on`, `vgs_threshold` | `gate`, `drain`, `source` |
| `Regulator` | `output_voltage`, `input_voltage_max`, `output_current_max`, `dropout_voltage`, `quiescent_current` | `vin`, `vout` (power ports) |
| `Connector` | `current_rating`, `voltage_rating` | `shell`, plus per-instance pins |
| `TestPoint` | none | `probe` |
| `MountingHole` | `diameter` | `mount` |

`DecouplingCapacitor` is a `Capacitor` whose job is stated, so a checker can
find it. It is not in `LIBRARY` because it is a role, not a distinct part.

## Every parameter is optional

```python
Resistor(resistance=10 * kOhm)     # power_rating unstated
```

An unstated parameter is unknown, and any check that needed it reports
[undecided](/concepts/values-and-undecided/) rather than assuming a value. If a
resistor's power rating matters to a constraint, the constraint says undecided
until someone supplies it.

## Packages and footprints

```python
Resistor(resistance=10 * kOhm, package="R_0603_1608Metric")
```

`package=` attaches a `Footprint` trait. Where a part lands physically is a
trait rather than a parameter, because it is a fact about the realization, not
about the electrical behaviour.

## Traits

Behaviour attaches to a part without widening its class:

| Trait | Carries |
| --- | --- |
| `Footprint` | Where a component lands physically |
| `Sourcing` | Manufacturer, MPN, distributor codes |
| `DatasheetEvidence` | The document a component's claims are cited from |
| `Simulatable` | A model, as data. The backend is not here |
| `Renderable` | A view-compiler hint carrying no geometry and no meaning |

## Writing your own

Subclass `Part` and declare parameters, surfaces, pins and a pin map:

```python
from fang.interfaces import I2CPort, Pin, PinMap
from fang.lang import Parameter, Part, V

class IMU(Part):
    i2c = I2CPort(voltage=3.3 * V)
    supply_current = Parameter("A", description="run current")
    SCL = Pin("SCL", role="clock", number="4")
    SDA = Pin("SDA", role="data", number="5")
    pinmap = PinMap({"i2c.scl": "SCL", "i2c.sda": "SDA"})
```

Nothing registers it. A part is a class, and using it is how it enters a design.
