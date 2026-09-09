---
title: Rationale
description: Why a value is what it is, as entities rather than prose.
sidebar:
  order: 6
  attrs:
    data-icon: open-book
---

The reason a component has the value it has is expensive to reconstruct and
easily lost. Fang keeps it in the same graph as the component, as entities with
the same identity and provenance rules as everything else.

The goal is that `fang` answers "why is this 4.7 µH?" without anyone having
written a design document.

## What a program declares

Rationale is declared in the class body, beside the parts it is about, rather
than in a method or a comment.

```python
from fang.lang import System, A, V, uH
from fang.parts import Inductor, Regulator
from fang.rationale import Calculates, Chooses, Cites, Requires, Verifies


class Rail3V3(System):
    rail_tolerance = Requires(
        "The 3V3 rail holds 3.3 V within 3% for 0 to 1.5 A",
        priority="MUST",
        validation="analysis",
    )

    part_choice = Chooses(
        "Which converter makes the 3V3 rail?",
        selected="TPS62130",
        alternatives=[
            {"part": "LM2596", "reason": "asynchronous, and too tall for the enclosure"},
            {"part": "MP2315", "reason": "no power-good output, and the sequencing needs one"},
        ],
        requirements=("rail_tolerance",),
        evidence=("absolute_maximum",),
    )

    absolute_maximum = Cites(
        "VIN absolute maximum is 17 V, recommended operating is 3 to 17 V",
        document="SRC-DS-TPS62130",
        locator="section 6.1, absolute maximum ratings",
    )

    controller = Regulator(output_voltage=3.3 * V, output_current_max=3 * A)
    inductor = Inductor(inductance=4.7 * uH, current_rating=2 * A)

    inductor_value = Calculates(
        "L = v_out * (1 - v_out / v_in) / (f_sw * ripple_current)",
        inputs=("inductor", "controller"),
        result="4.7 uH at 1.25 MHz for 30% ripple at 1.5 A",
        requirements=("rail_tolerance",),
    )

    load_regulation = Verifies(
        "rail_tolerance",
        method="analysis",
        evidence=("absolute_maximum",),
        result="PASS",
    )
```

| Declaration | Records |
| --- | --- |
| `Requires(statement, *, priority, validation, state, source)` | A requirement the design must meet |
| `Assumes(claim, *, rationale)` | A working claim with **no** evidence behind it |
| `Cites(claim, *, document, locator)` | A claim with a document and a location within it |
| `Chooses(question, *, selected, alternatives, requirements, evidence, rationale)` | A decision, its alternatives and what it rests on |
| `Calculates(expression, *, inputs, result, requirements)` | A computed result and the inputs it depends on |
| `Verifies(verifies, *, method, evidence, result)` | What is verified, how and on what evidence |

Names bind to the attribute, so `requirements=("rail_tolerance",)` refers to the
`rail_tolerance` declaration above it. A name that resolves to nothing is
[`ELAB-0006`](/reference/diagnostics/).

`Assumes` and `Cites` are deliberately different declarations. An assumption
records the absence of evidence, and merging it with a citation would make a
design look better justified than it is.

## Coverage is computed on demand

```python
coverage(snapshot)                    # which requirements are verified and which are not
impacted_by(snapshot, changed)        # what a change puts at risk
```

Both are computed on demand from the graph, so neither can drift from the
design, and an unverified requirement is reported as unverified.

## Impact propagates through the graph

A change is classified as electrical or presentation-only, and invalidation
follows the reference edges. Moving a part on a sheet does not invalidate a
simulation. Changing the inductor invalidates the calculation that used it, the
verification that rested on the calculation and the requirement that
verification closed.

The propagation is derived from `references()`, the same method that drives
referential integrity and topology adjacency, so a rationale link visible to
validation is visible to impact analysis too.

## Evidence from outside

External results re-enter as `Evidence` through an ordinary transaction, against
the committed head, through the same gate. A simulation run, a DRC report and a
bench measurement all take that path. There is no side channel, so a
verification cannot rest on evidence the graph never saw.
