# RFC-0001: Verification backends

| | |
| --- | --- |
| Status | Accepted; delivered by the OpenSpec change `fang-verification` |
| Author | Animesh Chouhan |
| Date | 2026-09-21 |
| Supersedes | nothing; extends "Simulation Is A Compiler Target" and "Verification Level Selection" in the kernel spec |

RFC 2119 keywords are normative. Section 6 is the normative part; everything
before it is the argument for it, and everything after it is what is
deliberately left out.

## 1. Summary

The kernel already holds constraints it cannot decide. `require(self.ripple <=
30 * mV)` over a parameter nobody has a number for evaluates to undecided, and
stays undecided, because nothing in the toolchain reads a value back from a
solver into the graph. `fang sim` lowers a deck and runs ngspice, and what comes
back is a finding printed to a terminal; the constraint that motivated the run
never hears about it. Meanwhile a program can write `Verifies("rail_tolerance",
result="PASS")` and the coverage query believes it.

This RFC adds the layer that closes that loop. A program declares a
**question**: which requirement it verifies, which parameters it will measure,
under what **bench** (sources, loads, analysis window), and how. The kernel
**routes** the question to the cheapest verification level that can decide it,
lowers it into the native input of a **tool** behind one protocol, runs the
tool across a process boundary, brings the numbers back as `Decimal`
**measurements**, and re-enters them through the commit gate: the measured
parameters as inferred values with the evidence as their source, the run as an
`Evidence` entity, and the declared `Verification` with its result filled in.
The constraint that was undecided is then decided by the evaluator that already
exists, and a measurement that would violate a hard constraint does not advance
the head — it is recorded as a failed verification, with the proposal's
rejection as the explanation.

The tools are ngspice and Xyce for circuit questions, KiCad's ERC for rule
questions over the schematic fang draws, and Touchstone models for RF
questions. The survey in section 3 ranks every open-source tool considered and
says why the field, thermal and layout solvers wait for a physical layer the
EIR does not yet hold.

## 2. Motivation

Three things are wrong today, and each is a small gap with a large consequence.

**The level selector has no input.** `simulation.select_level` takes five
booleans a caller has to fill in. Nothing looks at a constraint and decides
which level can settle it, so the spec's "cheapest level that can decide a
question" is a function nobody calls.

**The result has nowhere to land.** `NormalizedResult` carries assertions as
strings and a finding as a dictionary. `ingest_external_results` turns results
into prose claims on `Evidence` entities, with the actor hard-coded to
`kicad-drc`. No path exists from a simulated number to a parameter the
constraint evaluator can read, so a simulation can never decide a constraint.

**A verification can be asserted.** `Verifies(..., result="PASS")` records a
pass that no computation produced. The buck regulator example does exactly
this, by method "analysis", with two datasheet citations as its evidence. That
is a citation, not a verification.

The consequence is that the toolchain can describe a design and check what is
decidable by inspection, and cannot yet check what is only decidable by
computing something. Everything a solver could tell the design is stranded on
the far side of a process boundary.

## 3. Survey: open-source tools, ranked by value

Value here is a product of three things: **which questions the tool decides**
that the kernel cannot decide itself; **how close its input is to what the
kernel already holds** — a netlist and parameters, which exist, or copper
geometry, which does not; and **what it costs to depend on** — a binary on the
path found at run time costs nothing to the core install, a Python package
with a compiled stack costs an extra, and a licence that reaches across the
process boundary costs a conversation.

Everything below is reached across a process boundary or read as data. Nothing
is linked into the kernel, and the kernel never binds to a wrapper library in
place of emitting a tool's native input — that is the existing requirement,
and PySpice is excluded from the table for exactly that reason.

The two tools installed on the machine this was written on were verified
against their installed versions (ngspice 45.2, kicad-cli 9.0.8). Everything
else is described from its published documentation, and a claim about it is
verified before it is written against — the same rule the agent-surface stage
applied to the MCP SDK.

### 3.1 Tier 1 — decides questions now, from what the kernel already holds

| Tool | Licence | Decides | Input it needs | Level | Delivered |
| --- | --- | --- | --- | --- | --- |
| **ngspice** | BSD-3 | Operating point, transient (ripple, overshoot, settling, startup), AC (corner, gain, phase margin), DC sweeps, noise | The SPICE deck the kernel already lowers; a bench | circuit | this change |
| **KiCad CLI** (`kicad-cli sch erc`) | GPL-3 | Electrical rules over the schematic fang draws: undriven inputs, conflicting drivers, unconnected pins | The `.kicad_sch` the schematic compiler already writes | external (rule check) | this change |
| **Touchstone models** (`.sNp`, read in-tree) | file format, no licence | Return loss, VSWR and insertion loss at a frequency, through an L or π matching network, from a vendor's or a VNA's measured N-port | A model file the part declares; the matching values the graph holds | equation | this change |
| **Xyce** | GPL-3 | Everything ngspice does, plus sensitivity analysis and parallel sweeps: a thousand compensation networks ranked in one run | The same deck; Xyce's own `.print` and measure-file conventions | circuit | this change, as a backend that reports unsupported where it is not installed |

ngspice is first because it is the only tool that answers the question every
power rail asks — *what does the output actually do under load* — and the deck
it needs already exists. KiCad ERC is second not because its rules are deep
(fang's own compatibility check covers the electrical ones on the graph) but
because it is the manufacturer's-eye check on the artifact fang ships, it costs
one subprocess, and it establishes the rule-check path DRC will use once there
is a board. Touchstone reading is third because an RF question over a chip
antenna is otherwise unanswerable, the model is data the part carries, and
evaluating it is closed-form arithmetic: no solver, no dependency, and it is
the cheapest level in the ladder. Xyce is fourth because it costs almost
nothing once ngspice is behind a protocol, and a second SPICE dialect is what
proves the protocol is not secretly ngspice-shaped.

### 3.2 Tier 2 — decides questions now, at the cost of a dependency

| Tool | Licence | Decides | Cost | Level | Status |
| --- | --- | --- | --- | --- | --- |
| **scikit-rf** | BSD-3 | N-port composition beyond a cascade, de-embedding, calibration, vector fitting, mixed-mode (differential) parameters | Python extra pulling numpy and scipy | equation / symbolic | named as the `rf` extra; not required by anything in this change |
| **SymPy** + **Lcapy** | BSD-3 / LGPL-3 | Symbolic transfer functions and poles of linear networks: the *symbolic* level the spec names, which today has no implementation | Python extra; Lcapy pulls SymPy and numpy | symbolic | follow-on change |
| **atlc** | GPL-2 | Characteristic and differential impedance of a trace from its stackup cross-section, by 2-D field solution | A binary; needs only a stackup and a trace geometry, not a routed board | external | follow-on, first thing after a stackup exists |
| **OpenVAF** | GPL-3 | Compiles Verilog-A device models to ngspice's OSDI interface: a model supply, not an analysis | A binary at model-compile time | — | follow-on; widens what "the part carries a model" can mean |

scikit-rf is the one the original proposal ranked highest, and it is the one
this RFC deliberately reads *around*. Reading a Touchstone file and cascading
two-ports is a hundred lines of complex arithmetic the standard library does;
what scikit-rf adds — de-embedding, calibration, fitting — is real, and it is
worth an extra when a question needs it. Making every RF question pay for a
numpy stack to answer "is S11 below −10 dB at 2.44 GHz" would be the wrong
trade.

### 3.3 Tier 3 — decides questions the kernel cannot yet ask

These need copper: traces, planes, a stackup, placement. The EIR's kernel
architecture names the physical entities — footprint, pad, board, layer,
region, the placement and routing constraints — and none of them is
implemented. Fang places parts and names nets; it does not route. Every tool
in this tier is blocked on that layer, and is ranked here by what it will be
worth once the layer exists.

| Tool | Licence | Decides | Needs | Level |
| --- | --- | --- | --- | --- |
| **FastHenry** | MIT's own permissive licence | Loop inductance and resistance of a switching hot loop, a return path, a via: *moving C17 3.2 mm closer cuts the loop from 8.4 nH to 3.1 nH* | Conductor geometry of the loop | external |
| **KiCad CLI** (`kicad-cli pcb drc`) | GPL-3 | Clearance, width, annular ring, courtyard, and schematic parity on the board | A `.kicad_pcb` | external (rule check) |
| **openEMS** (+ **CSXCAD**; **gerber2ems** for the Gerber path) | GPL-3 / LGPL-3 / Apache-2.0 | Full-wave S-parameters of an antenna, a transition, a coupled pair; radiated fields | A mesh over a selected region of the board | external |
| **Palace** | Apache-2.0 | Full-wave FEM: the same questions as openEMS, on a finite-element mesh, scaling across cores | A mesh | external |
| **Elmer FEM** (+ **Gmsh**) | GPL-2 / LGPL-2.1, GPL-2 | Junction and board temperature from component dissipation, copper area and the environment | A meshed board with per-component power | external |
| **FasterCap** / **FastCap** | LGPL-2.1 / MIT-style | Parasitic capacitance of a pad, a plane cut-out, a guard ring | Conductor and dielectric geometry | external |
| **PyBERT** + **PyIBIS-AMI** | BSD-3 | Channel eye and jitter over an IBIS-AMI model | A channel model, which needs a routed trace | behavioural |
| **gerbonara** / **pcb-tools** | MIT / Apache-2.0 | Reading and checking the manufacturing artifacts fang will one day emit | Gerbers | external (rule check) |

The right first step into this tier is not a solver. It is the physical layer
itself, as its own OpenSpec change, with the invariant that a `.kicad_pcb` is
an interchange encoding of that layer and never a second store of the same
facts. The second step is atlc, because a stackup is enough for it, and
"USB_D+ is 90 Ω differential" is the most common layout question a rail-and-
signal design asks. The third is FastHenry, because a hot-loop number is the
placement argument that turns *"CIN should be closer"* into a measurement.

### 3.4 Considered and set aside

| Tool | Why not |
| --- | --- |
| **PySpice** | A wrapper. The kernel emits native SPICE; binding to a wrapper is what the spec's "Simulation Is A Compiler Target" forbids. |
| **Qucs-S / Qucsator** | Its ngspice and Xyce backends are the ones already here; its own simulator adds transmission-line primitives that ngspice also has. Re-evaluate if the S-parameter-in-a-SPICE-deck path is wanted. |
| **Gnucap** | A third SPICE without a question the first two leave open. |
| **OpenModelica**, **SystemC-AMS** | The behavioural level for system simulation. Nothing in the examples asks a question at that level yet; a switching converter's *ideal* model is a circuit-level model with assumed provenance, and that is the honest place for it today. |
| **Freerouting**, **KiKit** | Routing and panelization are *doing*, not *verifying*; they are tools a plan calls, not backends a question routes to. |
| **CalculiX**, **OpenFOAM** | Structural and CFD are beyond any question a board program declares. |
| **LTspice** | Not open source. Its `.subckt` libraries are readable by ngspice, so vendor models written for it remain usable as data. |

## 4. Design

### 4.1 Terms

- A **question** is what a program declares when it says a requirement is to
  be verified by computation: the requirement it serves, the parameters it
  will measure into, the **measures** that produce them, the bench, and the
  method. It elaborates to a `Verification` entity whose result is `UNKNOWN`
  until a tool answers it.
- A **bench** is the explicit operating condition of a run: sources applied at
  part surfaces, loads applied at part surfaces, the analysis and its window.
  Nothing about a bench is defaulted.
- A **measure** is one named number a tool is asked for: a peak-to-peak, an
  average, a maximum, a value at a time or frequency, a crossing, a return
  loss. It names the surface it is taken at and writes into one parameter.
- A **tool** is a backend behind the protocol in 4.3. It has a level, it says
  whether it is installed, and it never answers a question it cannot decide.
- A **level** is one of the five in the spec: equation, symbolic,
  behavioural, circuit, external. The **equation** level is the kernel's own
  constraint evaluator and runs no tool.
- A **measurement** is a `Decimal` quantity with the tool, its version, the
  job it came from and a confidence. It is the only thing that crosses back
  from a tool into the kernel.

### 4.2 The loop

```text
Fang program
   |  Simulates(...) / Checks(...) / Evaluates(...)   -- a question, declared
   v
Verification entity, result UNKNOWN          Constraint over the measured parameter,
(what it verifies, the bench, the measures)  evaluating to undecided
   |
   v
route(question) --> level, tool              equation: already decided, no tool runs
   |
   v
tool.prepare(snapshot, question) --> Job     the native input: a deck, a schematic,
   |                                         a model file and a frequency
   v
tool.run(job, workspace) --> RawRun          across a process boundary; version recorded;
   |                                         unsupported if the tool is absent
   v
tool.read(job, raw) --> Measurements         Decimal at the boundary, nothing else
   |
   v
Transaction against the head:
   SetParameter(measured, Value.inferred(source=EVD, confidence))
   AddEntity(Evidence: the run, structured)
   RemoveEntity + AddEntity(Verification: result, evidence, level)
   |
   v
KernelGraph.propose --> the constraint check runs over the measured value
   |
   +-- accepted:  commit; the constraint is decided
   +-- rejected:  a hard constraint failed; the head does not move;
                  the failure is recorded as a Verification FAIL with the
                  Evidence, in a second transaction that touches no parameter
```

### 4.3 The tool protocol

```python
class Tool(Protocol):
    name: str                 # "ngspice", "xyce", "kicad-erc", "touchstone"
    level: Level

    def covers(self, question: Question) -> bool: ...
    def available(self) -> bool: ...
    def version(self) -> str: ...
    def prepare(self, snapshot, question, *, traits) -> Job: ...
    def run(self, job: Job, *, workspace: Path) -> RawRun: ...
    def read(self, job: Job, raw: RawRun) -> tuple[Measurement, ...]: ...
```

`prepare` is a lowering and is deterministic: the same snapshot and question
give a byte-identical `Job`, whose `input` is the tool's native text and whose
`assumptions` and `coverage_gaps` say what the run does not cover. `run` is
the only method that leaves the process, and it records the version with the
raw output. `read` is a parser and produces nothing that was not in the raw
output. A tool that is not installed answers `available() == False`, and the
runner reports the question **unsupported**, naming the tool; it never falls
through to a different tool with a different level, because a cheaper answer
is not the same answer.

ngspice, Xyce, KiCad ERC and the Touchstone reader implement this. The
existing `NgspiceBackend`, `compile_plan`, `lower_to_spice` and `normalize`
remain the machinery underneath the ngspice tool; the tool adds what was
missing — subcircuit instantiation for modelled parts, bench devices,
measurement directives, and a parser for what ngspice prints.

Two things learned against the installed ngspice, recorded so the next reader
does not re-learn them: `.meas ac` in a batch deck reports the *real part* of
a node voltage where the same line inside a `.control` block reports the
magnitude (an RC corner came back as 1024 Hz against the correct 1592 Hz), so
the ngspice lowering emits measurements through a control block; and `.print
op` is not honoured in batch mode, so operating-point values are read from a
`print` in the same block.

### 4.4 Routing

`route(snapshot, question)` returns the level and the tool:

1. If every constraint over the question's measured parameters already
   evaluates to a decided status on the snapshot, the level is **equation**,
   no tool is named, and the run records that nothing ran. This is the spec's
   "a question an equation can decide does not run a simulator", made
   concrete: the equation is the constraint evaluator.
2. Otherwise the question's method names the level — `simulation` is circuit,
   `rule check` is external, `model` is equation — and the first registered
   tool at that level whose `covers()` accepts the question is chosen, in
   registration order, which is fixed and documented.
3. If no tool covers it, the question is **unroutable**, which is reported and
   is not an error of the design.

The chosen level and tool are written onto the `Verification` entity, so a
cheap answer is distinguishable from an expensive one in the graph and not
only in a log.

### 4.5 The bench is explicit

A circuit question without a bench is not runnable, and the runner says so
rather than assuming a source. A bench names:

- **supplies**: `{"dc_in.dc": 12 * V}` — a part surface and a voltage. The
  surface's `vcc` and `gnd` pins become the source's nodes.
- **loads**: `{"rail_out.dc": 1.5 * A}` or `{... : 2.2 * Ohm}` — a part
  surface and a current sink or a resistance, by dimension.
- **analysis**: the existing `OperatingPoint`, `Transient`, `ACSweep` or
  `DCSweep`, with its window.
- **abstracted**: parts deliberately left out of the deck, each named.

Every bench item is written into the job as an assumption, and every part
abstracted is a coverage gap, so a reader of the evidence sees the conditions
the number holds under. A surface a bench names that no pin map resolves is an
error at prepare time, naming the surface.

### 4.6 Re-entry through the gate

The measurement transaction carries three kinds of operation and nothing
else: `SetParameter` on each measured parameter with `Value.inferred(quantity,
source=<evidence id>, confidence)`, `AddEntity` of one `Evidence` per run whose
`extensions["measurement"]` carries the structured record (tool, version,
level, job hash, each measure's name and quantity, assumptions, coverage
gaps), and the replacement of the declared `Verification` — removed and
re-added with the same identity — now carrying the result, the evidence and
the level. Identity is preserved because the verification is the same
declaration; its provenance gains a record for the run.

The transaction is proposed like any other. The constraint check the gate
already runs is what decides the constraint over the measured parameter. Two
outcomes:

- **Accepted.** The runner commits. The constraint is decided, the
  verification reads `PASS`, and the parameter carries an inferred value whose
  source is the evidence.
- **Rejected because a hard constraint over the measured value failed.** The
  head does not move: canonical state never holds a value that violates a
  hard constraint, and the rejection's diagnostics are the explanation. The
  runner then proposes a second transaction that adds the `Evidence` and
  replaces the `Verification` with result `FAIL` and touches no parameter.
  That one passes, because evidence of a failure is not itself a failure. The
  design is recorded as having failed its verification, with the number that
  failed it, and the constraint stays undecided in the graph — which is true:
  the design has no accepted value for it.

A rejection for any other reason — a stale base, a malformed entity — is
reported as it is and nothing is recorded.

The confidence of an inferred measurement is bounded by the provenance of the
models it rests on: `1` for a run over primitives and vendor models, lower
where a model's provenance is *assumed* (an ideal switch standing in for a
controller). The exact scale is the tool's to state and the evidence records
it; a program can require a confidence but the layer never raises one.

### 4.7 Determinism

- A `Job` is a function of the snapshot and the question. Two preparations of
  the same question over the same snapshot are byte-identical, and the job's
  hash is recorded on the evidence.
- Every number crosses the boundary as a `Decimal` under the kernel's fixed
  context. A tool that computes in binary floats — the Touchstone reader's
  complex arithmetic — quantizes to six significant figures before the
  boundary, and the RFC states this so a reader knows where the rounding is.
- Tool versions are recorded on every evidence entity. Two runs on two
  versions of ngspice are two pieces of evidence, not one.
- Seeds are recorded where a tool takes one; none of the delivered tools does.
- A committed example output that carries a measured number is compared by
  the suite like every other output. It is regenerated on the machine's
  installed tool, so a tool version that moves a number in its fourth
  significant figure moves the committed file, and the diff says so. The
  listing prints three significant figures for this reason; the evidence keeps
  all of them.

### 4.8 The authoring surface

Questions are rationale declarations, filed beside `Requires` and `Verifies`,
because a verification is engineering reasoning and belongs in the same place
as the rest of it:

```python
class Rail3V3(System):
    rail_tolerance = Requires("The 3V3 rail holds 3.3 V within 3% for 0 to 1.5 A ...")

    ripple = Parameter("V", description="peak-to-peak on the rail at full load")
    output = Parameter("V", description="the rail's average at full load")

    under_load = Simulates(
        "rail_tolerance",
        measures={
            "ripple": PeakToPeak("rail_out.dc", after=1 * ms, until=1.2 * ms),
            "output": Average("rail_out.dc", after=1 * ms, until=1.2 * ms),
        },
        supplies={"controller.vin": 12 * V},
        loads={"rail_out.dc": 1.5 * A},
        analysis=Transient(stop="1.2ms", step="10ns"),
        abstracted=("dc_in", "protection", "reverse"),
    )

    def constraints(self):
        require(self.ripple <= 30 * mV)
        require(self.output >= 3.2 * V)
        require(self.output <= 3.4 * V)
```

`Checks("layout_rules", tool="kicad-erc", excluded={"endpoint_off_grid":
"fang draws its sheet on its own grid"})` declares a rule-check question; an
excluded rule is recorded on the evidence with its reason, never dropped.
`Evaluates("antenna_match", measures={"return_loss": ReturnLoss("antenna.rf",
at=2.44 * GHz, through=("series_l", "shunt_c"))})` declares an RF question
over a part that carries a `Touchstone` model.

Measures name a **part surface** — `rail_out.dc`, `antenna.rf` — and the
surface's pin map resolves it to pins, which the netlist resolves to nodes.
A system's own surface is not a valid probe, because it has no pins of its
own; the error names the surface and says so.

### 4.9 The command

`fang verify board.py` routes every declared question, runs the tools that
are installed, prints one block per question — level, tool, each measure's
number, result, or *unsupported* naming what is missing — and exits non-zero
if any verification failed. With `--commit` and a workspace, the measurement
transactions are applied to the workspace's graph. Without a workspace the
run is reported and nothing persists, which is what an example's committed
`verification.txt` is.

`fang sim` stays as the low-level command it is: compile a plan, lower a
deck, run it, print a finding. `fang verify` is the command that reads the
answer back.

## 5. Phasing

| Stage | Change | Delivers | Needs |
| --- | --- | --- | --- |
| 13 | `fang-verification` (this RFC) | Questions, benches, measures, the tool protocol, routing, re-entry through the gate; ngspice, Xyce, KiCad ERC, Touchstone; `fang verify`; three examples | nothing new: ngspice and kicad-cli found on the path |
| 14 | `fang-physical` | The physical layer of the EIR: board, layers, stackup, footprints and pads as entities, placement and routing constraints in the one registry, `.kicad_pcb` as interchange | a design conversation about identity for physical entities |
| 15 | `fang-fields` | atlc for impedance from the stackup; FastHenry for loop parasitics; KiCad DRC over the board; openEMS or Palace over a selected region; Elmer for temperature | stage 14 |
| — | `fang-symbolic` | Lcapy behind the symbolic level; scikit-rf behind the `rf` extra for composition beyond a cascade | nothing; independent of 14 |

Stage 13 is deliberately the whole loop on the narrowest tools, because the
loop is the design and the tools are backends.

## 6. Requirements

These are the normative statements the OpenSpec delta spec carries into the
kernel spec, word for word where it can.

### R1. Questions Are Declared

A Fang program SHALL be able to declare a verification question beside the
requirement it serves: the parameters it measures into, the measures that
produce them, the method, and for a circuit question the bench. The question
SHALL elaborate to a `Verification` entity with result `UNKNOWN`, carrying its
source location, and a program SHALL NOT be able to declare a computed result
for it.

### R2. The Bench Is Explicit

A circuit question SHALL name every source and load applied and the analysis
window, each at a part surface a pin map resolves. The runner SHALL NOT supply
a default source, load or window. Every bench item SHALL be recorded on the
job as an assumption, every abstracted part as a coverage gap, and a bench
naming a surface no pin map resolves SHALL be refused naming the surface.

### R3. The Cheapest Level Is Chosen And Recorded

The runner SHALL route a question to the cheapest level that can decide it. A
question whose constraints the kernel's evaluator already decides SHALL be
answered at the equation level with no tool run. The chosen level and tool
SHALL be recorded on the `Verification` entity. A question no registered tool
covers SHALL be reported unroutable rather than answered by a tool at another
level.

### R4. Tools Sit Behind One Protocol

Every tool SHALL implement `covers`, `available`, `version`, `prepare`, `run`
and `read`. `prepare` SHALL be deterministic over the snapshot and the
question. `run` SHALL cross a process boundary or read a declared model file,
and SHALL record the tool's version. `read` SHALL produce `Decimal`
measurements and nothing the raw output did not contain. A tool that is not
installed SHALL report unsupported by name and SHALL NOT be substituted.

### R5. Measurements Re-enter Through The Gate

A measurement SHALL enter canonical state only as a transaction against the
committed head carrying `SetParameter` operations with inferred values whose
source is the run's `Evidence`, that `Evidence` with the structured
measurement record, and the replacement of the declared `Verification` under
its original identity. The constraint over a measured parameter SHALL be
decided by the existing constraint check in the gate and by nothing else.

### R6. A Failing Measurement Is Recorded, Not Applied

WHEN the measurement transaction is rejected because a hard constraint over a
measured value failed, the head SHALL NOT move, the rejection SHALL be
returned with its diagnostics, and the runner SHALL record the `Evidence` and
the `Verification` with result `FAIL` in a transaction that sets no
parameter. A rejection for any other reason SHALL record nothing.

### R7. Rule Checks Are Evidence

A rule-check question SHALL run the external checker over the artifact the
kernel lowers, SHALL record every violation the checker reports with its rule,
severity and the items it names, and SHALL record each excluded rule with the
declared reason. A violation of error severity SHALL make the verification
`FAIL`; a warning SHALL NOT.

### R8. A Touchstone Model Is Data

A part MAY carry a Touchstone model as a trait with its provenance. An RF
question over it SHALL be answered by reading the file and composing the
named matching parts in closed form, at the equation level, and the
measurement's confidence SHALL be bounded by the model's provenance. A
frequency outside the file's range SHALL be refused rather than extrapolated.

### R9. The Verify Command

`fang verify` SHALL route and run every declared question, print each
question's level, tool, measurements and result or the reason it did not run,
exit non-zero when any verification failed, and persist measurements only with
`--commit` into an existing workspace.

### AT-V1. Acceptance: an undecided constraint is decided by a run that entered through the gate

GIVEN a program declaring a parameter with no value, a hard constraint over
it, and a circuit question measuring into it with an explicit bench, WHEN
`verify` runs with the tool installed, THEN the constraint that was undecided
is decided on the committed head, the parameter's value is inferred with the
run's evidence as its source, the verification names its level and tool, and
the evidence names the tool's version. AND WHEN the same run is made with the
constraint tightened past the measured value, THEN the head does not move and
the verification reads `FAIL` with the same evidence.

## 7. Non-goals and open questions

- **No geometry.** Nothing here reads or writes a board. Section 3.3 is the
  argument for doing that as its own change.
- **No optimization.** The proposal that motivated this RFC ends with a loop
  that proposes component changes and re-simulates. That is a layer above
  this one; its unit of work is a transaction through `propose`, and this
  layer is what gives it a number to rank by.
- **No agent tool yet.** The MCP surface gains nothing in this change. A
  read-only `verifications` projection listing questions and their routes is
  cheap and can follow; running tools from an agent session raises a sandbox
  question — a tool spawns a process — that deserves its own requirement.
- **Open: confidence scale.** The tools state a confidence in `[0, 1]`
  bounded by model provenance, and nothing in the kernel yet consumes it
  beyond recording. A policy that refuses to commit an inferred value below a
  confidence is the obvious next use, and is a `Policy` field, not a runner
  concern.
- **Open: sweeps.** Xyce's value is in sweeps and sensitivities. A question
  that measures into a *range* rather than a scalar — ripple across a load
  range — needs the measure to say so and the parameter to be a range
  quantity. `Quantity` already represents ranges; the measures do not yet
  produce them.
