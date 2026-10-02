---
title: Verification
description: Questions, benches, measures, the tools that answer them, and fang verify.
sidebar:
  order: 7
  attrs:
    data-icon: approve-check
---

A verification question is declared beside the requirement it serves. It names
the parameters it measures into and the measures that produce them, and a
program cannot state its answer. `fang verify` routes each question to the
cheapest level that can decide it, runs the tool there, and brings the
measurements back through [the commit gate](/concepts/the-commit-gate/).
[Verification](/concepts/verification/) explains why it works this way; this
page lists what there is.

```bash
fang verify board.py              # route and run every question; nothing persists
fang verify board.py --commit     # persist the measurements into the workspace
```

## Declaring a question

Three declarations from `fang.verification`, and `Emulates` from
`fang.emulation`, all filed with `Requires` and `Verifies` in a class body. Each elaborates to a `Verification` entity whose
result is `UNKNOWN`, and each refuses a `result` argument with `SIM-0002`.

| Declaration | Method | Answered by |
| --- | --- | --- |
| `Simulates` | `simulation` | a circuit simulator, on a bench the question names |
| `Checks` | `rule check` | an external checker, over an artifact the kernel lowers |
| `Evaluates` | `analysis` | a data model a part carries, in closed form |
| `Emulates` | `emulation` | the board's firmware, run in an emulator ([Emulation](/reference/emulation/)) |

`Verifies(..., method="inspection", result="PASS")` stays for verifications by
inspection and test: a person states the result, it is not a question, and
nothing routes it.

### Simulates

```python
ripple = Parameter("mV")
output = Parameter("V")

under_load = Simulates(
    "rail_tolerance",
    measures={
        "ripple": PeakToPeak("rail_out.dc", after=1 * ms, until=1.2 * ms),
        "output": Average("rail_out.dc", after=1 * ms, until=1.2 * ms),
    },
    supplies={"controller.vin": 12 * V},
    loads={"rail_out.dc": 2.2 * Ohm},
    analysis=Transient(stop="1.2ms", step="10ns"),
    abstracted=("dc_in", "protection", "reverse", "rail_out"),
)

def constraints(self):
    require(self.ripple <= 30 * mV)
```

| Argument | Is |
| --- | --- |
| `measures` | Parameter name to measure. Each name must be a parameter the module declares (`SIM-0001`), in a unit the measure produces (`UNIT-0001`) |
| `supplies` | Part surface to voltage. Each becomes a `V` device |
| `loads` | Part surface to a current, which becomes an `I` device, or a resistance, which becomes an `R`. Anything else is `SIM-0005` |
| `analysis` | `OperatingPoint`, `Transient` or `ACSweep`. Under AC each supply is also the stimulus, at its own magnitude |
| `abstracted` | Parts, or blocks of parts, left out on purpose. Each is a coverage gap |
| `tool` | A tool to route to, if the question insists on one, such as `"xyce"` |

**Nothing about a bench is defaulted.** A question with no supply or no
analysis still elaborates, and is reported not runnable (`SIM-0004`) rather
than run against a source nobody chose. Every bench item is recorded on the run
as an assumption.

### Measures

A measure names a part surface the way the program does, `"rail_out.dc"`, and
elaboration resolves it to pins through the part's pin map. A surface with a
ground wire is measured from its signal pin to its return; a single-wire
surface, against the simulator's ground; `"part.surface.signal"` names one wire.
A system's own surface has no pins and is refused with `SIM-0003`.

| Measure | Takes | Produces |
| --- | --- | --- |
| `PeakToPeak(surface, after=, until=)` | Highest minus lowest voltage in the window | volts |
| `Average(surface, after=, until=)` | Mean voltage in the window | volts |
| `Maximum(surface, after=, until=)` | Highest voltage in the window | volts |
| `Minimum(surface, after=, until=)` | Lowest voltage in the window | volts |
| `ValueAt(surface, at=)` | The voltage at a time, a frequency, or the operating point | volts |
| `Crossing(surface, level=, edge=, occurrence=, after=)` | Where the voltage crosses a level | seconds, or hertz in an AC sweep |
| `ReturnLoss(surface, at=, through=, reference=)` | -20 log10 \|Gamma\| through matching parts | dB |

Windows are times in a transient and frequencies in an AC sweep; a window in the
wrong dimension is refused where it is written. A filter's corner is a
`Crossing` of the level 1/sqrt(2) of the drive, falling.

### Checks

```python
sheet_rules = Checks(
    "sheet_spec",
    excluded={
        "endpoint_off_grid": "fang draws its sheet on its own grid",
        "lib_symbol_issues": "fang draws its own symbols",
    },
)
```

A rule check measures into no parameter. Errors fail the verification and
warnings do not. An excluded rule does neither, and an exclusion without a
reason is refused with `SIM-0008`. On a sheet fang draws, the two rules above
fire on every symbol, which is why a question names them rather than the tool
hiding them.

### Evaluates

```python
self.antenna.add_trait(Touchstone(source="chip_antenna.s1p", ports=("FEED",),
                                  provenance=...))

matched = Evaluates(
    "match_spec",
    measures={"return_loss": ReturnLoss("antenna.rf", at=2.44 * GHz,
                                        through=("shunt_c", "series_l"))},
)
```

`through` names the matching parts in order from the port toward the model.
Each is a shunt element when a terminal is on ground and a series element
otherwise, and its value is the one the graph holds; a part with no value
leaves the question unanswered, naming the part. A frequency outside the file is
refused naming its range (`SIM-0007`).

## Routing

`route()` picks the level and the tool, cheapest first:

1. If every constraint over the question's measured parameters already
   evaluates to a decided result, the **equation** level answers it with the
   constraint evaluator, and no tool is prepared or run.
2. Otherwise the method names the level -- `simulation` is circuit, `rule
   check` is external, `analysis` is equation, `emulation` is behavioural -- and the first registered tool
   at that level that covers the question is chosen, the one it names if it
   names one.
3. A question nothing covers is **unroutable**. It is not answered at another
   level, because a cheaper answer is not the same answer.

The route is the same on every machine: a tool is chosen whether or not it is
installed, and one that is not installed is reported **unsupported** by name.
Nothing stands in for it.

## The tools

| Tool | Level | Covers | Needs |
| --- | --- | --- | --- |
| `ngspice` | circuit | `Simulates`: operating point, transient, AC | `ngspice` on the path |
| `xyce` | circuit | `Simulates`: transient, AC, when the question names it | `Xyce` on the path |
| `kicad-erc` | external | `Checks` over the schematic | `kicad-cli` on the path |
| `touchstone` | equation | `Evaluates` with `ReturnLoss` | nothing: it is fang |
| `renode` | behavioural | `Emulates` | Renode 1.17.0 on the path |

That is the routing order. A module that brings a tool adds it with
`register_tool()`, after the built-ins, and a method with `register_method()`;
`fang.emulation` adds `renode` and the `emulation` method that way when it is
imported.

Every tool sits behind one protocol: `covers`, `available`, `version`,
`prepare(snapshot, question, traits=)`, `run(job, workspace=)` and
`read(job, raw)`, with an optional `verdict(job, raw)` for a tool that judges
rather than measures. Preparing is a lowering and is deterministic; running is
the only step that leaves the process; reading produces decimal quantities and
nothing the output did not contain.

A SPICE deck instantiates each modelled part as an `X` device in its model's
port order, through the trait's `pin_map`, and includes the model by path rather
than inlining it. ngspice measures through a `.control` block, because in batch
mode it ignores `.print op` and reports a deck-level `.meas ac` as a real part.
Xyce gets the same circuit with deck-level `.MEASURE` lines, and is read from
the measure file it writes.

## Re-entry

An answer enters as one transaction against the committed head:

- each measured parameter set to an **inferred** value whose source is the
  run's evidence, with the run's confidence;
- one `Evidence` entity carrying the measurement record: the tool and its
  version, the level, the job's hash, each measure with its value or the reason
  it has none, the assumptions, the coverage gaps, and the digest of every input
  file the snapshot does not hold;
- the declared `Verification`, replaced under its own identifier with its
  result, the evidence, the level and the tool.

The gate's constraint check decides the constraint. If a hard constraint over a
measured value fails, the head does not move; the evidence and the verification
with result `FAIL` are recorded by a second transaction that sets no parameter.
Any other rejection records nothing. Measurements prepared against a snapshot
that is no longer the head are refused with `TXN-0001`.

Confidence is bounded by the provenance of the models a run rests on: 1 for
primitives and asserted models, 0.8 for inferred, 0.5 for unverified ones and
for a model with no provenance at all. `assumed_provenance(reason)` states the
last kind.

## The command

```bash
fang verify board.py
```

Each question is printed with its level, its tool and version, its measurements
at three significant figures, its assumptions, coverage gaps and confidence, and
its result, or the reason it did not run.

| Outcome | Exit |
| --- | --- |
| Every question answered and none failed | `0` |
| A verification failed | `1` |
| A question not runnable, or refused by the gate for another reason | `1` |
| A tool not installed, or a question no tool covers | `0` |
| No question declared: "nothing to verify" | `0` |

Without `--commit` nothing is written: runs happen in a scratch directory and
the workspace is left as it was. `--commit` persists the new head into an
existing workspace, keeping each run's files under `.copperhead/simulations/`.
`fang build`, `fang diff` and `fang verify` keep what earlier runs measured: a
program declares a measured parameter without a value, so elaborating it again
does not withdraw the measurement.
