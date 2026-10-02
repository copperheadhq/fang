# Design: Verification Backends

## Context

See [proposal.md](proposal.md) for motivation and
[RFC-0001](../../../rfcs/RFC-0001-verification-backends.md) for the argument
and the tool survey. What shapes the approach is what already exists, because
most of the loop does:

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

Verified against the installed tools rather than from memory: ngspice 45.2
ignores `.print op` in batch mode and reports the real part for a deck-level
`.meas ac`, while `meas` inside a `.control` block reports magnitudes and an
RC corner correctly; a switching buck deck of 160 000 points runs in well under
a second; `kicad-cli sch erc --format json` on a fang-drawn sheet reports
`endpoint_off_grid` and `lib_symbol_issues` on every symbol, which are facts
about the drawing and not the design.

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

**Non-Goals:**

- No board geometry, and so no FastHenry, openEMS, Elmer or DRC (RFC §3.3).
- No optimization loop and no agent tool (RFC §7).
- No change to `fang sim`, `select_level`'s signature, or any existing
  requirement's text.

## Decisions

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

### The measured value enters as an inferred parameter, through `SetParameter`

This is what makes the existing evaluator decide the constraint. The
alternative — a resolver overlay that consults evidence — would be a second
place a parameter's value can come from, which is exactly what the governing
invariant forbids.

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
`XyceBackend` is its sibling.

Subcircuit instantiation reads the model file's `.subckt` line for the port
order and maps the part's pins through the trait's `pin_map`; a port the map
does not reach is a preparation error naming it. The model path is resolved
against the program's folder, which the elaboration's source location gives.

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
installed KiCad.

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
  in the RFC: its value is establishing the rule-check path and checking the
  artifact fang ships.
- [Xyce cannot be run here] → its dialect is tested on preparation and on
  parsing a captured measure file; its `run` is tested only for reporting
  unsupported. The RFC says so.

## Migration Plan

Additive. `buck_regulator`'s hand-asserted `Verifies(..., result="PASS")` is
replaced by a `Simulates` question, which changes that example's committed
outputs; `python examples/regenerate.py buck_regulator` rewrites them.
`SCHEMA_VERSION` does not move: `level` and `tool` are optional fields omitted
when absent, and `extensions` already serializes.

## Open Questions

- Whether `verify --commit` should also re-run `build`'s tool plan. It does not
  in this change; the two commands stay independent.
