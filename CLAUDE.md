# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Fang is the Copperhead hardware kernel plus the Python-embedded language that authors hardware
for it. The kernel elaborates a Fang program into the Engineering Intermediate Representation
(EIR), holds it as a live typed graph, mutates it only through validated
transactions, and lowers it into downstream artifacts.

Pure Python 3.11+, and the core install has no runtime dependencies. Two optional extras exist and
neither is imported outside the one module that needs it: NetworkX, used for graph *analysis* only —
it is never a persisted or public representation — and the MCP SDK, which only
[fang/mcp.py](fang/mcp.py)'s registration layer imports.

## Commands

```bash
pip install -e ".[dev]"          # add ",analysis" for the NetworkX-backed queries, ",mcp" for `fang mcp`
python -m pytest                 # whole suite (1639 tests): ~85s; ~7 min where Renode runs the emulations live
fang build examples/sensor_board/sensor_board.py   # the console script, after an editable install
python -m pytest -rs             # also lists the acceptance tests deferred to later phases
python -m pytest tests/test_graph.py::test_name -x
python -m pytest -k "at_k7"      # acceptance criteria are named test_at_r*/test_at_k*/test_at_v*/test_at_f*
openspec list                    # OpenSpec CLI (v1.12) drives the change workflow
python -m build                  # dist/*.whl and dist/*.tar.gz; twine check --strict them
```

There is no linter or formatter configured; match the surrounding style.

## Packaging

The distribution is **`copperhead-fang`** on PyPI (the bare name `fang` is taken
by an unrelated package); the import name stays `fang`. The version has one
source of truth, `fang.__version__`, which `pyproject.toml` reads dynamically
and the release workflow checks against the git tag — never write a version
literal anywhere else. `SCHEMA_VERSION` beside it is the serialized-EIR version
and moves independently. The sdist ships the tests, the examples they read, and
the spec, so `python -m pytest` runs from inside an unpacked sdist; keep
[MANIFEST.in](MANIFEST.in) in step when adding anything the suite reads.
[RELEASING.md](RELEASING.md) is the release procedure.

## The governing invariant

There is exactly one canonical model, the EIR. The kernel graph is its live realization;
everything else is a lowering of it, a projection of it, or an interchange encoding of it.
**Never introduce a second persisted representation of the same facts.** `ConstraintRegistry`
enforces this literally: constructing a second registry for a project raises `ELAB-0012`;
downstream tools get a generated `Projection`, never their own store.

Four further invariants the tests hold, and which any change must preserve:

- **Determinism.** Identical inputs give byte-identical snapshots. Verified across processes
  with differing `PYTHONHASHSEED` (see [tests/test_serialization.py:102](tests/test_serialization.py#L102)).
  Magnitudes are `Decimal` strings under a fixed `Context(prec=34)`, never binary floats;
  serialization sorts by Unicode code point except for the collections in
  `serialization.ORDERED_COLLECTIONS`, whose order is semantic.
- **Explicit unknowns.** `null` never means "unknown". `Value.unknown()` is a distinct status.
- **Undecided is a third truth value** (`Truth.UNDECIDED` / `CheckStatus.UNKNOWN`). An unknown
  operand makes a check undecided; it is never silently a pass or a failure. Whether undecided
  *blocks* is the gate's policy decision, made in `KernelGraph.propose`, not by the evaluator.
- **Dimensional rejection at write time.** `Arithmetic.__post_init__` checks dimensions when the
  expression is constructed, so a dimensionally invalid expression cannot be stored, let alone
  evaluated. Type and unit correctness therefore never needs re-checking in `validation.validate`.

## Architecture

The dependency order is roughly the order below; lower layers never import higher ones.

**Foundations.** [fang/units.py](fang/units.py) is dimension vectors over the seven SI bases,
unit algebra, and `Quantity` (scalar, range, or tolerance, with a decimal magnitude).
[fang/values.py](fang/values.py) wraps a quantity in a status — explicit, inferred, assumed, or
unknown — and models unresolved `ConflictingValue` candidates. [fang/identity.py](fang/identity.py)
derives identifiers as UUIDv5 over `(project namespace, "<kind>:<canonical semantic path>")`,
rendered as a prefix plus 12 hex digits, lengthened 4 digits at a time only against the revision's
existing identifier set — so re-derivation reproduces the same lengths. The three origins are
`derive()`, `authored()`, `imported()`. [fang/provenance.py](fang/provenance.py) is append-only.

**The entity model.** [fang/entities.py](fang/entities.py) holds `Entity` and its subclasses
(Component, Net/Rail, Connection, Interface/Port/Bus, Domain, Requirement, Decision, Evidence,
Model). Every entity is a frozen dataclass carrying identity, parameters, provenance, and a source
location, and exposes two protocol methods the rest of the kernel relies on:
`references()` (drives referential integrity, diff impact, and topology adjacency) and `as_dict()`
(drives canonical serialization). **A new entity kind must implement both**, and be registered in
`identity.PREFIXES` and in `graph._COLLECTION_OF`.

**Constraints.** [fang/constraints.py](fang/constraints.py) is the single registry plus a typed
expression tree (`Literal`, `Ref`, `Arithmetic`, `Comparison`, `Logical`) evaluated over
`Interval` arithmetic against a `Resolver` supplied by a snapshot. A `Ref` to an unknown value
yields `Truth.UNDECIDED`, which propagates through Kleene three-valued `and`/`or`/`not`.
[fang/topology.py](fang/topology.py) adds `TopologyConstraint` over enumerated conductive paths.

**The graph and the gate.** [fang/graph.py](fang/graph.py) is the centre of the system.
`Snapshot` is immutable and content-hashed. `Transaction` names the base snapshot it was built
against and carries `Operation`s (`AddEntity`, `RemoveEntity`, `Connect`, `SetParameter`).
`KernelGraph.propose()` applies the transaction **to a copy** and runs six gate conditions in
order: stale-base rejection, normalization into well-formed entities, structural validation,
every required `CheckClass` has run, no blocking check result, no undecided result over a
must-be-decided requirement, and policy approvals satisfied. Without a project policy the required
check classes are those whose scope meets the affected entities on the head or the candidate, so a
removal still brings in the check that covered what it removed. Condition 5 does not count a
constraint undecided only because a declared question has not yet measured, or failed to measure,
its parameter (RFC 12 §9.3). Only `commit()` advances the head.
Rejection is correct by construction — the candidate is simply discarded — and a rejected
`Proposal` still returns its diagnostics and its diff, because the explanation is the useful
output of a rejection.

Two ordering rules the gate encodes and that new code must not invert:
`materialize()` refuses a `Realization` whose parent is not the committed snapshot, and
`ingest_external_results()` refuses results produced against anything but the committed head —
external check results re-enter as `Evidence` through an ordinary transaction.

**Interfaces and pins.** [fang/interfaces.py](fang/interfaces.py) is the catalogue and the pin
model; [fang/lowering.py](fang/lowering.py) turns an interface connection into pin connections,
choosing in declared order and recording each choice as a `Decision`. A port may name its
peripheral instance (`peripheral="I2C1"`), and a candidate may carry a `Selector` or `AF(n)` cited
from a `Cites` on the same part; the chosen pin's selector lands on the pin `Connection` as
`selectors`, never on the `Pin`, because one pin serves several ports. An I2C port's address is a
dimensionless parameter or a `Strap` keyed by the device's own pins.
`compatibility.resolve_address` is the one reader of either: it resolves a strap from the inferred
nets when asked and never stores the result beside the strap, so the addressing rule and anything
else that needs an address cannot disagree.

**Lowerings.** [fang/netlist.py](fang/netlist.py) projects a snapshot to a netlist and
[fang/kicad.py](fang/kicad.py) emits it; [fang/schematic.py](fang/schematic.py) is the
schematic compiler the spec's architecture names, lowering a snapshot to a `.kicad_sch`.
It draws its own symbols rather than reading an installed KiCad's, so the file is a
function of the snapshot and nothing else; connectivity is a global label on every pin,
because fang places parts and names nets but does not route. `KicadRenderer` runs
`kicad-cli` across a process boundary and strips the one timestamp line KiCad writes;
it renders the ordinary KiCad picture — background, frame, title block — with fang's own
`DRAWING_SHEET` rather than the installed KiCad's, whose title block prints that KiCad's
version, and the page is cut to leave the frame and the block their room.
[fang/copperhead.py](fang/copperhead.py) is a second schematic lowering: it writes copperhead's
netlist intent (`schematic.intent.json`) from a snapshot and runs `copperhead draft schematic`
across the same kind of process boundary, and copperhead places and wires the sheet with KiCad's
library symbols. A part is drawn with the symbol it declares as `symbol = "library:name"` (which
also reaches the netlist as its `libsource`), else its part type's (op amps, diodes, meters,
lamps), else `power:GND` for a ground marker, else its designator prefix's (`SYMBOL_OF_PREFIX`);
each symbol maps the part's pins where KiCad numbers them differently, so pins land by name. The
ground net's name, terminal names, short values and the date are explicit options, the same
defaults for every caller. `examples/draw_figures.py` passes only those options to the same
`compile_intent`, and test_handbook holds every committed figure intent to it byte for byte. A
part with no symbol, a pin its symbol has no place for, or a net left with fewer than two drawn
pins, is reported as a loss.

**Firmware emulation.** [fang/emulation.py](fang/emulation.py) runs a board's compiled firmware
against the board in Renode, as one more verification question: `Emulates` sits on the question
base in [fang/verification.py](fang/verification.py), and importing `fang.emulation` registers the
`emulation` method at the behavioural level and the `renode` tool after ngspice. `compile_plan`
resolves everything from the snapshot and the traits before anything runs: the target and its
firmware, each I2C bus's controller (the port's `peripheral`), pins and selectors (the lowered
connections), open drain (the interface), addresses (`resolve_address`), observed pins (the
platform descriptor's own pin table, never a pin's name). Otherwise it refuses with `SIM-0009`..`SIM-0016`.
[fang/renode/](fang/renode/) lowers the plan to Renode's own `.repl` and `.resc` and runs it on a
temporary copy in its own process group; its package data is the F401 platform description, the
C# probes (`probes/fang_probes.cs`) and the model descriptors (`models/*.json`), which say what
each model covers and which of its warnings are expected. Things learned against Renode 1.17.0
that the code depends on: durations are written as decimal seconds (it reads `"100ms"` as 100 s),
files are named `$ORIGIN/...` (its launcher runs from its install directory) and it cannot include
a script from a path with a space (so such a temporary directory is reported unsupported), probes
are named `fang_` plus the device's full path (they share a namespace with the platform's
peripherals, and two that would collide are refused), and the GPIO output-type register is judged
by the firmware's writes because Renode does not store it. A measure gives an
absent event in a completed run as the half-open range after the run's end, nothing for a run
that timed out, and nothing over a model that warned of something its descriptor does not expect;
a warning is matched only against the descriptor of the model that raised it. An address must be a
whole number and a selector one the platform reads (AF0 to AF15 on the F401). A run keeps its
bundle, events, log and outcome in the workspace it is given, and `fang emulate` fails on a run that
did not complete.
The bundle's plan names no snapshot, so an unrelated design change leaves the job current. The
firmware's digest goes on evidence, never in the snapshot; `stale()` resolves the bound path
exactly as a run does (`_firmware_location`, against the program that declares the part) and
compares the digest with the file.
Emulation models are `EmulationModel` traits, not `Simulatable`, because the trait registry holds
one trait per protocol per entity.

**Above the graph.** [fang/validation.py](fang/validation.py) checks identifier uniqueness,
referential integrity, provenance traceability, prohibited cycles, contradictory mandatory
constraints, and the requirement state machine. [fang/diff.py](fang/diff.py) classifies each
change as electrical or presentation-only and propagates invalidation.
[fang/queries.py](fang/queries.py) answers rationale questions on demand.
[fang/serialization.py](fang/serialization.py) is canonical JSON and the record stream.
[fang/diagnostics.py](fang/diagnostics.py) is a code registry over the areas
`ELAB IFACE TOPO UNIT TXN SIM IMPORT MCP`; **codes are allocated, never reused, and retired rather
than deleted** — add new ones via `_allocate` at the bottom of the relevant area block.

**Verification.** [fang/verification.py](fang/verification.py) turns an undecided constraint into
a decided one without a second way in. A question (`Simulates`, `Checks`, `Evaluates`, all on
`QuestionDeclaration`) is a `Verification` entity whose result is `UNKNOWN`, carrying the
canonical question in `extensions["question"]` with every surface resolved to pins at elaboration;
a program cannot state its result, nor give a measured parameter a value (`SIM-0002`). `route()`
answers at the equation level only when every measured parameter holds a value and every constraint
over them is decided, and otherwise picks the first registered tool at
the level the method names (`METHOD_LEVELS`), installed or not, so a missing tool is reported
unsupported rather than replaced. Tools sit behind the `Tool` protocol (`covers`, `available`,
`version`, `prepare`, `run`, `read`, optionally `verdict`) and trade in a `Job` bundle, a `RawRun`
and `Measurement`s; the built-ins, in routing order, are ngspice and Xyce (`SpiceTool` over the
lowering in [fang/simulation.py](fang/simulation.py)), KiCad ERC ([fang/rulecheck.py](fang/rulecheck.py))
and Touchstone ([fang/rf.py](fang/rf.py)), and `register_tool` adds more. A run's measurements
re-enter as one transaction (inferred `SetParameter`s sourced from the run's `Evidence`, that
evidence with the measurement record, the verification replaced under its own identifier) and the
gate's constraint check decides; a measured value that fails a hard constraint never reaches the
head and is recorded as a `FAIL` by a second transaction that sets no parameter.
`carry_measurements` keeps a measurement across re-elaboration only while it is current, meaning
preparing the question again gives the job hash its record names; the job covers bundle files and
input digests (firmware, models) and never the snapshot or the installed tool version, so currency
is the same on every machine. A run already recorded for the same job and version re-enters from its
record through the gate instead of running. `fang verify` writes nothing without `--commit`, and
`--commit` persists measurements only: it refuses a program whose design no longer matches the
persisted records, which is `fang build`'s to persist. A rebuild carries a measurement that a
since-tightened constraint now breaks as that failure: the verification `FAIL`, the value withheld,
exactly what `failure_transaction` records. A provenance record appended to an existing entity
names its `fields` (`parameters.<name>.value` on the part, `evidence`, `level`, `result` and `tool`
on the verification). The Xyce dialect has run against a Xyce 7.10 build. A run's bundle names a model by its relative
path, or by `<digest12>/<path>` where two different files would share one.

**The agent surface.** [fang/mcp.py](fang/mcp.py) serves the kernel over the Model Context Protocol,
as `fang mcp`. It is two layers, and the split is load-bearing: everything above `build_server` is a
projection from kernel state to canonical-JSON-ready dictionaries and imports nothing from the SDK,
so the surface is testable without a client and the core install stays dependency-free;
`build_server` is the only place that imports `mcp`. A `Session` is bound to one project root named
when the server starts, and `Session.resolve` is the single gate every client-named path passes.
Mutation is `KernelGraph.propose` and `KernelGraph.commit` — never `apply()`, because splitting them
is what makes the rejection's explanation available before the state moves. An agent may advance the
head, and what bounds it is the gate's policy condition, not a check in the adapter, so **never
construct a more permissive `Policy` here than the project's**.

## The spec is the contract

The working contract is [openspec/specs/fang-kernel/spec.md](openspec/specs/fang-kernel/spec.md),
a self-contained normative document: terminology, design principles, layers of representation,
kernel architecture, and the project root, then 111 requirements over 373 scenarios and 26
acceptance tests. There is no other standards document in this repository — the spec is the whole
contract. Read the relevant requirement before changing kernel behaviour. Module docstrings quote
the requirement they implement by name (e.g. `Spec: "The Commit Gate"`) — keep that link intact.

Upstream of the spec sits copperhead RFC 12, *The Copperhead Hardware Kernel and Fang Language
Standard*, with RFC 3 for the EIR, in `copperheadhq/copperhead-rfcs`. That series is the one
normative home for a requirement: a new kernel capability is proposed there as a revision first,
and an OpenSpec change here cites it by RFC number, version, and section (the RFC repository's
README, "From standard to code", has the flow and the rules). The spec may be more specific than
the RFC, as a mapping must be, and never contradicts it. Surveys, spike findings, and the facts a
design was checked against go in the change's `design.md`, which is informative; this repository
keeps no separate RFC or design-note directory.

[tests/test_acceptance.py](tests/test_acceptance.py) holds exactly one test per acceptance
criterion, AT-R1..AT-R13, AT-K1..AT-K10, AT-V1, AT-F1 and AT-F2, and all 26 pass. The only skips in the suite are for optional binaries
that may not be installed (NetworkX, the MCP SDK, ngspice, Xyce, kicad-cli, copperhead, renode); each names what is missing. If a
criterion ever has to be deferred again, skip it with the reason named rather than weakening the
assertion, so the suite reports what is actually demonstrated.

Other tests share [tests/conftest.py](tests/conftest.py), whose fixtures build one small vertical
slice (regulator, controller, rail, ground domains). Its identifiers are *computed* with `derive`
rather than written down, so fixtures cannot drift from the derivation rules; time is pinned to
`FIXED_TIME`; and an autouse fixture releases the project's `ConstraintRegistry` after each test.
Tests import it as `from conftest import ...`.

## Examples are folders, and they carry their outputs

Every example under [examples/](examples/) is a folder: `<name>/<name>.py`, a
`README.md` explaining what it is for, and the files `fang` produces from it
under `out/` — the KiCad netlist, the netlist and check and graph listings, the
views worth looking at, a `rationale.md` for the examples that record any
reasoning, and a `verification.txt` for the ones that declare a question: what
`fang verify` finds, at three significant figures and without tool versions.
That one is compared only where the tools its questions route to are installed,
and skipped by name where they are not. `python examples/regenerate.py` rewrites them all;
[tests/test_examples.py](tests/test_examples.py) rebuilds them and compares, so
a committed output cannot drift from the program beside it. An example named in
`regenerate.SCHEMATICS` also ships a `.kicad_sch` and KiCad's render of it, so
regenerating or testing that one needs `kicad-cli` on the path; without it the tests
still check every one of its outputs but the render. One named in
`regenerate.DRAFTED` also ships copperhead's draft under `out/copperhead/`, and
needs `copperhead` there too; one named in `regenerate.EMULATED` ships each emulation question's
plan, platform description and script under `out/renode/`, which need no emulator. The textbook
groups in `regenerate.FIGURES` are drafted by copperhead too, but by `examples/draw_figures.py`
into each example's `figure/`, which neither `regenerate.py` nor the suite runs. A program that
declares a module-level `BENCH` (the circuits under `examples/ti_opamp_handbook/`
do, through its `handbook.py`) is simulated too: its `out/` ships each SPICE deck
and a `simulation.txt` of measurements against claims, so it needs `ngspice`, and
[tests/test_handbook.py](tests/test_handbook.py) fails on any claim that does not
hold. Two things in an
output are normalized before that comparison and only two: the compiler version
and the snapshot hash, which covers provenance and so covers this checkout's
absolute path. Add an example by adding the folder — the suite discovers it —
and give it a `README.md` and an `out/`, or it is not an example.

## Work is organized as OpenSpec changes

[openspec/ROADMAP.md](openspec/ROADMAP.md) chunks the toolchain into 12 stages, each an OpenSpec
change with a proposal, a delta spec, and tasks. All twelve are archived under
`openspec/changes/archive/<date>-<id>/`; a new stage starts with `/opsx:propose`. The ordering is a
product ordering: stages 1–6 close the loop from a Fang program to a KiCad netlist. **All twelve
stages are delivered**, and every acceptance criterion in the spec is demonstrated rather than
deferred. Every stage ships working code and tests; nothing is a placeholder. Three changes beyond
the twelve, `fang-verification`, `fang-mcu-parts` and `fang-emulation`, implement copperhead RFC 12
version 1.3, now adopted, and are archived beside them.

Use the `/opsx:*` skills (propose, apply, update, sync, archive, explore) for that workflow rather
than editing `openspec/` artifacts ad hoc. `openspec/config.yaml` carries project context that
those skills read.

## The site and the brand

[site/](site/) holds the landing page for `fang.copperhead.sh` and the brand assets. It is one
self-contained `index.html` with no build step, serving `site/` as the document root.
[site/BRAND.md](site/BRAND.md) fixes the mark's geometry, the palette, and the voice; the palette
is copperhead's own, taken from `docs.copperhead.sh`, with two values nudged for contrast and the
reason recorded. Fang is a sub-brand of copperhead, so a change to the identity belongs upstream
in copperhead's system first.
[site/social/](site/social/) holds images for posting, drawn in that identity by its `make.py`
from runs made as they are drawn (the firmware emulation renders run `sensor_node` and its broken
builds in Renode), so no number on an image is typed in by hand.

RFC 2119 keywords in the spec and RFCs are normative.
