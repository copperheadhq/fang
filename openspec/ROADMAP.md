# Fang delivery roadmap

**The twelve stages through the physical layer are delivered**, and every
acceptance criterion in the combined spec is demonstrated rather than deferred.
Stages 13 to 18 are planned.

The full code-defined electronics toolchain, chunked into stages. Each stage is
an OpenSpec change with its own proposal, delta spec, and tasks. Every delivered
stage ships working code and tests; nothing delivered is a placeholder.

The ordering is a product ordering, not the spec's evidence ordering: the first
five stages together are the vertical slice from a Fang program to a KiCad
netlist a person can open.

## The goal the stages serve

Hardware is described as code, compiled out to the major EDA tools for a person
to edit there, and read back into the same model — with that model carrying
enough detail to produce the schematic, the board, the manufacturing outputs,
the documentation, and simulation across RF, power, thermal, and signal
integrity.

Stages 1 to 11 built the model and one direction of one tool. Stage 12 gave it
a physical layer and carried a rule out to the tool that routes copper. Stages
13 to 18 are the rest of the round trip and the physics.

| # | Change | Delivers |
| --- | --- | --- |
| 1 | ✅ `fang-kernel-core` | Entity model, identity, units, values, constraints, transactions, commit gate, serialization, diff, topology |
| 2 | ✅ `fang-language` | The authoring surface: `Module`, `System`, parameters, traits, `require()`, the connect operator, deterministic elaboration, diagnostics |
| 3 | ✅ `fang-interfaces` | Interface catalogue, ports, buses, deterministic pin lowering, compatibility checks with undecided results |
| 4 | ✅ `fang-parts` | Part model: pins, packages, footprints, part traits, sourcing, and a standard library of generic parts |
| 5 | ✅ `fang-netlist` | Net inference from connectivity, designator assignment, netlist IR, KiCad netlist emission |
| 6 | ✅ `fang-cad` | KiCad s-expression reader and writer, project import, the canonical mapping table, lossy-operation reporting, one safe round trip |
| 7 | ✅ `fang-toolplan` | Tool plan emission, handles as symbolic conditions, the tool contract, the operation phase, realizations |
| 8 | ✅ `fang-views` | View compiler, the six required views, the layout boundary, SVG rendering, stable placement seeds |
| 9 | ✅ `fang-simulation` | Simulation models as traits, plans, SPICE lowering, the ngspice backend, result normalization |
| 10 | ✅ `fang-rationale` | Requirement, evidence, decision, and calculation authoring from Fang; the verification graph; impact propagation |
| 11 | ✅ `fang-cli` | The workspace (`.copperhead/`), the manifest, and `fang build`, `check`, `view`, `sim`, `export` |
| 12 | ✅ `fang-physical` | The Physical/PCB IR: board, stackup, layers, placement, pads, traces, vias, zones, regions; the routing check class; `.kicad_dru` rule and net class projections; a `.kicad_pcb` reader that reports what it could not represent |
| 13 | ⬜ `fang-schematic` | A schematic IR, the `.kicad_sch` writer and reader, sheet and hierarchy mapping, symbol selection as a recorded decision |
| 14 | ⬜ `fang-writeback` | Writers that edit a tool's own files in place: the foreign-node splice, preservation of what Fang does not model, and the round trip closed in both directions |
| 15 | ⬜ `fang-fabrication` | Manufacturing outputs as lowerings: Gerber, drill, IPC-2581, the BOM, and pick-and-place |
| 16 | ⬜ `fang-physics` | Equation-level analysis with no external backend: impedance from the stackup, IR drop over the copper, a thermal resistance network, current density against trace width |
| 17 | ⬜ `fang-solvers` | RF, signal integrity, power integrity, and thermal solvers as optional backends across the process boundary, each normalized like ngspice |
| 18 | ⬜ `fang-interchange` | The tools with no open format: IPC-2581 out, netlist and EDIF in, and a declared fidelity per adapter |

## The vertical slice

Stages 1 to 6 close the loop that makes the toolchain real:

```
Fang program -> elaboration -> kernel graph -> transaction gate
    -> snapshot -> netlist compiler -> KiCad netlist -> a board file
```

with import running the same path backwards into the same model.

## The second arc

Stages 12 to 18 extend that one-directional slice into a round trip a person
can work inside, and then give the model something to say about physics. Stage
12 is delivered: a program states its board and its rules about copper, those
rules leave as a `.kicad_dru` that names the constraint each one projects, and a
routed board comes back as physical entities that decide them. The ordering of
the rest is again a product ordering, and three dependencies fix most of it:

- **13 before 14.** A schematic is the layer a person actually edits, and today
  Fang emits a netlist, so a tool opening the project shows a ratsnest and no
  drawing. Writing a schematic is worth more than any other single stage here,
  and it reuses the s-expression layer stage 12 extends.
- **14 before 15.** Fang does not place and does not route, so complete copper
  only ever arrives by import. Manufacturing outputs are a lowering of a
  physical layer that is complete, which means the write-back path comes first.
- **16 before 17.** The equation level needs no external binary and stays
  deterministic, so it is where all four physics start answering. External
  solvers follow as optional extras, and the core install stays free of runtime
  dependencies.

Stage 18 depends on nothing above it and can move whenever a tool other than
KiCad is worth the adapter.

## Two decisions these stages need first

Both are spec decisions, not code, and both are cheap now and expensive to
retrofit.

- **Whether imported geometry is authoritative.** The physical layer is
  compiled and not a peer source of truth for a fact the layers above it
  already state. But a person's placement and routing is information no program
  derives, so it cannot be a compilation of anything. The resolution is that a
  physical entity is canonical and *not* derived — what Fang compiled and what a
  person drew are told apart by `authored()` and `imported()` provenance, the
  way every other entity's origin is told apart, rather than by the layer it
  sits in. Stage 12's `.kicad_pcb` reader was the first code this bound, and it
  reads a board into `imported()` identity with every external identifier
  recorded in the mapping table beside it.
- **Whether a writer preserves or regenerates.** Reporting loss is the right
  answer when reading a file into the model. It is the wrong answer when writing
  a person's file back, because regenerating it wholesale deletes every
  construct Fang does not model. So a writer splices: it keeps the parsed
  original's foreign nodes and replaces only what Fang owns. The original file
  is an input artifact cached in `.copperhead/`, not a representation of the
  facts, and that holds only so long as no fact is read from it that the graph
  does not also hold. Stage 14 rests on this.

## Invariants every stage holds

These come from the combined spec and are not renegotiated per stage:

- One canonical model. No stage introduces a second persisted representation.
- Deterministic output. Identical inputs give byte-identical snapshots.
- Unknown is representable; undecided is a third truth value.
- Every mutation is a transaction through the one gate.
- Every entity carries identity, provenance, and a source location.
