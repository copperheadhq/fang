## 1. Value decoders

- [x] 1.1 Add `from_dict` beside `as_dict` for `Identity` (its `uuid` and its
      `fang.identity.Path` from strings), `SourceLocation`, `Actor`, `Input`,
      `ProvenanceRecord`, and `Provenance`, with the inverse of `rfc3339()` in
      `fang/serialization.py` (design D2, D6)
- [x] 1.2 Add `from_dict` for `Tolerance`, `Quantity` (its unit through
      `Unit.parse`, and `min` and `max` back to `minimum` and `maximum`),
      `Dimension`, `Value`, `Candidate`, `ConflictingValue`, and `Signal`
- [x] 1.3 Add decoders for the expression nodes `Literal`, `Ref`, `Arithmetic`
      (with its exponent), `Comparison`, and `Logical`, dispatched on `node`
- [x] 1.4 Test that each of these types reserializes to the same canonical bytes
      after decoding, with every enum value and every optional field both set and
      unset

## 2. Traits on entities

- [x] 2.1 Add `traits: Mapping[str, Trait]` to `Entity`, written by `_base_dict`
      under `traits` only when it is non-empty (D1)
- [x] 2.2 Attach a copy of each module's traits to the entity `_build_entities`
      builds
- [x] 2.3 Give `TraitRegistry` a constructor from a snapshot's entities, make
      `Elaboration.traits` that view, and have `compile_netlist`,
      `lower_to_spice`, the runtime, the CLI, and the MCP session derive traits
      from the snapshot when none are passed. The runtime and the CLI already
      pass `Elaboration.traits`, which is now the view, so they are unchanged;
      `lower_to_spice` passes its argument on to `compile_netlist`
- [x] 2.4 Add `from_dict` for `Footprint`, `Sourcing`, `DatasheetEvidence`,
      `Simulatable` (with its provenance), and `Renderable`
- [x] 2.5 Classify a change confined to an entity's traits as
      `model_or_trait_changed` in `fang/diff.py`, with a test

## 3. The rehydration registry

- [x] 3.1 Create `fang/rehydrate.py` with `register_entity`, `register_trait`,
      record and trait decoding, and the load report, registering every core kind
      and protocol at import (D3)
- [x] 3.2 Add `from_dict` for every entity class: the base `Entity` for `block`,
      `Requirement`, `Connection`, `Component`, `Net`, `Rail`, `Interface`,
      `Port`, `Pin`, `Bus`, `Domain`, `Decision`, `Evidence`, `Calculation`,
      `Verification`, `Assumption`, `Model`, and `Constraint`, whose decoder
      returns a `TopologyConstraint` for `class: "topology"`
- [x] 3.3 Load a record of an unregistered kind, a trait of an unregistered
      protocol, and a known record with an unmodelled key as `OpaqueEntity` or
      `OpaqueTrait`, byte-identical on reserialization and named in the load
      report (D4). A trait with an unmodelled key also loads as an `OpaqueTrait`
      on its still-typed entity, and a record whose decoded entity would not
      reserialize to the same bytes is kept as an `OpaqueEntity`
- [x] 3.4 Refuse a malformed record with a new `ELAB` diagnostic, allocated
      through `_allocate`, that names the record's id and the field, returning no
      partial snapshot (`ELAB-0013`; a manifest mismatch is `ELAB-0014`)
- [x] 3.5 Add a completeness test: every entity class the package defines (each
      `Entity` subclass in `fang`, and the base `Entity` for `block`), and every
      shipped trait class, has a registered decoder. `identity.PREFIXES` and
      `graph._COLLECTION_OF` also name kinds no class defines yet, such as
      `circuit` and `outcome`; a record of one loads as an `OpaqueEntity`

## 4. Workspace reload

- [x] 4.1 Record `extracted_upstream` in the manifest when it is non-empty (D5)
- [x] 4.2 Make `Workspace.read_snapshot()` check the schema major version, decode
      every record, build the snapshot from the manifest's versions, refuse a hash
      mismatch naming both hashes, and return the snapshot with its load report
- [x] 4.3 Remove the `entities=` argument from `read_snapshot` and update its
      callers. It had no callers
- [x] 4.4 Test the scenarios: the reloaded hash equals the manifest's and the
      stream is byte-identical; traits enumerate from a reloaded snapshot with no
      program run; a stream that does not match its manifest is refused; and a
      schema 1.1 workspace loads with no traits

## 5. Schema, outputs, and verification

- [x] 5.1 Move `SCHEMA_VERSION` to the next minor version (D7) and update any test
      that pins it
- [x] 5.2 For every example, write the snapshot, read it back, and assert that the
      record stream is byte-identical and that the netlist compiled from the
      reloaded snapshot, with no traits passed, equals the elaboration's
- [x] 5.3 Run `python examples/regenerate.py`, and keep a rewritten output only if
      a line other than a snapshot hash moved (D8). All sixteen rewritten files
      (each example's `.net` and `graph.txt`) differed only in the hash, so none
      was kept
- [x] 5.4 Add `CHANGELOG.md` entries under Unreleased
- [x] 5.5 Run `python -m pytest` and confirm the suite passes with no new skips:
      692 collected, 686 passed, 6 skipped. The skips are the four optional `mcp`
      SDK tests, the optional graph analysis extra, and ngspice, the same six as
      before this change
- [ ] 5.6 Before archive, settle the schema version number against PR #4 (design
      Open Questions) and record the outcome here
- [x] 5.7 Declare `dimension` an ordered collection, with a test that a
      reference's dimension survives canonical form (D9)

## 6. Review fixes

- [x] 6.1 Under a manifest older than schema 1.2, load a record holding an
      expression reference as an `OpaqueEntity` with its reason, tested against
      `tests/fixtures/schema-1.1`, written by commit `62a6de3` (D9)
- [x] 6.2 Keep `OpaqueTrait` out of a registry built from entities, record it as
      untyped, and refuse a netlist or a simulation plan that needs untyped state
      (`ELAB-0015`) (D10)
- [x] 6.3 Copy traits into a registry built from entities, so changing one does
      not change the snapshot (D10)
- [x] 6.4 Render a decimal without depending on a context's precision, so a
      rendering renders to itself at any magnitude
- [x] 6.5 Compare fields by canonical bytes in the semantic diff, so a program's
      snapshot and its reload diff as unchanged
- [x] 6.6 Dispatch a `class: "topology"` record carrying any topology field to
      `TopologyConstraint`, so one missing `mode` is refused rather than kept
- [x] 6.7 Normalize an arithmetic exponent to a `Fraction`, write a year below
      1000 with four digits, and let an MCP session bound to a snapshot answer
      with its traits
- [x] 6.8 Run `python -m pytest` with the review fixes: 720 collected, 714 passed,
      6 skipped, the same six optional extras as before
