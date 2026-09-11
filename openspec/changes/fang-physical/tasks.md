# Tasks: The Physical Layer

Ordered by the migration plan in [design.md](design.md). Step 2 is the only step
that can regress the gate; it lands alone.

## 1. The entity model and the root shape

- [x] 1.1 Add `fang/physical.py` with `Board`, `Stackup`, `Layer`, `Placement`,
      `Pad`, `Via`, `Trace`, `Zone`, and `Region` as frozen dataclasses over
      `Entity`, each implementing `references()` and `as_dict()`; verify every
      new kind round-trips through `serialization.canonical_bytes` and that a
      test asserts both protocol methods exist on each.
- [x] 1.2 Have each physical entity name the entity it realizes — trace to net,
      placement to component, pad to pin — and return it from `references()`;
      verify `validation.validate` reports a dangling reference when the named
      entity is absent.
- [x] 1.3 Allocate the missing prefixes in `identity.PREFIXES` (`stackup`,
      `layer`, `placement`, `pad`, `via`, `trace`, `zone`; `board` and `region`
      are already there); verify identifiers derive reproducibly and that
      lengthening still reproduces the same lengths against an existing set.
- [x] 1.4 Add `_PHYSICAL_OF` beside `graph._COLLECTION_OF` and group physical
      entities under the `physical` root mapping with every key present when
      empty; verify a snapshot with no board serializes nine empty lists and
      that an unregistered kind still falls through to `extensions`.
- [x] 1.5 Add `"layers"` to `serialization.ORDERED_COLLECTIONS`; verify a
      stackup serializes its layers top to bottom rather than sorted.
- [x] 1.6 Register the new kinds in `diff._KIND_TO_CHANGED` as
      `PHYSICAL_CHANGED`; verify a placement move classifies as physical and
      not electrical — the spec scenario's wording, and the right one: board
      position is not view presentation — and that removing a trace does not
      invalidate an electrical check.
- [x] 1.7 Bump `SCHEMA_VERSION` to `1.2` and confirm it moves independently of
      `__version__`; verify a 1.1 artifact still reads and that the major-version
      rejection path is untouched.
- [x] 1.8 Regenerate every example with `python examples/regenerate.py` and
      commit the outputs; verify `python -m pytest tests/test_examples.py` is
      green and that the only diffs are the schema version.

## 2. The resolver and the check class

- [x] 2.1 Extend `Snapshot.resolver()` to resolve a `physical.`-prefixed
      attribute over the physical entities realizing the target; verify a bare
      attribute of the same name still resolves from `parameters` and is
      unaffected.
- [x] 2.2 Aggregate a multi-segment realization to `Quantity.range(min, max)`
      with `ValueStatus.INFERRED` and the board realization as its source;
      verify a rule fails when the narrowest segment fails and passes when every
      segment does.
- [x] 2.3 Resolve an unrealized or unknown physical attribute to unknown;
      verify a routing rule on an unrouted net evaluates `CheckStatus.UNKNOWN`
      and is reported undecided rather than as a pass.
- [x] 2.4 Fix the physical attribute vocabulary in `fang/physical.py` and name
      it in the spec's terms. A reference evaluates to an interval, so every
      referenceable attribute is a scalar quantity: `layer` (a string) and
      `position` (a pair) are not, and position is carried as scalar
      `position_x` / `position_y` instead. Verify an unrecognized name resolves
      unknown rather than raising.
- [x] 2.5 Narrow `CONSTRAINT_CHECK` to the electrical classes and add
      `ROUTING_CHECK` in `fang/routing.py` over `ROUTING`, `PLACEMENT`, and
      `MANUFACTURING`, scoped to the entities its constraints target; verify an
      electrical constraint is still evaluated under the same check name and
      that a routing constraint is evaluated exactly once.
- [x] 2.6 Move `DEFAULT_CHECKS` so `KernelGraph.__init__` defaults to it rather
      than to `(CONSTRAINT_CHECK,)`, keeping the `checks.py` re-export; verify
      a graph constructed with no explicit checks runs the routing check when a
      routing constraint is touched, and does not when nothing touches one.
- [x] 2.7 Verify gate behavior end to end: a failing hard routing rule rejects
      the proposal and the rejection carries the rule identifier and the diff;
      an advisory rule reports without blocking; the head is unchanged in both.

## 3. Authoring physical intent

- [x] 3.1 Add keyword-only `constraint_class` and `constraint_kind` arguments to `lang.require()`,
      defaulting to today's `electrical` / `declared`, and carry them through
      `ElaborationContext` into `elaborate._build_constraints`; verify every
      existing example elaborates to byte-identical entities.
- [x] 3.2 Add the `board()` declaration method beside `constraints()` with the
      same once-per-elaboration rules; verify the declaration is recorded rather
      than evaluated and carries the source location of its line.
- [x] 3.3 Settle the copper-weight spelling left open in design.md: `ozcu`, a
      length rather than a mass, because what a stackup composes with is the
      thickness the weight produces; verify a layer's copper weight is a
      `Quantity` and that a bare number is refused.
- [x] 3.4 Verify no placer, router, or field solver is constructed during
      elaboration, in the style of the existing sandbox assertion at
      [spec.md:1511](../../specs/fang-kernel/spec.md#L1511).

## 4. Projections outward

- [ ] 4.1 Emit a `.kicad_dru` from routing-class projections, sorted by
      constraint identifier; verify each rule names the constraint it projects
      and restates no field the constraint record already defines.
- [ ] 4.2 Emit net class assignments from the same projections; verify a net
      belongs to exactly one class and that the assignment names its origin.
- [ ] 4.3 Verify emission is byte-identical across two runs from one committed
      snapshot and across processes with differing `PYTHONHASHSEED`.
- [ ] 4.4 Add the rules export to `fang/cli.py`; verify `fang export --rules`
      writes the file and exits non-zero with a diagnostic when the snapshot
      holds no routing constraint. Sequence this after `fang-mcp`'s CLI work
      rather than editing `cli.py` in parallel.

## 5. Reading geometry back

- [ ] 5.1 Add a `.kicad_pcb` reader to `fang/kicad.py` over the existing
      `sexpr` parser, recognizing board outline, stackup, `footprint`
      placement, `segment`, `via`, and `zone`; verify a real board file parses
      into physical entities with derived identities.
- [ ] 5.2 Route every unrecognized construct through `importing.Unrepresented`;
      verify an unknown board element is reported with its location under
      `IMPORT-0001` and is not approximated by a different entity kind.
- [ ] 5.3 Record every external identifier in the existing `MappingTable`;
      verify no external identifier becomes a canonical identity.
- [ ] 5.4 Report a board that joins two pins the committed netlist does not as
      a finding against the board; verify the netlist is not rewritten.
- [ ] 5.5 Offer a layout-chosen pin swap as `Realization.implied_changes`;
      verify it returns through `to_transaction` and the gate, and that the
      ingest itself changed no semantic state.
- [ ] 5.6 Verify `materialize()` refuses a board realization whose parent is not
      the committed snapshot, and that `ingest_external_results` refuses DRC
      results produced against anything but the committed head.

## 6. Diagnostics, spec, and the worked example

- [ ] 6.1 Allocate the routing codes with `_allocate` at the bottom of the
      `TOPO` block — unresolved physical reference, board disagrees with the
      netlist, unrepresented board construct if `IMPORT-0001` does not cover it;
      verify no code was reused and the registry assertions pass. Sequence after
      `fang-mcp`'s `_allocate` calls to avoid a silent collision on rebase.
- [ ] 6.2 Sync the delta into `openspec/specs/fang-kernel/spec.md` and give each
      new module a docstring quoting the requirement it implements by name;
      verify the `Spec:` link is present in `physical.py` and `routing.py`.
- [ ] 6.3 Add an example folder with `<name>.py`, `README.md`, and `out/`,
      demonstrating a width rule that fails against one board and passes against
      another; verify `tests/test_examples.py` discovers it and its committed
      outputs match, and update `MANIFEST.in` if it reads anything new.
- [ ] 6.4 Add stage 12 to `openspec/ROADMAP.md` and mark it delivered; verify
      the table renders and the stage names what it shipped.
- [ ] 6.5 Run the full suite and confirm it is green with no new skips beyond
      optional binaries; verify `python -m pytest -rs` names only NetworkX and
      ngspice.
