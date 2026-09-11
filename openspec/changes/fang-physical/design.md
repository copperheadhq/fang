# The Physical Layer — Design

## Context

See [proposal.md](proposal.md) for motivation. The constraints that actually
shape the approach are in the code, and they are tighter than the proposal
implies:

- `Snapshot.resolver()` ([graph.py:130](../../../fang/graph.py#L130)) resolves a
  `Ref` by looking up `entity.parameters[attr]` and nothing else. A routing rule
  about copper has no way to reach copper today.
- `Snapshot.as_dict()` builds the root from `ROOT_COLLECTIONS` (lists) and
  `ROOT_MAPPINGS` (dicts). `physical` is a **mapping**, so physical entities
  cannot simply be appended to a collection the way every other kind is.
- `CONSTRAINT_CHECK` evaluates *every* `Constraint` in the graph, whatever its
  class. The gate runs only the checks `policy.required` selects out of
  `self._checks`; the unconditional part of the gate is `validate()`, not this
  check class. So the check set is genuinely narrowable.
- `elaborate._build_constraints` hard-codes `ConstraintClass.ELECTRICAL` and
  `constraint_kind="declared"`. A program cannot currently produce a constraint
  in any other class.
- `traits.Footprint` already exists and means *which library footprint* — not
  *where the part sits*. The names will collide unless the model separates them.
- `fang/sexpr.py` already tokenizes and parses s-expressions; `fang/kicad.py`
  uses it for netlists only.

## Goals / Non-Goals

**Goals**

- One canonical model. Physical facts live in the same graph, behind the same
  gate, under the same identity and provenance rules.
- A routing constraint that is decidable when the board exists and honestly
  undecided when it does not.
- A rule projection a layout tool can consume, that carries its origin and
  cannot become a source of truth.

**Non-Goals**

- Any geometry Fang computes itself. No placer, no router, no field solver, no
  width-from-current table. A width rule states a threshold a person or a
  standard chose; the kernel checks it, it does not derive it.
- Writing `.kicad_pcb`. Geometry moves in one direction across this boundary.
- Modelling a full DRC. The rules that matter here are the ones expressible as
  typed constraint expressions over physical attributes.

## Decisions

### D1. Physical attributes resolve through a reserved `physical.` namespace

A routing constraint targets the semantic entity it is about — `NET-vbus`, not
the trace segments a router happened to produce, whose identities do not exist
when the rule is written. `Snapshot.resolver()` gains a second lookup: when the
attribute name begins with `physical.`, it resolves over the physical entities
realizing that entity instead of over its parameters.

```
Ref("NET-vbus", "physical.trace_width")   -> interval over the traces naming NET-vbus
Ref("CMP-u1",   "physical.position")      -> the placement naming CMP-u1
```

*Why the namespace.* Bare `trace_width` would collide with an authored parameter
of the same name, and the collision would resolve differently depending on
whether the board had been imported yet — a determinism bug that only appears
late. The prefix makes the two unambiguous by construction and makes the
constraint record self-describing.

*Alternative rejected:* a second resolver passed alongside the first. Two
resolvers means one `Ref` has two possible answers, and the evaluator would have
to know which to ask. One resolver, one answer.

### D2. An aggregate resolves to an interval, statused `inferred`

A net is realized by many trace segments. `Ref` resolves to
`Quantity.range(min, max)` across them, so `>= 0.5 mm` fails when the narrowest
segment fails and a maximum-width or clearance rule stays expressible from the
same reference.

*Corrected during implementation.* This decision first said the existing
`Interval` arithmetic already handled that. It did not. A closed interval meant
two different things and the evaluator could not tell them apart: an interval of
*uncertainty*, where one value lies somewhere inside and a straddling comparison
is honestly undecided, and the span of a *population*, where every value in it is
copper on a board. Under the first reading `[0.3, 1.0] >= 0.5 mm` is undecided,
which is why the narrowest-segment rule evaluated `UNKNOWN` rather than failing.

So `Interval` carries a `population` flag, `Ref` sets it for a `PHYSICAL_PREFIX`
attribute, and `Comparison` drops the undecided middle when a population meets a
fixed bound: min settles every `>=` and max every `<=`. Equality is deliberately
left out — the span reports the extremes and never says which values between
them are present, so `==` and `!=` over a population stay undecided. Arithmetic
propagates the flag, because doubling every segment width leaves a set of real
widths rather than a range of uncertainty.

The flag is the whole of the change to the evaluator, and it does not touch the
uncertainty semantics every electrical constraint relies on: an interval is a
population only when a physical reference produced it.

The value is `ValueStatus.INFERRED`, with the board realization as its `source`.
`Value.__post_init__` requires an inferred value to carry a source and a
confidence, which is the right pressure here: the check result cites the board
it was computed from, so a re-route invalidates it visibly.

*Alternatives rejected:* resolving to the minimum alone (a maximum rule becomes
inexpressible); resolving `EXPLICIT` (an aggregate computed from geometry is not
a stated fact, and the distinction is the whole point of `ValueStatus`).

### D3. The `physical` root key becomes a keyed mapping, and `SCHEMA_VERSION` goes to 1.2

`physical` stays a mapping and gains one key per physical kind:

```yaml
physical:
  boards: []
  stackups: []
  layers: []
  placements: []
  pads: []
  vias: []
  traces: []
  zones: []
  regions: []
```

`Snapshot.as_dict` gets a `_PHYSICAL_OF` map beside `_COLLECTION_OF`; a kind in
neither still falls through to `extensions`, unchanged. Every key is present
even when empty, exactly as the root rule requires, so a project with no board
serializes `physical` with nine empty lists rather than `{}` — **this changes the
bytes of every existing snapshot**, which is what the version bump is for.

`SCHEMA_VERSION` moves `1.1` → `1.2`: additive, minor, per the versioning
requirement. Committed example outputs under `examples/*/out/` are regenerated in
the same change.

*Alternative rejected:* making `physical` a flat list like the other
collections. It would flatten nine kinds into one array and contradict the root
shape the spec fixes.

### D4. `Placement` is a new entity; the `Footprint` trait keeps its meaning

`traits.Footprint` stays what it is: the library and name of the footprint a
component uses — a sourcing-adjacent fact about the part. The physical layer adds
`Placement`, which names the component, the layer, the position, and the
rotation. The two never restate each other, which is the governing invariant
applied to a place it would be easy to violate.

`Placement.position` and `Pad`/`Trace` geometry are already in
`diff.PRESENTATION_FIELDS` (`position`, `geometry`), so a pure move classifies as
presentation rather than electrical without any change to `diff.py` beyond
registering the new kinds in `_KIND_TO_CHANGED`.

### D5. `CONSTRAINT_CHECK` narrows to the electrical classes; `ROUTING_CHECK` takes the rest

`CONSTRAINT_CHECK` currently evaluates every constraint regardless of class. It
narrows to `ELECTRICAL`, `PHYSICS`, `TOPOLOGY`, `SOURCING`, and `TESTABILITY`;
the new `ROUTING_CHECK` in `fang/routing.py` covers `ROUTING`, `PLACEMENT`, and
`MANUFACTURING`, scoped to the entities those constraints target, and joins
`DEFAULT_CHECKS`.

Both call `Constraint.evaluate`. There is one evaluator; a check class is a
selection and a scope, which is what `checks.py` already says a check class is.

*Why this is safe:* no existing design can hold a non-electrical constraint,
because `elaborate` can only emit `ELECTRICAL`. The narrowing is a no-op for
every program in the repository, and a test pins that.

*One migration seam:* `KernelGraph.__init__` defaults to `checks=(CONSTRAINT_CHECK,)`.
A caller who takes that default and then adds routing constraints would silently
not have them checked. The default becomes `DEFAULT_CHECKS`, which moves
`DEFAULT_CHECKS` out of `checks.py` into `graph.py` or inverts that import —
resolved during apply; `checks.py` currently imports from `graph.py`, so the
tuple moves down and `checks.py` re-exports it.

### D6. `require()` learns a class; the program declares the board

`require(expr, class="routing", kind="min_trace_width")` — keyword-only, both
defaulting to today's `electrical` / `declared`, so every existing program
elaborates to byte-identical entities. `ElaborationContext.constraints` carries
the class through to `_build_constraints`.

A module declares its board in a `board()` method beside `constraints()`, called
once during elaboration under the same rules: recorded, never evaluated, and
carrying the source location of the line that produced it. Layer copper weights
are `Quantity` like every other magnitude — `1 * oz` — never a bare number, which
means `oz` joins the unit table as a mass unit.

*Alternative rejected:* a separate `require_routing()`. Two spellings of one verb
for a difference the record already carries in a field.

### D7. Rules project to `.kicad_dru`; codes go in the `TOPO` area

`ConstraintRegistry.project()` already produces a `Projection` carrying the
projected identifier plus class-specific fields. `fang/routing.py` renders a
sorted-by-identifier `.kicad_dru` and a net class assignment from those
projections. Sorted by identifier, so emission is byte-identical for a snapshot.

Diagnostics go in the existing `TOPO` area rather than a new `PHYS` one. `TOPO`
already means physical intent that net equivalence cannot express, which is
precisely what a routing rule is, and `AREAS` is normative in the spec — adding
one is a change to the contract that this change does not need to make.

### D8. The `.kicad_pcb` reader is a read-only subset over the existing parser

`fang/sexpr.py` parses it already. The reader recognizes board outline, stackup,
`footprint` placement, `segment`, `via`, and `zone`, and routes everything else
through `importing.Unrepresented`, which already emits `IMPORT-0001` with a
location. External identifiers go into the existing `MappingTable`; none becomes
canonical identity.

The reader is deliberately narrow. A construct it does not know is reported, not
approximated — the failure mode this avoids is a keepout silently becoming a
zone.

## Risks / Trade-offs

- **The schema bump rewrites every committed example output.** → Regenerate with
  `python examples/regenerate.py` in the same change; `tests/test_examples.py`
  fails loudly if any output drifts, so this cannot be half-done.
- **Narrowing `CONSTRAINT_CHECK` is a behavior change to the gate.** → It is a
  no-op today (D5) and pinned by a test asserting an electrical constraint is
  still evaluated by the same class under the same name.
- **`physical.` attribute names become contract.** Once a rule references
  `physical.trace_width`, renaming it breaks stored constraints. → Fix the
  attribute vocabulary in the spec delta's terms and keep it small: width,
  length, clearance, layer, position, copper weight. Unknown attribute names
  resolve unknown rather than raising, consistent with every other `Ref`.
- **An interval hides which segment failed.** A failing width rule says the net
  fails, not which segment. → The `CheckResult` message names the offending
  physical entity; the interval is what the rule evaluates over, not what the
  finding reports.
- **`fang/cli.py` and `fang/diagnostics.py` are also touched by the in-flight
  `fang-mcp` change** (3/32 tasks, `MCP` area and `cmd_mcp` already landed). →
  Sequence, do not parallelize. Diagnostic codes are allocated, never reused, so
  a concurrent `_allocate` in two branches produces a silent collision on
  rebase.
- **A read-only board boundary means Fang cannot hand a router a starting
  board.** That is the trade for not owning geometry, and it is the whole point
  of the boundary. Revisit only with a stage that has a reason to write.

## Migration Plan

1. Entities, identity, and root shape first, with `SCHEMA_VERSION` at 1.2 and
   the example outputs regenerated. Nothing references physical facts yet, so
   the suite stays green on structure alone.
2. The resolver and `ROUTING_CHECK` next, including the narrowing of
   `CONSTRAINT_CHECK`. This is the step that can regress the gate; it lands with
   its tests and nothing else.
3. The language surface, which is purely additive because both new arguments
   default to today's behavior.
4. The projections, then the reader. Either can land without the other.

Rollback is per step: each is additive except step 2, which reverts by widening
`CONSTRAINT_CHECK` back to every class.

## Open Questions

- Which copper-weight unit spelling to standardize on — `oz` as a mass, or
  thickness in `um`. Both are expressible; the choice affects only what the
  stackup example reads like, and can be settled when the unit table is touched
  in step 1.
