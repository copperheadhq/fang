# The Physical Layer

## Why

The spec names six layers of representation and the kernel implements five. The
Physical/PCB IR — "board outline, stackup, layers, components, pads, vias,
traces, zones, regions, and dimensions" — is a key in the project root that
serializes as `{}` and nothing else. So a Fang program can state that a rail
carries two amps and the kernel cannot say how wide the copper has to be, cannot
check a board that claims to satisfy it, and cannot carry the rule to the tool
that routes it.

Every seam for this layer is already cut and none is filled. `identity.PREFIXES`
allocates `PCB` and `REGION`. `diff.py` classifies both kinds as
`PHYSICAL_CHANGED`. `ConstraintClass` has `ROUTING`, `PLACEMENT`, and
`MANUFACTURING`, and the spec says in as many words that they are classes in the
one registry and that an emitted rule file is a projection of it.
`ingest_external_results` defaults its actor to `kicad-drc`. A routing constraint
can be constructed today and evaluates correctly — and is permanently undecided,
because no entity in the graph carries a width for its `Ref` to resolve. The
undecided result is right, and it is the only answer this kernel can give about
copper.

## What Changes

- **Add the physical entities.** `Board`, `Stackup`, `Layer`, `Placement`,
  `Pad`, `Via`, `Trace`, `Zone`, and `Region`, each a frozen dataclass with
  identity, provenance, and a source location, each implementing `references()`
  and `as_dict()`, and each registered in `identity.PREFIXES` and
  `graph._COLLECTION_OF`. The `physical` root key stops being empty.
- **A physical entity names what it realizes.** A `Trace` names its net, a
  `Placement` names its component and the `Footprint` trait that component
  already carries, a `Pad` names its pin. The existing `Footprint` trait stays
  the *reference* to a library footprint; the physical layer adds the *placed
  instance*. Neither restates the other, and geometry never derives identity.
- **Let a routing constraint reach copper.** Extend `Snapshot.resolver` so a
  `Ref` to a physical attribute of a semantic entity — `Ref("NET-vbus",
  "physical.trace_width")` — resolves over the physical entities realizing it,
  as an interval across the segments rather than a single number. A net with no
  traces resolves unknown, never a pass.
- **Add the `routing` check class**, scoped to the entities its constraints
  target, so the gate requires it exactly when a transaction touches them.
  Placement and manufacturing constraints evaluate through the same path.
- **Extend the authoring surface.** A module declares its board and stackup, and
  `require()` records a routing or placement constraint rather than always an
  electrical one — today `elaborate.py` hard-codes `ConstraintClass.ELECTRICAL`
  and `constraint_kind="declared"` for every constraint a program writes.
  Minimum width, clearance, and matched length become expressible in a program.
- **Project rules outward.** Emit a KiCad design-rule file and net class
  assignments as `Projection`s carrying the identifier of the rule they project.
  These are generated artifacts, never a place engineering facts are recorded.
- **Read geometry back.** A `.kicad_pcb` reader ingesting board outline,
  stackup, placement, and routing into physical entities, reporting what it
  could not represent through the existing `MappingTable` and `ImportReport`.
  This is the first `.kicad_pcb` handling in the repository; the adapter reads
  and writes netlists only.
- **Close the return path.** A board is a `Realization` of kind `board` whose
  parent must be the committed snapshot, so `materialize()` already refuses it
  otherwise. External DRC results re-enter as `Evidence` through
  `ingest_external_results`, and a pin swap chosen during layout returns as an
  ordinary transaction through `implied_changes` — not as a side effect.
- **Add the routing diagnostic codes** in the `TOPO` area, allocated at the
  bottom of that block and never reused.

**Not in this change**, and deliberately: Fang does not place, does not route,
and does not write board geometry. It states the rules, hands them to the tool
that does the work, and reads the result back through the gate. There is no
autorouter, no `.kicad_pcb` writer, and no field-solver-derived width.

## Capabilities

### New Capabilities

None. The spec is the whole contract and is self-contained; the physical layer
is already described in it and belongs in it rather than beside it.

### Modified Capabilities

- `fang-kernel` — fills in the Physical/PCB IR the layers section already
  requires: what a physical entity is, how it maps to the layer above it, how a
  routing constraint resolves against it, that a board is a realization and not
  a peer source of truth, and what the layer refuses to do.

## Impact

- New modules `fang/physical.py` (the entity model and the resolver extension)
  and `fang/routing.py` (the check class and the rule projections), plus their
  tests.
- `fang/entities.py`, `fang/identity.py`, `fang/graph.py`, and `fang/diff.py`
  gain registrations for the new kinds. `fang/serialization.py` may gain ordered
  collections where a physical order is semantic — a stackup's layers are one.
- `fang/kicad.py` gains a `.kicad_pcb` reader; `fang/importing.py` gains its
  mapping entries.
- `fang/lang.py` and `fang/elaborate.py` gain the board, stackup, and
  constraint-class authoring surface.
- `fang/cli.py` gains a rules export; `fang/diagnostics.py` gains codes. Both
  files are also touched by the in-flight `fang-mcp` change — sequence the two
  rather than editing them in parallel.
- One new example folder demonstrating a width rule that fails, then passes,
  with its `out/` outputs committed; `MANIFEST.in` follows if it reads anything
  new.
- `openspec/ROADMAP.md` gains stage 12. This is the first stage after the
  eleven that closed the program-to-netlist loop.
- No new runtime dependency. Standard library only, as the core install is.
