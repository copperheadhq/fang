# fang-kernel Specification

## MODIFIED Requirements

### Requirement: Deterministic Canonical Serialization

Machine-generated kernel state SHALL serialize canonically: reserializing an
unchanged state SHALL produce byte-identical output, on any machine and in any
process. JSON is the canonical interchange encoding.

Canonical serialization is UTF-8 with no byte order mark, LF line endings, and
one trailing newline; strings in Unicode normalization form C with no trailing
whitespace; mapping keys sorted ascending by Unicode code point; unordered
collections sorted ascending by entity identifier, and a collection whose items
carry no identifier sorted by each item's canonical serialization, with no
other field used as a sort key; physical quantities as decimal strings and
never as binary floating point; a bare number as the shortest decimal that
round-trips to the same value, written positionally with no exponent, no
trailing zeros after the decimal point, no point when the value is whole, and
zero as `0`; and timestamps as RFC3339 in UTC with a trailing `Z`. A value with
no canonical serialization, such as a non-finite number, SHALL be refused.

A collection whose order carries meaning, such as a power-up sequence, a
rationale list, or a provenance list, SHALL preserve its order, and the schema
SHALL state which collections those are. The layout records' ordered
collections are those of copperhead RFC 11 Section 6.13: `outline`, `layers`,
and `preserved`.

The content hash of a record SHALL equal the one any conforming encoder
computes from the same record, in any language.

#### Scenario: No environment-derived value is emitted

- **WHEN** state is serialized
- **THEN** the output contains no wall-clock time, host name, absolute path,
  process identifier, or ordering derived from memory address or hash iteration
  order
- **AND** the exception is a value that is itself recorded engineering data,
  such as the `created_at` field of a provenance record

#### Scenario: The record stream has a fixed canonical form

- **WHEN** state is persisted as a stream of typed entity records
- **THEN** each record is one canonically serialized object on one line
- **AND** records are ordered ascending by entity identifier
- **AND** the stream carries no framing that varies between runs

#### Scenario: Persistence form is not a schema change

- **WHEN** persistence moves between the single logical document and the record
  stream
- **THEN** the logical root is reconstructible from either without loss
- **AND** the choice alters no identity, no ordering, and no content

#### Scenario: Items sharing a field still have one order

- **WHEN** a collection holds items without identifiers that share a `code`,
  `name`, or `symbol` field
- **THEN** they sort by their whole canonical serialization
- **AND** the collection serializes to the same bytes whatever order it was
  built in

#### Scenario: A bare number has one written form

- **WHEN** a bare number such as 2.0, 0.1, or 1e-07 is serialized
- **THEN** it is written `2`, `0.1`, and `0.0000001`
- **AND** an infinite or not-a-number value is refused

#### Scenario: The RFC's example records hash as the RFC computed them

- **WHEN** the example records RFC 11 Section 6.13 publishes are serialized
- **THEN** each footprint key is the content hash of its definition
- **AND** every hash an example cites is the content hash of the example it
  names
