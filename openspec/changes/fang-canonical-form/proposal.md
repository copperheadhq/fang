# Canonical Form for Cross-Language Hashes

This change implements copperhead RFC 3, *The Copperhead Engineering
Intermediate Representation Standard*, version 1.6, Section 17.1, and the
ordered collections of RFC 11, *The Copperhead PCB Layout Generation Standard*,
version 1.4, Section 6.13. Both revisions are open as
[copperheadhq/copperhead-rfcs#15](https://github.com/copperheadhq/copperhead-rfcs/pull/15).
The change may proceed while that PR is open, and claims conformance only to
the version that merges.

## Why

The kernel's content hashes are how RFC 11's layout records cite one another.
copperhead's TypeScript encoder must compute the same ones from the same
records. Three behaviours of `fang/serialization.py` made the bytes depend on
the encoder rather than on the record:

- **Sorting by the wrong field.** An item without an identifier sorted by its
  `code`, `name` or `symbol` field before its serialization. Items sharing such
  a field kept their input order, so one collection could serialize, and hash,
  two ways. RFC 3 Section 17.1 sorts an entity by its identifier, and any other
  item by its canonical serialization.
- **`repr` for bare floats.** It writes `2.0` where the shortest decimal is `2`,
  and `1e-07` where JavaScript writes `1e-7`.
- **Ordered collections missing on main.** `outline`, `layers` and `preserved`
  were not in `ORDERED_COLLECTIONS`, so a ring's points, a stackup's layers, or
  an adapter's verbatim records would have been sorted.

## What Changes

- **Unordered collections.** An entity sorts by its identifier. Every other item,
  a string included, sorts by its canonical serialization, and no other field is
  a key.
- **Bare numbers.** A bare number is the shortest decimal that round-trips,
  written positionally: no exponent, no trailing zeros after the point, no point
  when the value is whole, and zero as `0`. A non-finite number raises
  `NotCanonicalizable`.
- **`ORDERED_COLLECTIONS`** is exactly the set the standards declare.
  RFC 3 Section 17.1 now declares order by key name, as the union of the keys
  each standard states:
  - RFC 3 states `provenance`, `rationale`, `alternatives_rejected`, `args` and
    `power_sequence`.
  - RFC 11 Section 6.13 states `outline`, `layers` and `preserved`, which are
    added here.
  - RFC 12 states `branches` and `calls`.
  - `sequence`, `steps` and `candidates` are dropped. No standard orders them,
    and `candidates` is unordered in RFC 11's records.
- **Conformance fixtures.** RFC 11's example records are copied unchanged from
  #15 at commit `c7f6643` into `tests/fixtures/rfc11/`.
  `tests/test_canonical_form.py` recomputes every hash those records cite to
  one another, and covers each rule above.

## Impact

- **Bytes and content hashes change** for three kinds of record: those holding
  an id-less collection whose items share a `code`, `name` or `symbol`, those
  holding a bare float, those holding an array under `outline`, `layers` or
  `preserved`, and those holding a conflicting value's candidates.
- **No schema version change.** The requirement already said "the shortest
  decimal" and "sorted ascending by entity identifier", so this is a
  conformance fix, and `SCHEMA_VERSION` does not move.
- **Suite results.** 1656 tests pass and 1 is skipped. The one failure,
  `test_examples.py::test_a_committed_output_still_matches_the_program[noninverting_amp]`
  (paper size A4 against A5), fails the same way on main without this change.
- **Merging with the physical-layer work.** That branch already orders
  `layers`, `outline` and `path`. Merging it conflicts on that set, which
  resolves to this change's set. `path` is not declared by any standard, so
  the physical branch drops it, unless RFC 11 is revised to declare it.

## Resolved Question

RFC 3 Section 17.1 required the schema to state which collections are
ordered, but no standard stated them; this encoder held the only list. RFC 3
now publishes its keys and the rule that order is declared by key, in
[copperhead-rfcs#15](https://github.com/copperheadhq/copperhead-rfcs/pull/15),
and RFC 12 states `branches` and `calls` in
[copperhead-rfcs#11](https://github.com/copperheadhq/copperhead-rfcs/pull/11).
`ORDERED_COLLECTIONS` is that union.
