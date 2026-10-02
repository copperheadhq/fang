# Design: Verification Backends

## Context

See [proposal.md](proposal.md) for motivation. The normative text this change
implements is copperhead RFC 12 version 1.3, Sections 12.7 to 12.10
([copperheadhq/copperhead-rfcs#6](https://github.com/copperheadhq/copperhead-rfcs/pull/6));
this document is informative. It holds the tool survey that ranks what the
change delivers and what it leaves for later, the facts the design was checked
against, and the decisions that map the RFC onto fang's code. What shapes the
approach is what already exists, because most of the loop does:

- `simulation.compile_plan`, `lower_to_spice`, `NgspiceBackend` and `normalize`
  already turn a snapshot into a deck, run ngspice across a process boundary,
  and record the version. The lowering emits only two-terminal primitives: a
  part with a subcircuit model gets an `.include` line and no device.
- `simulation.select_level` encodes the five levels and takes booleans nobody
  supplies.
- `Value.inferred(quantity, source, confidence)` is already the value status
  for "computed or extracted; carries source and confidence".
- `SetParameter`, `AddEntity` and `RemoveEntity` already exist, and `AddEntity`
  refuses an identifier that is present.
- The gate's constraint check already evaluates every constraint whose scope a
  transaction touches, and blocks on a failed hard one.
- `rationale.Verifies` already elaborates to a `Verification` entity through
  `elaborate._rationale_entity`, with sibling names resolved in the declaring
  module's scope. `Entity.extensions` is the namespaced place for what the
  schema has no field for.
- `schematic.compile_schematic` and `KicadRenderer` already write a
  `.kicad_sch` and run `kicad-cli` against a scratch copy.
- `ingest_external_results` already refuses results not produced against the
  committed head.

Three things are wrong today, and each is a small gap with a large
consequence. The level selector has no input: nothing looks at a constraint and
decides which level can settle it. The result has nowhere to land:
`NormalizedResult` carries assertions as strings, `ingest_external_results`
turns results into prose claims with the actor hard-coded to `kicad-drc`, and
no path exists from a simulated number to a parameter the evaluator can read.
And a verification can be asserted: `Verifies(..., result="PASS")` records a
pass no computation produced, which the buck regulator example does by method
"analysis" with two datasheet citations as its evidence — a citation, not a
verification.

Verified against the installed tools rather than from memory (ngspice 45.2,
kicad-cli 9.0.8 when this was written; the machine has since moved to KiCad
10.0.6):

- ngspice ignores `.print op` in batch mode, so operating-point values are read
  from a `print` inside a `.control` block.
- A deck-level `.meas ac` reports the *real part* of a node voltage, where the
  same line inside a `.control` block reports the magnitude: an RC corner came
  back as 1024 Hz against the correct 1592 Hz. The ngspice lowering therefore
  emits measurements through a control block.
- A switching buck deck of 160 000 points runs in well under a second.
- `kicad-cli sch erc --format json` on a fang-drawn sheet reports
  `endpoint_off_grid` and `lib_symbol_issues` on every symbol, which are facts
  about the drawing and not the design.

## Survey: open-source tools, ranked by value

Value is a product of three things: **which questions the tool decides** that
the kernel cannot decide itself; **how close its input is to what the kernel
already holds** — a netlist and parameters, which exist, or copper geometry,
which does not; and **what it costs to depend on** — a binary on the path found
at run time costs nothing to the core install, a Python package with a compiled
stack costs an extra, and a licence that reaches across the process boundary
costs a conversation.

Everything below is reached across a process boundary or read as data. Nothing
is linked into the kernel, and the kernel never binds to a wrapper library in
place of emitting a tool's native input — the existing requirement, and the
reason PySpice is excluded. The two tools installed when this was written were
verified against their installed versions; everything else is described from
its published documentation, and a claim about it is verified before it is
written against.

### Tier 1 — decides questions now, from what the kernel already holds

| Tool | Licence | Decides | Input it needs | Level | Delivered |
| --- | --- | --- | --- | --- | --- |
| **ngspice** | BSD-3 | Operating point, transient (ripple, overshoot, settling, startup), AC (corner, gain, phase margin), DC sweeps, noise | The SPICE deck the kernel already lowers; a bench | circuit | this change, on the spine |
| **KiCad CLI** (`kicad-cli sch erc`) | GPL-3 | Electrical rules over the schematic fang draws: undriven inputs, conflicting drivers, unconnected pins | The `.kicad_sch` the schematic compiler already writes | external (rule check) | this change, after the spine |
| **Touchstone models** (`.sNp`, read in-tree) | file format | Return loss, VSWR and insertion loss at a frequency, through an L or π matching network, from a vendor's or a VNA's measured N-port | A model file the part declares; the matching values the graph holds | equation | this change, after the spine |
| **Xyce** | GPL-3 | Everything ngspice does, plus sensitivity analysis and parallel sweeps | The same deck; Xyce's own `.print` and measure-file conventions | circuit | this change, after the spine, reporting unsupported where not installed |

ngspice is first because it answers the question every power rail asks — *what
does the output actually do under load* — and the deck it needs already exists.
KiCad ERC is second not because its rules are deep (fang's own compatibility
check covers the electrical ones on the graph) but because it is the
manufacturer's-eye check on the artifact fang ships, it costs one subprocess,
and it establishes the rule-check path DRC will use once there is a board.
Touchstone reading is third because an RF question over a chip antenna is
otherwise unanswerable, the model is data the part carries, and evaluating it
is closed-form arithmetic. Xyce is fourth because it costs almost nothing once
ngspice is behind a protocol, and a second SPICE dialect proves the protocol is
not secretly ngspice-shaped.

### Tier 2 — decides questions now, at the cost of a dependency

| Tool | Licence | Decides | Cost | Level | Status |
| --- | --- | --- | --- | --- | --- |
| **scikit-rf** | BSD-3 | N-port composition beyond a cascade, de-embedding, calibration, vector fitting, mixed-mode parameters | Python extra pulling numpy and scipy | equation / symbolic | named as a future `rf` extra; nothing here imports it |
| **SymPy** + **Lcapy** | BSD-3 / LGPL-3 | Symbolic transfer functions and poles of linear networks: the symbolic level, which has no implementation | Python extra | symbolic | follow-on change |
| **atlc** | GPL-2 | Characteristic and differential impedance of a trace from its stackup cross-section | A binary; needs a stackup and a trace geometry | external | follow-on, first thing after a stackup exists |
| **OpenVAF** | GPL-3 | Compiles Verilog-A device models to ngspice's OSDI interface: a model supply, not an analysis | A binary at model-compile time | — | follow-on |

scikit-rf is read *around* deliberately. Reading a Touchstone file and
cascading two-ports is a hundred lines of complex arithmetic the standard
library does; what scikit-rf adds is real, and worth an extra when a question
needs it, but making every RF question pay for a numpy stack to answer "is S11
below −10 dB at 2.44 GHz" would be the wrong trade.

### Tier 3 — decides questions the kernel cannot yet ask

These need copper: traces, planes, a stackup, placement. The kernel names the
physical entities and implements none of them; fang places parts and names nets
and does not route. Every tool here waits on that layer.

| Tool | Licence | Decides | Needs | Level |
| --- | --- | --- | --- | --- |
| **FastHenry** | permissive | Loop inductance of a hot loop, a return path, a via | Conductor geometry | external |
| **KiCad CLI** (`kicad-cli pcb drc`) | GPL-3 | Clearance, width, annular ring, courtyard, schematic parity | A `.kicad_pcb` | external (rule check) |
| **openEMS** (+ CSXCAD, gerber2ems) | GPL-3 / LGPL-3 / Apache-2.0 | Full-wave S-parameters of an antenna, a transition, a coupled pair | A mesh over a region | external |
| **Palace** | Apache-2.0 | Full-wave FEM, the same questions as openEMS | A mesh | external |
| **Elmer FEM** (+ Gmsh) | GPL-2 / LGPL-2.1 | Junction and board temperature | A meshed board with per-component power | external |
| **FasterCap** / **FastCap** | LGPL-2.1 / MIT-style | Parasitic capacitance of a pad, a cut-out, a guard ring | Conductor and dielectric geometry | external |
| **PyBERT** + **PyIBIS-AMI** | BSD-3 | Channel eye and jitter over an IBIS-AMI model | A routed trace | behavioural |
| **gerbonara** / **pcb-tools** | MIT / Apache-2.0 | Reading and checking manufacturing artifacts | Gerbers | external (rule check) |

The first step into this tier is not a solver but the physical layer itself, as
its own change, with a `.kicad_pcb` as an interchange encoding of that layer and
never a second store. The second is atlc, because a stackup is enough for it;
the third is FastHenry, because a hot-loop number turns *"CIN should be closer"*
into a measurement.

### Considered and set aside

| Tool | Why not |
| --- | --- |
| **PySpice** | A wrapper; binding to it is what "Simulation Is A Compiler Target" forbids. |
| **Qucs-S / Qucsator** | Its ngspice and Xyce backends are the ones already here. |
| **Gnucap** | A third SPICE without a question the first two leave open. |
| **OpenModelica**, **SystemC-AMS** | The behavioural level for system simulation; nothing in the examples asks a question there yet. |
| **Freerouting**, **KiKit** | Doing, not verifying: tools a plan calls, not backends a question routes to. |
| **CalculiX**, **OpenFOAM** | Beyond any question a board program declares. |
| **LTspice** | Not open source. Its `.subckt` libraries remain usable by ngspice as data. |

## Goals / Non-Goals

**Goals:**

- One loop, reusing the evaluator, the value model, the operations and the gate
  as they are. The layer adds a runner and lowerings; it adds no second
  resolver, no second evidence store and no new operation kind.
- Every new behaviour testable without a binary: preparation, parsing, routing
  and re-entry are pure; only `run` needs the tool, and those tests skip by
  name.
- Examples that are real boards with real questions, whose committed outputs
  the suite regenerates and compares.
- The spine first. Questions, routing and the protocol, re-entry and `fang
  verify` land as one unit proven on ngspice; Xyce, rule checks and Touchstone
  follow on the same protocol.

**Non-Goals:**

- No board geometry, and so no FastHenry, openEMS, Elmer or DRC (Tier 3 above).
- No optimization loop: a loop that proposes component changes and
  re-simulates is a layer above this one, whose unit of work is a transaction
  through `propose`; this layer gives it a number to rank by.
- No agent tool. A read-only projection listing questions and their routes is
  cheap and can follow; running tools from an agent session spawns a process,
  and that needs its own requirement.
- No change to `fang sim`, `select_level`'s signature, or any existing
  requirement's text.

## Decisions

### The loop

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

### A question is a `Verification` entity, not a new kind

The spec's knowledge layer already has the entity: "what it verifies, the
method used, the evidence it rests on, and its result". A question is that
entity before its result is known. The declarations `Simulates`, `Checks` and
`Evaluates` subclass `Verifies`, fix their method, refuse a `result` argument,
and carry their bench and measures into `Verification.extensions["question"]`
as a canonical dictionary. `Verification` gains two optional fields, `level`
and `tool`, written by the run.

*Alternative considered:* a `question` entity kind with its own prefix and
collection. It would double the bookkeeping — a question and a verification
for the same fact — and the coverage query would need to join them. One entity
whose result moves from unknown to decided is the simpler truth.

*Alternative considered:* the bench as `Model` entities attached to the ports
they drive. A bench is a condition of a verification, not a property of the
circuit; two questions over one board have two benches.

### The authoring surface

Questions are rationale declarations, filed beside `Requires` and `Verifies`,
because a verification is engineering reasoning and belongs with the rest of
it:

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

`Checks("layout_rules", tool="kicad-erc", excluded={"endpoint_off_grid": "fang
draws its sheet on its own grid"})` declares a rule-check question.
`Evaluates("antenna_match", measures={"return_loss": ReturnLoss("antenna.rf",
at=2.44 * GHz, through=("series_l", "shunt_c"))})` declares an RF question over
a part carrying a `Touchstone` model.

### The measured value enters as an inferred parameter, through `SetParameter`

This is what makes the existing evaluator decide the constraint. The
alternative — a resolver overlay that consults evidence — would be a second
place a parameter's value can come from, which is exactly what the governing
invariant forbids.

The program declares the parameter without a value, so re-elaborating it says
nothing about the value and must not withdraw a committed measurement; RFC 12
Section 12.7 states the ownership this rests on, and the delta spec carries it
as a scenario. Fang's spec has no per-fact ownership check yet, so the
behaviour is held by the elaboration diff leaving an inferred value with a
source in place when the program supplies none.

The confidence of an inferred measurement is bounded by the provenance of the
models it rests on: `1` for a run over primitives and cited vendor models,
lower where a model's provenance is *assumed* (an ideal switch standing in for
a controller). The exact scale is the tool's to state and the evidence records
it; a program can require a confidence but the layer never raises one.

### Replacing the verification is `RemoveEntity` then `AddEntity`

Both exist; applied in order inside one transaction they replace an entity
under its identifier, and the diff reports it as modified. A new `ReplaceEntity`
operation would be tidier and is not needed, and the agent surface's operation
table would have to learn it.

### A failing measurement takes two proposals

The first proposal carries the parameters, and the gate rejects it when a hard
constraint fails — correctly: the head must not hold a violating value. The
runner recognises that case by the rejection's diagnostics naming a constraint
whose references include a measured parameter, and proposes a second
transaction with the evidence and the failed verification only. Anything else
that rejects the first proposal is surfaced untouched.

*Alternative considered:* a policy flag letting an "observation" transaction
through despite a failing constraint. It is a gate bypass, and the first thing
the agent surface would have to be forbidden from using.

### The tool protocol is structural, and the SPICE tools share one lowering

`Tool` is a `typing.Protocol`. `SpiceTool` holds the shared preparation —
plan, devices, subcircuit instances, bench devices — and is parameterised by a
dialect object that writes the analysis and measurement lines and parses the
output: `NgspiceDialect` emits a `.control` block and parses `name = value`
lines from stdout; `XyceDialect` emits `.measure` lines and parses the
`.mt0`-style measure file. `NgspiceBackend` is reused unchanged for `run`;
`XyceBackend` is its sibling. Because the dialect is a seam from the start,
landing ngspice first and Xyce later changes no shared code.

Subcircuit instantiation reads the model file's `.subckt` line for the port
order and maps the part's pins through the trait's `pin_map`; a port the map
does not reach is a preparation error naming it. The model path is resolved
against the program's folder, which the elaboration's source location gives,
and the model file's digest is recorded among the evidence's inputs, because
the snapshot does not hold the file.

### Probes are part surfaces

`"rail_out.dc"` resolves through the part's pin map to its `vcc` and `gnd`
pins, and `spice_nodes` gives their nodes. A two-terminal `Electrical` surface
resolves to its one pin, measured against node 0. This keeps probes in the
vocabulary the program is written in and needs no connection-graph walk. A
system's own surface has no pins and is refused by name.

The resolution needs module structure the snapshot does not keep (pin maps
live on the `Part` class). `elaborate` therefore records, for each question,
the resolved pins per surface — as `(component id, vendor pin name)` pairs —
inside the question dictionary at elaboration time, where the module tree is
in hand. The runner then needs only the snapshot.

### Touchstone is read in-tree; scikit-rf is not a dependency

Option-line parsing (`# GHZ S MA R 50`), the three formats, renormalization
and a series/shunt cascade into a one-port are complex arithmetic in the
standard library. Results are quantized to six significant figures before
becoming `Decimal`, so the last bits of `math.log10` cannot differ between
platforms in a committed output.

### Rule checks: exclusions are declared, with reasons, and recorded

fang's sheet is drawn on its own grid with its own symbol library, so two ERC
rules fire on every symbol. They are not hidden by the tool; the *question*
excludes them, each with a reason, and the evidence records the rule, the
reason and the count excluded.

### Determinism

- A `Job` is a function of the snapshot and the question. Two preparations of
  the same question over the same snapshot are byte-identical, and the job's
  hash is recorded on the evidence.
- Every number crosses the boundary as a `Decimal` under the kernel's fixed
  context. A tool that computes in binary floats — the Touchstone reader's
  complex arithmetic — quantizes to six significant figures before the
  boundary. The reader's frequencies are not among those floats: they are read
  from the file's text and scaled to hertz as decimals, because `2.01 * 1e9`
  is 2009999999.9999998 and a question at a file's last point was refused as
  outside it.
- Tool versions are recorded on every evidence entity. Two runs on two versions
  of ngspice are two pieces of evidence, not one.
- Seeds are recorded where a tool takes one; none of the delivered tools does.

### Diagnostics go in the `SIM` area

`SIM-0001..` are allocated for: a question naming an undeclared parameter, a
question stating a result, an unresolvable surface, a missing bench, a load of
the wrong dimension, a model port the pin map does not reach, a frequency
outside a model's range, an exclusion without a reason. The area list in the
spec does not change.

### Example outputs carry three significant figures

`verification.txt` prints measured numbers at three significant figures and
omits tool versions; the evidence keeps every figure and the version. The
suite compares the file like any other and skips it, by name, where the tool
is absent — the precedent is `schematic.svg`, which already depends on the
installed KiCad. A committed output carrying a measured number is regenerated
on the machine's installed tool, so a version that moves a number in its
fourth significant figure moves nothing in the listing, and one that moves it
further shows up as a diff a person reads.

### Settled while building the spine

Groups 1 to 7 are built. None of the decisions above had to change; these are
the details they left open, settled the smallest way that works, and the two
places the shipped examples differ from the sketches above.

**The extension points** `fang-emulation` codes against, all in
`fang/verification.py`. `QuestionDeclaration(Verifies)` owns the fixed method
(`fixed_method`), the refusal of a `result` (SIM-0002), the check that every
measure writes a declared parameter, and the canonical
`extensions["question"]` built by `elaborate_question(module, project_id=)`,
which `elaborate` calls on any verification declaration that has it; a kind of
question overrides `named_surfaces()`, `resolve_surface(module, name)`,
`measured_dimension(measure)` and `question_fields(module)`. A measure kind
subclasses `Measure` and registers by its `kind`. `METHOD_LEVELS` and
`register_method(method, level)` map a method to a level; `route()` reads
them and holds no closed set. `Tool` is a runtime-checkable `Protocol`;
`register_tool(tool, before=None)` appends to `TOOLS` in routing order,
ngspice first. A `Job` is a bundle: `files` (relative path to text or bytes),
`assumptions`, `coverage_gaps`, `inputs` (path to digest), `extra` (the tool's
own record fields), `confidence`, and, outside its hash, `snapshot` and
`sources` (where each input is read from on this machine); `Job.single` and
`Job.input` keep the one-file case short. `RawRun` carries the version, the
exit status, stdout, stderr, output files and a terminal `Status`.
`Measurement` carries a `Quantity` or, with no value, a `reason`, which the
evidence records; only a measurement with a value sets a parameter.

**Equation-level answers.** The tool recorded is `evaluator`. An unanswered
question whose measured parameters all hold values and whose constraints are
already decided is answered by replacing its
verification with the evaluator's result, its evidence being whatever entity
the measured values name as their source. A question already answered with the
same result is reported `current` and nothing changes, so asking again on a
head where ngspice answered it leaves the circuit-level record in place. This
is how `rc_filter` shows one question at two levels: answered by ngspice on
the elaborated program, then, on the head that run committed, routed to the
equation level with nothing run. The listing shows both passes. A measured
parameter with no value keeps the question off the evaluator even where no
constraint reads it: deciding the others would otherwise pass a question one of
whose measures nobody took.

**A run's result** is FAIL when any constraint over a measured parameter
fails, UNKNOWN when a measure has no value or no constraint reads the measured
parameters, and PASS when every one passes. It is predicted with the gate's own
evaluator so the verification can carry it, and the proposal is rebuilt on the
rare disagreement with the gate's check results, which decide.

**Evidence identity** is derived from the verification's path and a digest of
the job's hash, the tool and its version: the same run is the same evidence, so
asking again with the same job and version runs nothing and adds no duplicate,
and a tightened constraint fails on the same evidence the passing run had. Such a
run's recorded measurements re-enter through the gate (`reenter(...,
recorded=evidence)`): the parameters are set from the measurement record, the
evidence is cited as it stands, and the verification gains a
`verification_reentry` provenance record rather than a second run record. The
gate decides on the head as it is now, so a FAIL whose constraint has been
relaxed passes, and a PASS whose constraint has become undecided is unknown; the
answer is `current`, with nothing committed, only when the gate decides what the
head already holds. A verdict is the checker's own over the same job and is not
re-judged, so a rule check asked again is current as before. A
run that did not complete is tried again when asked, each attempt recorded as
evidence of its own (`run_<digest>_retryN`), so a crash does not stand in for
an answer. A tool that turns out to be missing only when it is run is reported
unsupported, like one missing before. The
measurement record follows RFC 3 Section 14, carrying the run's terminal status,
where it ran (`ran`, `local` unless a tool's job says `hosted`, set once as the
record's own field for every tool) and its confidence, and adds the exit status
and message; a measure with no value appears in `measures` with its `reason` in
place of a value, and a tool's `extra` fields sit beside the record's own,
refusing their names.

**The constraint check reads what a constraint reads.** Its scope was each
constraint and its targets; it now includes every entity the expression
references. Without that, a measured parameter on one module constrained by
another module would be set with the constraint never evaluated, and the
decision would not be the gate's.

**Models and confidence.** `Simulatable` gains `not_modelled`, whose items
become coverage gaps on every run over the model. A model's confidence is read
from its latest provenance record -- asserted 1, inferred 0.8, unverified 0.5
-- and a model with no provenance counts as unverified, as an uncited claim is
an assumption; `assumed_provenance(reason)` states it. A model's relative path
resolves against the declaring program's folder, the deck includes it by that
same relative path (an absolute or escaping path becomes `models/<name>`), and
the run copies it beside the deck. Two parts declared in different folders may
name different files by one relative path; named by the path alone they shared
one bundle entry and one include, so one part ran the other's model.
`bundle_paths` keeps the relative path where it names one file and, where two
different files would share it, names each `<digest>/<path>` under the first
twelve hex digits of its own digest, which is as machine-independent; the same
file named twice is one entry, and the Touchstone reader names its files the
same way. Two different files declaring one subcircuit are refused, naming the
parts, because a deck holds one definition (ngspice warns of a redefinition
and ignores it), so distinct includes alone would still run one model for
both. A port several pins land on, as a part's ground pins do, is reached
through one node: pins on different nodes are refused under SIM-0006, naming
the part, the port and each pin's net, and a pin on no net carries nothing, so
the port is taken through a pin on a net where the part has one. A primitive
is written from the value the graph holds, in SI decimals; one with no value
is refused, never written as 1.

**The bench under AC.** Each supply is also the AC stimulus, at its own
magnitude, and the job records that as an assumption. A question with no
analysis is not runnable under SIM-0004, as one with no supply is.

**The command's exit.** Failed is non-zero, as the spec requires; so is a
question the program left unrunnable or a measurement the gate refused for
another reason, since the work the command names did not happen. Unsupported
and unroutable are zero. Runs go to a scratch directory, and only `--commit`
writes, into `.copperhead/simulations` and the record stream. The head `verify`
starts from is the program elaborated afresh with what runs measured carried in,
which no transaction proposed, so `--commit` writes it only once the gate has
seen it whole: every entity proposed against an empty snapshot with the default
checks, exactly as `build` gates what it writes (the workspace keeps records,
not typed entities, so the persisted head cannot be rebuilt to propose a
re-elaboration against). That head carries the program as it is now, so
committing it would persist an edit made since the last build past `build`'s
tool plan, when `--commit` promises measurements and nothing else. Before
anything runs, `--commit` carries the persisted measured facts onto the fresh
elaboration whatever their currency (`carry_measurements(..., current=...)`
with a test that keeps every run) and compares the result with the persisted
records, entity by entity. An unchanged program gives the persisted design
back; anything else is an edit, a retuned part or a tightened constraint among
them, and the commit is refused, saying to run `fang build` first. The files a
program reads are outside the comparison, so a measurement made stale by an
edited model or a rebuilt firmware runs again and its answer is committed.
Entities are compared as records rather than by snapshot hash, so a newer
compiler that elaborates the same design is not an edit, and run evidence no
verification cites any more (a retried run's first attempt, left on the head)
is set aside, since a run left it and the next build drops it. The whole-design
gate stays behind the comparison. The `stale:` lines are judged on the
committed runs laid over the fresh elaboration, since a bound firmware is
found beside the program that declares its part; on the runs alone it fell
back to the working directory and read as missing.

**Re-elaboration keeps a measurement while it is current.** `carry_measurements`
keeps an answered verification, its evidence and the values that evidence is the
source of, wherever the fresh elaboration declares the same question and every
run it rests on is still current; a changed question is answered afresh. The
question's own description covers neither the circuit nor a model file nor the
firmware, so it cannot say whether a run is still current; preparing the
question afresh can. A run is current while routing its question on the fresh
elaboration and preparing it with the program's traits gives the job hash the
measurement record names (`Currency`). The hash covers the native input, the
digest of every input the snapshot does not hold and the question, and not the
snapshot's hash, so a 10 kOhm resistor changed to 22 kOhm, an edited model or a
rebuilt firmware image drops the measurement, and `verify` runs the question
again instead of reporting the old PASS current at the equation level. Whether
the tool is installed, and which version, is not consulted: it is machine state,
and letting it decide what a rebuild keeps would make `fang build` give
different snapshots on different machines. A run on another version is evidence
of its own the next time the question is asked. A program cannot state a measured value: a default or an
assignment on a measured parameter fails elaboration with SIM-0002, the code a
stated result gets, since the value would be the question's answer and would let
the evaluator answer it with nothing run.
A carried value is judged against the constraints the fresh elaboration states,
as the gate's constraint check judges it, in identifier order with what is
carried before it. One that a constraint tightened since now fails is not
carried: its verification is carried with result FAIL and its evidence, and the
parameter left without a value. That is what the failure-recording transaction
leaves when the same run re-enters under the tightened constraint, record for
record, so RFC 12 section 12.9's rule (a failing value never reaches the head,
and the failure is recorded) holds for a rebuild too. Before, the carried value
reached the design, `build`'s gate refused it, and `verify --commit` refused the
edit, so the workspace could not move until the design changed; now `build`
persists the edit and reports the failure, and a relaxed constraint lets the
recorded run re-enter and pass with nothing run again.
`reelaboration(head, elaborated)` is the transaction, empty for an unchanged
program. `build`, `diff` and `verify` rebuild the head around the facts read
back from the workspace's record stream (`MeasuredFacts.from_records`, with
`from_dict` readers on `Quantity`, `Value`, `Identity`, `SourceLocation` and
provenance), in the revision they were committed in, so an unchanged program
rebuilt after a commit is the committed snapshot byte for byte.

**The buck example's bench** differs from the sketch under "The authoring
surface": full load is 2.2 Ohm, not 1.5 A, because a resistor damps the output
filter's ring-up well inside the 1 ms the window waits and a current sink does
not -- with only the switches' resistance the ring outlasts the run and the
peak-to-peak would measure it rather than the ripple. The rail header is
abstracted beside the input parts, because a connector has no SPICE device and
the load is applied at its surface. `ripple` is declared in mV.

**Xyce** is the second dialect on the same seam, `XyceDialect` with
`XyceBackend`, registered after ngspice; it answers a question that names it
(`tool="xyce"`) or one ngspice does not cover, and covers transient and AC
questions, not operating points. Its deck is the ngspice deck up to the solver
options: the options are each simulator's own form -- Xyce's tolerances and
integration method are `TIMEINT` options, and `vntol`, which has no Xyce
counterpart, is named in a comment -- so "only the analysis and measurement
conventions differ" counts the options among those conventions. An AC measure
reads `VM`. Xyce is not installed here, so its lowering and its measure-file
reader are written from the Xyce Reference Guide and tested on preparation and
on a measure file written in the guide's documented form, not one captured from
a run; `RawResult` gains `outputs` so a backend can return the files a run
wrote. The first run on a machine with Xyce is the check this cannot make.

**Rule checks answer with a verdict, not a measurement.** A rule check writes
no parameter, so its result cannot come from a constraint. A tool may define
`verdict(job, raw) -> Verdict` beside `read`: the result, the fields its
evidence carries beside the measurement record's own, and the lines a listing
shows. The runner asks for it when the tool has one; for a question with no
measured parameters the verdict is the result, and for one with parameters the
constraints still decide and a failing verdict can only make it worse. The
ERC verdict records every violation with its rule, severity, description and
items, each declared exclusion with its reason and count, and the error and
warning totals; errors fail and warnings do not. The ERC job carries the sheet
fang draws with the snapshot's hash replaced -- the job names its snapshot
beside itself -- so the job is the same wherever the program was read from.
The report format was captured from kicad-cli 10.0.6, as the risk note below
asks, and a trimmed capture is the parser's fixture. The reader requires that
schema, `erc.v1`, and every field it reads (the sheets, their violations, and
each violation's rule, severity, description and items); read leniently, a
report of a changed schema or with no sheets was a report of no violations and
passed. Such a report fails the run with the reason, so its evidence is
recorded as a run that did not complete, no verdict is drawn and the
verification stays unknown. `Checks` defaults to no
named tool and routes by method; the built-in tools load on first use of the
registry, because `rulecheck.py` imports `verification.py`.

**Touchstone questions.** `Evaluates` fixes the method `analysis`, which
routes to the equation level, where the in-tree `touchstone` tool covers a
question whose measures are all `ReturnLoss`. The tool is always available and
its version is fang's. `through` names the matching parts in order from the
port toward the model; the record carries each with its position, because the
record stream sorts any list it does not know to be ordered. A part is a shunt
element when one of its terminals is on ground and a series element otherwise,
and its value is the inductance, capacitance or resistance the graph holds.
The named parts must be the ladder the graph connects: counted back from the
model's port 1, each shunt part joins the node reached so far to ground and
each series part joins it to the next node toward the port, and the first part
that does not is refused under SIM-0003, naming the part, the node reached and
the nets it joins. Otherwise parts named out of order, or a typo naming some
other capacitor, composed a plausible number for a circuit nobody drew.
Return loss is positive, -20 log10 |Gamma|, against a reference of 50 Ohm
unless the measure names another; the file's own reference is honoured when
the load is read back from S11, which is how files in different references
agree. A file of more than one port is read at port 1 with the others
terminated in the file's reference, and the job says so. Interpolation is
linear in real and imaginary parts. The run re-reads the declared file and
refuses one whose digest has changed since preparation. A perfect match is an
infinite return loss. Decibels needed a unit: `dB` is dimensionless with a
factor of 1, and `GHz`, `nH` and `dB` join the literals `fang.lang` exports.
The seven bases cannot tell a decibel from a percent, so a unit also says
whether it is logarithmic (`units.LOGARITHMIC`), and a decibel is kept apart
from every linear dimensionless unit with UNIT-0001 wherever the units are
known: `converted_to` refuses the conversion either way (10 dB is not 1000
percent), an expression node carries whether it is a decibel (a `Literal` from
its quantity, a `Ref` from the declared unit `fang.lang` hands it, unserialized,
`Arithmetic` from its operands) so `Comparison` and `Arithmetic` refuse a mix
where it is written, a parameter declared in dB refuses a value in another
dimensionless unit, and a measure into a dimensionless parameter of the other
scale fails elaboration, a `ReturnLoss` into anything not declared in dB among
them. A bare number stays neutral. The design's sketch names `("series_l",
"shunt_c")`; the shipped example's antenna is below 50 Ohm, so its match puts
the shunt part at the port, `("shunt_c", "series_l")`.

**Infinity.** A quantity bound may be infinite; it serializes as `Infinity`,
which `Decimal` reads back, and compares under interval semantics. A NaN is
refused.

## Risks / Trade-offs

- [A simulator update moves a committed number] → three significant figures in
  the listing; a real move shows up as a diff in a file a person reads, which
  is the point of committing it.
- [The ideal buck model reads as a claim about the TPS62130] → the model file
  is named `ideal_buck.sub`, its trait's provenance is *assumed*, the run's
  confidence is lowered for it, and the coverage gap "the control loop is not
  modelled; duty is fixed" is recorded on the evidence and printed by `verify`.
- [Question data in `extensions` is less typed than fields] → it is a canonical
  dictionary built by one function and read by one function, and the spec's
  extension mechanism is the sanctioned place for it; promoting it to fields is
  a schema-version change that can follow once the shape has settled.
- [ERC on a generated sheet is mostly about the drawing] → accepted and stated
  in the survey: its value is establishing the rule-check path and checking the
  artifact fang ships.
- [Xyce cannot be run here] → its dialect is tested on preparation and on
  parsing a captured measure file; its `run` is tested only for reporting
  unsupported.
- [KiCad moved from 9.0.8 to 10.0.6 on this machine] → the ERC parser is
  written against JSON captured from the installed version when the rule-check
  group is built, not against the 9.0.8 output this survey saw.

## Migration Plan

Additive. `buck_regulator`'s hand-asserted `Verifies(..., result="PASS")` is
replaced by a `Simulates` question, which changes that example's committed
outputs; `python examples/regenerate.py buck_regulator` rewrites them.
`SCHEMA_VERSION` does not move: `level` and `tool` are optional fields omitted
when absent, and `extensions` already serializes.

## Phasing beyond this change

| Stage | Change | Delivers | Needs |
| --- | --- | --- | --- |
| 13 | `fang-verification` (this change) | Questions, benches, measures, the tool protocol, routing, re-entry; ngspice, then Xyce, KiCad ERC and Touchstone; `fang verify`; three examples | nothing new |
| — | `fang-mcu-parts`, `fang-emulation` | RFC 12 Sections 7.3, 7.4 and 12.11 to 12.14: firmware run in Renode as a question on this protocol | this change's spine |
| 14 | `fang-physical` | The physical layer: board, layers, stackup, footprints and pads as entities, `.kicad_pcb` as interchange | a design conversation about identity for physical entities |
| 15 | `fang-fields` | atlc, FastHenry, KiCad DRC, openEMS or Palace, Elmer | stage 14 |
| — | `fang-symbolic` | Lcapy behind the symbolic level; scikit-rf behind an `rf` extra | nothing |

## Open Questions

- Whether `verify --commit` should also re-run `build`'s tool plan. It does not
  in this change, and it refuses a program changed since the last build, so
  the design it commits into is one `build`'s plan ran over.
- The confidence scale. Tools state a confidence in `[0, 1]` bounded by model
  provenance, and nothing yet consumes it beyond recording. A policy that
  refuses to commit an inferred value below a confidence is the obvious next
  use, and is a `Policy` field, not a runner concern (RFC 12 Appendix C,
  decision 13).
- Sweeps. Xyce's value is in sweeps and sensitivities. A question that measures
  into a range rather than a scalar — ripple across a load range — needs the
  measure to say so and the parameter to be a range quantity. `Quantity`
  already represents ranges; the measures do not yet produce them.
