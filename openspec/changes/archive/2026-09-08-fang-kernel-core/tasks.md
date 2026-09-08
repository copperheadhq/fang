# Tasks: Fang Kernel Core

## 1. Project scaffolding

- [x] 1.1 Create `pyproject.toml` for the `fang` package, Python 3.11+, with
      pytest configured and no runtime dependency beyond the standard library.
- [x] 1.2 Create the `fang/` package skeleton and `tests/` directory.

## 2. Units and quantities

- [x] 2.1 Implement `Dimension` as a 7-tuple of `Fraction` exponents in the
      fixed SI order, with multiply, divide, and integer/rational power.
- [x] 2.2 Implement unit parsing over SI symbols and ASCII plain names with the
      `*`, `/`, and `^` operators, accepting a metric prefix on input.
- [x] 2.3 Normalize the symbol and never the magnitude, so `3.3 V` stays `3.3 V`.
- [x] 2.4 Implement `Quantity` with kinds `scalar`, `range`, and `tolerance`,
      backed by `Decimal`, carrying optional conditions.
- [x] 2.5 Implement exact conversion between comparable units, recording
      rounding where the factor is not exact.
- [x] 2.6 Reject arithmetic across unequal dimensions with a `UNIT` diagnostic.

## 3. Values and unknowns

- [x] 3.1 Implement `Value` with status `explicit`, `inferred`, `assumed`, or
      `unknown`.
- [x] 3.2 Require source and confidence on `inferred`, rationale on `assumed`,
      and absence of a quantity on `unknown`.
- [x] 3.3 Represent a not-applicable value by absence, never by null.
- [x] 3.4 Implement conflicting-candidate values that retain every candidate and
      its source until a decision resolves them.

## 4. Identity

- [x] 4.1 Implement canonical semantic path parsing and formatting against the
      the canonical semantic path grammar, including bracketed indices and digit-leading names.
- [x] 4.2 Implement the transliteration algorithm step for step, including the
      sibling tie-break by Unicode code point and the `x` empty-result case.
- [x] 4.3 Implement `derive_id` as UUIDv5 over the fixed root namespace, the
      project namespace, and `<kind>:<path>`.
- [x] 4.4 Implement the twelve-hex-digit textual form and record the full UUID.
- [x] 4.5 Implement deterministic collision lengthening in four-digit steps as a
      function of the revision's identifier set.
- [x] 4.6 Reject a collision that survives the whole UUID as a shared path.
- [x] 4.7 Implement explicit keys that replace a name in the derivation path.
- [x] 4.8 Enforce identifier uniqueness across authored, derived, and imported
      origins, and keep external identifiers in an explicit mapping.

## 5. Entities and provenance

- [x] 5.1 Implement the base entity with identity, origin, display name, and
      source location.
- [x] 5.2 Implement the project root with every defined key present even when
      its collection is empty.
- [x] 5.3 Implement typed connections over the eight required kinds and make an
      untyped connection unrepresentable.
- [x] 5.4 Implement requirement, decision, evidence, component, net, rail,
      interface, port, bus, and domain entities to the depth the acceptance
      tests need.
- [x] 5.5 Implement append-only provenance records with the required fields, and
      require `confidence` when origin is `inferred`.
- [x] 5.6 Flag an entity traceable to neither a source location nor an import.

## 6. Constraints

- [x] 6.1 Implement the single constraint registry and reject any second store.
- [x] 6.2 Implement the constraint record with its required fields and its
      `class`, `enforcement`, and `verification.method` enumerations.
- [x] 6.3 Implement the typed expression tree over literal, ref, arithmetic,
      comparison, and logical node kinds.
- [x] 6.4 Compute a dimension for every node and reject a mismatch at
      construction time, not at evaluation.
- [x] 6.5 Implement `Truth` as `TRUE`, `FALSE`, `UNDECIDED` and evaluate
      comparison with interval semantics.
- [x] 6.6 Implement three-valued `and`, `or`, and `not`.
- [x] 6.7 Report a false applicability as not applicable rather than as passing.

## 7. Serialization

- [x] 7.1 Implement `canonical_dumps` as the single serialization path: sorted
      keys, LF, NFC strings, one trailing newline, no BOM.
- [x] 7.2 Emit magnitudes as decimal strings and bare numbers as the shortest
      round-tripping decimal.
- [x] 7.3 Emit timestamps as RFC3339 UTC with a trailing `Z`.
- [x] 7.4 Sort unordered collections by entity id and declare per entity kind
      which collections preserve meaningful order.
- [x] 7.5 Implement the record stream: one canonical object per line, ordered by
      entity id, with no run-varying framing.
- [x] 7.6 Prove the logical root is reconstructible from the stream without loss.
- [x] 7.7 Exclude wall-clock time, host, absolute path, process id, and
      address- or hash-derived ordering from output.

## 8. Validation and versioning

- [x] 8.1 Implement structural validation: identifier uniqueness, referential
      integrity, type and unit correctness, prohibited cycles, and contradictory
      mandatory constraints.
- [x] 8.2 Implement the requirement state transition table and reject any
      transition outside it.
- [x] 8.3 Require actor, reason, and provenance on every transition, and the
      cited evidence, waiver, or approval where the target state demands one.
- [x] 8.4 Implement `schema_version` on every artifact, reject an unimplemented
      major version, and preserve unknown fields.
- [x] 8.5 Record schema version, compiler version, and dependency lock identity
      with every snapshot.

## 9. Graph, transactions, and the commit gate

- [x] 9.1 Implement the immutable graph snapshot and its content hash.
- [x] 9.2 Implement the transaction as the only mutation unit, atomic and naming
      its base snapshot.
- [x] 9.3 Implement structured operations including `connect` and
      `set_parameter`, each carrying reason and requirement references.
- [x] 9.4 Reject or rebase a transaction proposed against a stale snapshot.
- [x] 9.5 Implement the proposal sandbox on a candidate branch, discarded on
      rejection but still producing diagnostics and a diff.
- [x] 9.6 Implement the six commit-gate conditions and the default required
      check set of structural validation plus every intersecting check class.
- [x] 9.7 Ensure no downstream artifact is materialized before commit.

## 10. Semantic diff

- [x] 10.1 Implement diff classification across all fifteen required classes.
- [x] 10.2 Separate presentation change from electrical change.
- [x] 10.3 Report a preserved-identity rename as a rename, not an add and a
      remove.
- [x] 10.4 Carry impact naming invalidated calculations, requirements, and
      verifications.

## 11. Diagnostics

- [x] 11.1 Implement `<AREA>-<NNNN>` codes over ELAB, IFACE, TOPO, UNIT, TXN,
      SIM, and IMPORT with severity, entities, source location, and message.
- [x] 11.2 Implement the code registry, never reusing or renumbering a code and
      keeping a retired code allocated.

## 12. Graph analysis and rationale queries

- [x] 12.1 Build NetworkX graphs on demand from typed entities and never expose
      node dictionaries publicly.
- [x] 12.2 Implement the six rationale queries from graph state alone with no
      model call.

## 13. Acceptance tests

- [x] 13.1 Implement one test per representation acceptance test AT-R1 to AT-R13
      that the kernel core can satisfy, and mark the rest pending their phase.
      (AT-R1, AT-R3, AT-R7 skip, naming Phase 2 as their owner.)
- [x] 13.2 Implement one test per kernel acceptance test AT-K1 to AT-K10 on the
      same basis. (AT-K1, AT-K4, AT-K6, AT-K10 skip, naming Phases 2, 3, and 6.)
- [x] 13.3 Add a cross-process byte-identity test proving reserialization is
      stable outside a single interpreter run.
- [x] 13.4 Add a test proving a rejected proposal leaves canonical state
      unchanged and still emits diagnostics and a diff.
