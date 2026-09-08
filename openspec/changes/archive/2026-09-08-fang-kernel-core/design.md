# Design: Fang Kernel Core

## Context

One standard fixes the representation; the other fixes the kernel over it. Both are prose.
This design records the decisions that turn them into Python, and the ones that
are deliberately deferred.

## Goals

- One canonical model. The kernel graph holds EIR entities and nothing else.
- Determinism as a testable property, not an aspiration: byte-identical output
  from unchanged input, on any machine and in any process.
- Unknown and undecided are first-class, never collapsed into defaults or passes.
- Every mutation goes through one gate, whatever its origin.

## Non-Goals

Pin lowering, topology verification, CAD adapters, views, simulation, and the
public language surface are specified but not implemented here. They are later
phases of the delivery plan, and each gets its own change.

## Decisions

### D1: Decimal, never binary float

Magnitudes are `decimal.Decimal` in memory and decimal strings on the wire.
Binary floating point is never used for a physical quantity, because
reserialization must be byte-identical and `0.1 + 0.2` must not become
`0.30000000000000004` in an engineering record.

Interval arithmetic over ranges and tolerances uses `Decimal` with a fixed
context, so that comparison results do not depend on platform float behaviour.

### D2: Dimension as a 7-tuple of Fractions

A dimension is a tuple of seven `Fraction` exponents in the fixed SI order
(length, mass, time, current, temperature, amount, luminous intensity).
`Fraction` rather than `int` because the EIR permits a rational exponent. Equality
is tuple equality, which makes "comparable" cheap and exact.

Unit parsing normalizes the symbol and not the magnitude: `3.3 V` stays
`3.3 V`. A metric prefix is accepted on input and recorded as part of the
canonical symbol.

### D3: Identity is a pure function of project state

`derive_id(project_id, kind, path)` is UUIDv5 over the fixed root namespace.
Nothing in the derivation reads the clock, the host, the process, or iteration
order. Collision lengthening takes the revision's whole identifier set as input,
so it is a function of state rather than of insertion order — this is what makes
lengths reproducible.

Transliteration follows the canonical semantic path rules step for step, including the sibling
tie-break by Unicode code point, because a shortcut there silently changes
identity.

### D4: Three-valued logic as an enum, not None

`Truth` is `TRUE`, `FALSE`, `UNDECIDED`. `None` is never used for undecided,
matching the rule that null must not ambiguously mean "unknown" and "not
applicable". Comparison over intervals returns `UNDECIDED` on partial overlap.

Dimensional validity is checked when an expression is constructed, not when it
is evaluated, so an invalid expression cannot be stored.

### D5: Transactions produce a new snapshot, never mutate in place

The graph is held as immutable snapshots. A transaction is applied to a copy;
the copy is normalized, validated, and checked; only then does the graph's head
advance. Rejection discards the copy, which makes "a rejected proposal leaves
canonical state unchanged" true by construction rather than by discipline.

A transaction names its base snapshot. Applying one against a stale base raises
rather than merging optimistically.

### D6: Canonical JSON is written by one function

A single `canonical_dumps` is the only path to serialized output: sorted keys,
no whitespace variance, LF, NFC strings, decimal strings for magnitudes,
RFC3339 UTC timestamps. Ordered collections are declared per entity kind, so
that "sorted by id" applies only where order carries no meaning.

The record stream is the same function applied per entity, one object per line,
ordered by entity id.

### D7: NetworkX is an implementation detail

Graph algorithms build a NetworkX graph on demand from typed entities and throw
it away. Node dictionaries are never returned from a public API, per the kernel
§4.2, so the analysis library stays replaceable.

## Risks

- **Over-modelling before use.** The standard's risk register names this directly. Mitigation: the
  entity model here carries only what an acceptance test or a validation rule
  needs; further families are added when a query requires them.
- **Determinism regressions.** Mitigation: byte-identity is an acceptance test
  run on every change, not a review comment.
