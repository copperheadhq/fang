## 1. Fixtures and oracles

- [ ] 1.1 Write `tests/fixtures/kicad_schematic/generate.py`. It emits KiCad 10
      schematics from symbols it defines itself, never from KiCad's libraries,
      with one fixture per rule: orientations, junctions, labels on wires, label
      priority and ties, power symbols (global and local), multi-unit symbols with
      an unplaced unit, no-connect markers, reference ordering (`R9` against
      `R10`), a hierarchy with a reused sheet, and a project with several
      top-level sheets (D12)
- [ ] 1.2 Export each fixture's oracle netlist with `kicad-cli` 10.0.4 and commit
      it beside the fixture. For the project with several top-level sheets, export
      from its single-root equivalent (D12)
- [ ] 1.3 Add a regeneration test that is skipped when `kicad-cli` is absent, and
      a note in the fixture directory saying how the fixtures were made and that
      they are this project's to license

## 2. Record fields

- [ ] 2.1 Add `symbol`, `value_text`, `fitted`, and `sheets` to `Component`;
      `electrical_type` and `no_connect` to `Pin`; and `net_class` to `Net`. Each
      is written only when set (D7)
- [ ] 2.2 Add their decoders and extend the rehydration catalogue and completeness
      tests
- [ ] 2.3 Move `SCHEMA_VERSION` to the next free minor version (D13), and test that
      a record without the new fields is byte-identical to before

## 3. The drawing reader

- [ ] 3.1 Read `.kicad_pro` top-level sheets and net class settings, or a lone
      `.kicad_sch` as its own root. Check the format version and report one older
      than 20231120 (D5, D11)
- [ ] 3.2 Read embedded symbol definitions: units, body styles, and pins with
      their number, name, electrical type, and position
- [ ] 3.3 Read placed symbols: the uuid, `lib_id`, position, angle, mirroring,
      unit, the five fitted flags, properties, and instance entries
- [ ] 3.4 Read wires, junctions, local, global, and hierarchical labels, power
      symbols, no-connect markers, and sheet symbols with their pins, building
      sheet instances with instance and name paths (D5)
- [ ] 3.5 Place each pin in sheet coordinates with exact decimal geometry and the
      transform the probes established (D2)
- [ ] 3.6 Report every construct in D11, one by one or once per kind per sheet as
      D11 says

## 4. Net resolution and naming

- [ ] 4.1 Join points and segments as D3 describes, then join by name across
      sheets and down the hierarchy
- [ ] 4.2 Name nets by KiCad's priority, ties, and sheet-path prefixes, and
      generate `Net-(...)` and `unconnected-(...)` names with `{slash}` escaping
      and `_n` suffixes (D4)
- [ ] 4.3 Test each rule on drawing models built in code, and on every fixture
      against its oracle

## 5. Entities and identity

- [ ] 5.1 Build components from placed units sharing a reference. Key them on the
      board footprint path form, with a path derived from uuids; record the
      designator, symbol reference, value text, fitted state, and sheets (D6, D7)
- [ ] 5.2 Build pins keyed on the component identifier and number, with their name,
      electrical type, and no-connect intent, and report a no-connect pin that
      shares a net
- [ ] 5.3 Build nets keyed on their name, or for an unnamed net on its lowest
      member pin, with KiCad's name as an alias and the net class (D6)
- [ ] 5.4 Attach `Footprint` and `Sourcing` traits, and store the remaining fields
      under the `kicad` extension, reporting a field that differs between units
      (D7)
- [ ] 5.5 Test that re-annotating references and re-importing keeps every
      component identifier, and that an unchanged re-import keeps the snapshot
      hash

## 6. Presentation records

- [ ] 6.1 Add `fang/presentation.py` with symbol, label, power, and no-connect
      placements, a document naming its snapshot, and canonical serialization (D8)
- [ ] 6.2 Write and read the document under `.copperhead/presentation/`
- [ ] 6.3 Add `diff_presentation`, classifying every moved placement as a
      presentation change, and test that moving a symbol changes neither
      identifiers nor the snapshot hash

## 7. Fidelity and the command

- [ ] 7.1 Add `compare_with_netlist`, which matches nets by membership and reports
      component, membership, and name differences (D9)
- [ ] 7.2 Add `fang import <project> [--netlist <file>]`, applying the import
      through the commit gate and persisting the snapshot, mapping table, import
      report, and presentation document. It exits non-zero on a fidelity
      difference (D10)
- [ ] 7.3 Test the command end to end on a fixture, including a re-import that
      reuses the mapping table

## 8. Verification

- [ ] 8.1 Run the PCBGolf project locally, uncommitted, against its board: every
      footprint path resolves to an imported component, and every one of the
      board's 302 net names and pad memberships matches. Record the numbers here
- [ ] 8.2 Add `CHANGELOG.md` entries under Unreleased
- [ ] 8.3 Run `python -m pytest` and confirm the suite passes with no new skips
      beyond the regeneration test
- [ ] 8.4 Raise the RFC 12 Section 14.4 wording on connections along a wire as an
      erratum on copperhead-rfcs (Open Questions)
