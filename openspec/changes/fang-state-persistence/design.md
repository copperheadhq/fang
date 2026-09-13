## Context

**Traits are held beside the snapshot, not in it.** A `Part` appends traits to
itself (`Footprint` from its package in `lang.py`, `Sourcing` and
`DatasheetEvidence` from `select()`). `_build_entities` in `elaborate.py` copies
them into a `TraitRegistry` returned as `Elaboration.traits`. Five consumers take
that registry as a separate `traits=` argument: `compile_netlist`,
`lower_to_spice`, the runtime's `RunContext`, the CLI's build, netlist, export,
and sim commands, and the MCP session, which re-elaborates the program to get
it. `Workspace.write_snapshot` writes `snapshot.records()`, which carries no
traits.

**Nothing reads state back.** The only `from_dict` in the package is
`Manifest.from_dict`. `Workspace.read_snapshot` returns a snapshot with no
entities unless the caller passes live ones, and `fang/mcp.py` refuses
`add_entity` because "the kernel has no rehydration registry".

**The serialized form is not a mechanical mirror of the fields**, which rules out
a generic decoder:

- `Constraint` writes `constraint_class` as `class`, nests the verification
  status under `verification`, and writes its expression as a tree dispatched on
  `node`.
- `TopologyConstraint` shares the kind `constraint` and is told apart only by
  `class: "topology"`.
- `Requirement` nests `validation_method` under `validation.method`.
- `Quantity` writes `minimum` and `maximum` as `min` and `max`, and its unit as a
  symbol.
- `Dimension` is a list of fraction strings.
- `Identity` writes its `uuid` and `path` as strings, with `path` a
  `fang.identity.Path`.
- Enums become their values, and many tuples are sorted on write.
- `ProvenanceRecord.created_at` is a `datetime` that serializes as RFC 3339 with a
  trailing `Z`.
- A block is the base `Entity` with kind `block`, not a subclass.

**The snapshot hash covers the whole logical root:** the schema version, project,
revision, compiler version, lock, and every collection. It is computed from
`Snapshot.as_dict()`. `extracted_upstream` is hashed when non-empty but is not
recorded in the manifest.

**Open PR #4 (`fang-physical`) touches the same ground.** It moves
`SCHEMA_VERSION` to 1.2 and groups new physical entity kinds under `physical` in
`Snapshot.as_dict`.

## Goals / Non-Goals

**Goals:**

- Traits persist inside their entity's record, and the snapshot hash covers them.
- A workspace reloads into typed entities and traits with no program run, and
  the rebuilt snapshot reproduces the manifest's hash byte for byte.
- Every kind and protocol the kernel serializes has a decoder, in a registry later
  changes extend.
- Unknown records are preserved and reported; malformed records refuse the load.
- Existing callers keep working, and schema 1.1 workspaces still load.

**Non-Goals:**

- An agent adding an entity over MCP. Decoding makes it constructible, but how an
  agent's entity acquires identity and provenance is a requirement of its own.
- Building or checking from a workspace in the CLI instead of from the program.
- Programs elaborating against a base snapshot (the third change after this).
- The record fields schematic import adds under RFC 3 version 1.4.
- Decoders for PR #4's physical entity kinds, which that PR registers when it
  rebases.

## Decisions

### D1. Traits live on the entity

`Entity` gains `traits: Mapping[str, Trait]`, keyed by protocol. `_base_dict`
writes it under `traits` only when it is non-empty, so a record without traits is
byte-for-byte what it was. `_build_entities` attaches a module's traits to the
entity it builds. `TraitRegistry` gains a constructor from a snapshot's entities,
`Elaboration.traits` becomes that view, and each consumer that receives
`traits=None` derives the registry from the snapshot it was given. An explicit
`traits=` argument still works.

RFC 3 version 1.4 puts traits in the entity record. One structure then holds the
fact in memory and on disk, and the snapshot hash covers a footprint change as it
covers a parameter change.

Alternative considered: keep the registry beside the snapshot and splice trait
dicts into records at write time. Rejected: records would stop being
`entity.as_dict()`, the hash would not cover traits unless it were spliced too,
and two structures would hold one fact.

Trait classes are mutable dataclasses and entities are frozen. A trait is
therefore treated as a value: it is copied when attached, and changing one means
a new entity through a transaction, as changing a parameter already does.

### D2. Each decoder inverts its own `as_dict`, beside it

`from_dict` classmethods are added beside `as_dict` on:

- `Identity`, `SourceLocation`, `Actor`, `Input`, `ProvenanceRecord`, and
  `Provenance`;
- `Tolerance`, `Quantity` (its unit through `Unit.parse`), and `Dimension`;
- `Value`, `Candidate`, `ConflictingValue`, and `Signal`;
- the expression nodes, dispatched on `node`;
- every trait class, and every entity class.

The serialized form renames, nests, sorts, and flattens (see Context), so a
generic reflective decoder would have to guess, and a guess would corrupt state
rather than fail. Keeping each decoder beside its encoder keeps the pair in one
review.

Alternative considered: a reflective dataclass decoder with per-field overrides.
Rejected: the overrides would be most of the code, and they would sit away from
the `as_dict` they must mirror.

### D3. One registry, keyed by kind and by protocol

A new module, `fang/rehydrate.py`, holds `register_entity(kind, decoder)`,
`register_trait(protocol, decoder)`, the functions that decode a record or a
trait through them, and the load report. The core kinds and protocols register
when the module is imported. A kind with more than one class dispatches inside
its decoder: a `constraint` record with `class: "topology"` decodes as
`TopologyConstraint`, and any other as `Constraint`. Later changes register their
own kinds, starting with PR #4's physical entities. This is the registry the MCP
refusal and `Workspace.read_snapshot` both name as missing.

### D4. Unknown is preserved; malformed refuses

Three cases load as opaque values holding the record exactly as read:

- a record whose kind has no decoder loads as an `OpaqueEntity`, carrying the
  record's id and no references;
- a trait whose protocol has no decoder loads as an `OpaqueTrait`, carrying its
  protocol and payload;
- a known record with a key its decoder does not model loads as an
  `OpaqueEntity`.

Each serializes back byte-identically and is named in the load report.

Why the whole record goes opaque rather than just the unknown key: dropping the
key would change the bytes and the hash, which is silent loss. Decoding the rest
while keeping the key would need a side channel on every entity class. The
consequence is that a record a newer producer extended is opaque to an older
reader: typed operations do not see it, and the report says so. A check that
needed its data resolves to unknown and reports undecided, never passing.

A malformed record is a different case from an unknown one. A required field
missing, a value of the wrong type, or an enum value outside its set refuses the
load with an `ELAB` diagnostic naming the record's id and the field, and no
partial snapshot is returned.

### D5. `Workspace.read_snapshot()` is typed and checks itself

`read_snapshot()`:

1. reads the manifest and checks its schema major version with the existing
   `check_schema_version`;
2. decodes every record through the registry;
3. builds the snapshot with the manifest's project, revision, schema version,
   compiler version, lock, and extracted-upstream list, not the running code's;
4. refuses the load if the rebuilt hash differs from `manifest.snapshot`,
   naming both hashes.

It returns the snapshot together with the load report. The `entities=` argument,
which existed only because decoding did not, is removed once its callers use the
typed read.

Building with the manifest's versions is what lets a workspace written by an
earlier compiler reproduce its own hash. A mismatch means tampering, a decoder
bug, or a file from an implementation that serializes differently, and each of
those should stop the load.

The manifest gains `extracted_upstream`, written only when it is non-empty, so
step 3 can reproduce a hash that covers it.

### D6. RFC 3339 is parsed beside where it is written

`fang/serialization.py` gains the inverse of `rfc3339()`, accepting exactly the
trailing-`Z` form it writes. The parser does not lean on
`datetime.fromisoformat`, whose handling of `Z` differs across Python versions.

### D7. The schema minor version moves

Records gain an optional `traits` key, which "Schema Versioning and
Compatibility" classes as additive, so the minor version moves. A schema 1.1
stream loads with no traits. PR #4 also claims 1.2; see Open Questions.

### D8. Hashes move where traits exist

Every example part carries a `Footprint` trait, so every example's snapshot hash
changes. `tests/test_examples.py` already normalizes hashes. Committed outputs are
regenerated only if a line other than a hash moves.

### D9. A dimension vector keeps its order

This was found while writing the `Ref` decoder. Canonical serialization sorts
every list whose key is not in `ORDERED_COLLECTIONS`, and `dimension` was not in
it. That key holds the seven base-dimension exponents that a `Ref` and a `Unit`
write. The persisted vector was therefore sorted. It could not be decoded, and
two dimensions whose exponents were permutations of each other serialized
identically.

"Canonical Serialization" already requires a collection whose order carries
meaning to keep that order. The change is therefore a fix, not a new
requirement: `dimension` joins `ORDERED_COLLECTIONS`. A snapshot holding an
expression reference changes hash, which D8 already accepts.

A workspace the schema 1.1 writer wrote still holds sorted vectors. Decoding one
as if it were ordered does one of two things. It refuses a valid comparison, or,
worse, it loads a comparison of two references with a wrong dimension and a
matching hash. So under a manifest older than schema 1.2, a record holding an
expression reference loads as an `OpaqueEntity`, and the load report says the
order was never written. Rebuilding the design rewrites the record.
`tests/fixtures/schema-1.1` is a workspace that commit `62a6de3` actually wrote.

### D10. A consumer refuses state it cannot read

A `TraitRegistry` built from entities attaches only typed traits. It records an
`OpaqueTrait` as untyped rather than hand out an object that lacks the
protocol's fields. It also copies each trait, so a consumer that changes what it
is handed cannot change a frozen snapshot.

A netlist refuses to compile when a component, pin, net, rail, or connection
loaded untyped, or when a footprint or sourcing trait did, with `ELAB-0015`. A
simulation plan refuses a model that loaded untyped. Leaving the thing out would
produce a projection that claims to be complete while missing a part. That is
the silent pass D4 rules out.

## Risks / Trade-offs

- [A decoder drifts from its `as_dict`] → A round-trip test runs over every
  entity of every example and fixture. A completeness test fails when any entity
  class the package defines, or any shipped trait class, has no registered
  decoder. Kinds that `identity.PREFIXES` and `graph._COLLECTION_OF` name but no
  class defines yet, such as `circuit` and `outcome`, load opaque.
- [Opaque records hide content from typed operations] → They are named in the
  load report, and a check that needed their data reports undecided rather than
  passing.
- [Mutable traits inside frozen entities] → Traits are copied on attach; a test
  asserts a reloaded entity's traits are distinct objects from the program's.
- [PR #4 conflicts] → Whichever merges second rebases. PR #4's physical kinds
  register decoders in `fang/rehydrate.py`, and its `Snapshot.as_dict` grouping
  needs no decoder change, because records stay flat.
- [Every example hash changes] → Accepted; outputs normalize hashes (D8).

## Migration Plan

There is no data migration. A workspace written under schema 1.1 loads with no
traits, and the next `fang build` rewrites it with traits and the new schema
version. After a rollback, the earlier code still reads the new files as raw
records, since it never decoded them, and the major version is unchanged.

## Open Questions

- **The schema version number.** PR #4 moves `SCHEMA_VERSION` to 1.2 for its
  physical entities, and RFC 3 version 1.4 (copperhead-rfcs PR #2) assigns schema
  1.2 to the record fields of RFC 12 version 1.2. The proposal is that whichever
  change merges second takes the next free minor, and RFC 3's numbering is
  settled in review of that PR.
- **An agent's entity over MCP.** Should it become constructible in a change of
  its own, now that decoding exists? That needs a requirement for how an agent's
  entity is given identity and provenance.
