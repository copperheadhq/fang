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
substitute. There is no generic fallback device, because a result computed from
an invented model is worse than no result, because it looks like an answer.

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

Verification levels run one to five, cheapest first. `select_level()` picks the
cheapest level that can decide the question asked, so a question answerable by
inspection does not pay for a transient run.

## Backends

`NgspiceBackend` reaches ngspice across a process boundary. It is optional and
external; fang finds it on `PATH`.

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
