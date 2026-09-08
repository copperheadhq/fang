---
title: Installation
description: Install fang and build your first board.
sidebar:
  order: 2
---

Fang is pure Python 3.11+ with no required dependencies.

```bash
pip install copperhead-fang
```

The distribution is `copperhead-fang` because the bare name on PyPI belongs to
an unrelated package. The import name is still `fang`.

Two optional extras exist. When either is absent the toolchain says so rather
than working around it:

```bash
pip install "copperhead-fang[analysis]"   # NetworkX, for graph analysis queries
```

`ngspice` is an external simulator reached across a process boundary. Install it
with your package manager and fang will find it on `PATH`.

## Your first board

```python
# divider.py
from fang.lang import System, V, kOhm, uF
from fang.parts import Capacitor, Resistor


class Divider(System):
    top = Resistor(resistance=10 * kOhm, package="R_0603_1608Metric")
    bottom = Resistor(resistance=4.7 * kOhm, package="R_0603_1608Metric")
    filter_cap = Capacitor(capacitance=100 * uF, voltage_rating=16 * V)

    def architecture(self):
        self.top.p2 >> self.bottom.p1
        self.bottom.p1 >> self.filter_cap.p1
        self.bottom.p2 >> self.filter_cap.p2
```

```bash
fang build   divider.py            # elaborate, pass the gate, persist, run the plan
fang netlist divider.py            # components and nets
fang export  divider.py -o out.net # a KiCad netlist
```

`fang build` writes a `.copperhead/` workspace beside your sources. It holds the
design as a canonical record stream, a cache that can be rebuilt and a manifest
naming the schema version and the snapshot hash. Deleting the cache loses no
engineering fact.
