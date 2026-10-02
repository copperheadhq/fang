---
title: Simulation
description: Explicit plans and what happens when the simulator is missing.
sidebar:
  order: 6
  attrs:
    data-icon: analytics
---

Simulation is a compiler target, not a side trip. A design lowers to a SPICE
deck the same way it lowers to a netlist, and the result comes back normalized
into one shape.

```bash
fang sim board.py --analysis transient --stop 10ms --step 1us --probe "V(1)"
fang sim board.py -o deck.cir          # write the deck, whether or not it runs
```

## Nothing runs without a plan

`compile_plan()` turns a request into an explicit `SimulationPlan`. The plan
names which models will be used and the provenance that justifies each one, and
it names the analysis. Nothing runs until a plan exists, and you can inspect the
plan before anything does.

Models attach as the `Simulatable` trait. The model is **data**. The backend is
not part of it, so the same model can be run by a different simulator or by
none.

## A missing model is a rejection

If a selected component has no compatible model and is not explicitly
abstracted, the plan is **rejected with the reason** rather than run with a
substitute. There is no generic fallback device. A result computed from an
invented model is worse than no result, because it looks like an answer.

Explicit abstraction is available and has to be written down. The difference
between "this part is deliberately ideal here" and "we had nothing" is exactly
the difference the plan records.

## Analyses

| Analysis | Request |
| --- | --- |
| Operating point | `OperatingPoint`, from `--analysis op`, the default |
| Transient | `Transient`, from `--analysis transient`, with `--stop` and `--step` |
| DC sweep | `DCSweep` |
| AC sweep | `ACSweep` |

## Levels

Verification levels run one to five, cheapest first: equation, symbolic,
behavioural, circuit, external. A declared question is routed by `route()`,
which looks at the graph -- if the constraints over what it measures are
already decided, the equation level answers it and nothing runs -- and the
level and tool it chose are written on the verification. `select_level()`
remains for a caller that knows the answers to its questions already. See
[Verification](/reference/verification/).

## Models in a question's deck

A question's deck is written from the snapshot, the traits and the question.
A part carrying a `Simulatable` model with a `.subckt` file is instantiated as
an `X` device, its nodes in the order the model's `.subckt` line declares its
ports, each the node of the pin the trait's `pin_map` lands on that port. A
port no pin reaches is refused by name (`SIM-0006`). The model is included by
path, never inlined, and its digest is recorded on the run's evidence because
the snapshot does not hold the file.

```python
self.controller.add_trait(
    Simulatable(
        backends=("ngspice",),
        source="ideal_buck.sub",            # beside the program
        pin_map={"VIN": "vin", "GND": "gnd", "SW": "sw",
                 "BOOT": "boot", "FB": "fb", "EN": "en"},
        provenance=assumed_provenance("an ideal stand-in"),
        not_modelled=("the control loop is not modelled; duty is fixed",),
    )
)
```

`not_modelled` items become coverage gaps on every run over the model, and the
provenance bounds the run's confidence. A primitive is written with the value
the graph holds, in SI units with no suffix; one with no value is refused, not
written as 1.

## Backends

`NgspiceBackend` reaches ngspice across a process boundary, and `XyceBackend`
reaches Xyce the same way. Both are optional and external, and fang finds them
on `PATH`. Xyce writes its measures to a file beside the netlist, which the run
returns with what it printed.

If it is not installed, `BackendUnavailable` is reported. The plan still
compiles and the deck can still be written. The command says no run was made,
and does not substitute anything for one.

```bash
fang sim board.py -o deck.cir   # succeeds without ngspice; says nothing ran
```

## Results come back normalized

`normalize()` brings a backend's output into one shape, so what reads a result
does not know which simulator produced it. A `NormalizedResult` carries what the
run produced together with everything needed to judge it: the plan, the models
used and the assertions evaluated.

Results re-enter canonical state as `Evidence`, through an ordinary transaction
against the committed head, through [the gate](/concepts/the-commit-gate/).
There is no path by which a simulation result becomes a fact without passing it.
`fang sim` reports a run and stops there; a declared question answered by
`fang verify` is what sets a measured parameter, as an inferred value whose
source is that evidence.
