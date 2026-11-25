# Tasks: Canonical Form for Cross-Language Hashes

Implements copperhead RFC 3 version 1.6, Section 17.1, and RFC 11 version 1.4,
Section 6.13
([copperheadhq/copperhead-rfcs#15](https://github.com/copperheadhq/copperhead-rfcs/pull/15)).

## 1. Encoder

- [x] 1.1 `_entity_sort_key`: an entity by its identifier, any other item by
      its canonical serialization; drop the `code`, `name` and `symbol`
      shortcut.
- [x] 1.2 `_encode_number`: shortest round-trip digits, written positionally;
      refuse non-finite values with `NotCanonicalizable`.
- [x] 1.3 `ORDERED_COLLECTIONS`: add `outline`, `layers` and `preserved`.

## 2. Conformance

- [x] 2.1 Copy RFC 11's examples from #15 at `c7f6643` into
      `tests/fixtures/rfc11/`, with a README naming their source.
- [x] 2.2 `tests/test_canonical_form.py`:
      - every footprint key is the hash of its definition
      - every cited hash is the hash of an example
      - the named citations hold
      - plus a test for each rule
- [x] 2.3 Run the whole suite. The only failure is the pre-existing
      `noninverting_amp` output test, which fails the same way on main.

## 3. Close

- [x] 3.1 CHANGELOG entry under Fixed.
- [ ] 3.2 When #15 merges, recopy the fixtures if its examples changed, and
      archive this change.
- [ ] 3.3 Raise the open question with RFC 3: publish the ordered collections
      in the standard rather than only in this encoder.
