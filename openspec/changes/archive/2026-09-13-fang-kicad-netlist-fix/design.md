## Context

`fang/kicad.py` holds both halves of the KiCad netlist adapter. The reader reads a
component through `Node.value()`, which walks nested children, so components
import. It reads a net and a node through `Node.pairs()`, which reads only flat
atoms, so on a KiCad file every node fails the "ref and pin" check and no net is
recovered. The emitter builds every element as `SExpr(name, "key", "value", ...)`,
which renders the same flat form. The only import fixture,
`examples/imported/reference.net`, is hand-written in that form, and
`tests/test_kicad.py`, `tests/test_cli.py`, `tests/test_runtime.py`, and
`tests/test_examples.py` assert flat strings such as `(export "version" "E"` and
`(node "ref" ...`.

KiCad 10.0.4's `kicad-cli sch export netlist --format kicadsexpr` writes, for
copperhead's `open-key` project:

```
(export (version "E")
  (design (source ...) (date ...) (tool ...) (sheet ...))
  (components
    (comp (ref "R1") (value "10k") (footprint "...")
      (fields (field (name "Footprint") "...") ...)
      (libsource ...) (property (name "Sheetname") (value "...")) ...
      (sheetpath ...) (tstamps "...") (units ...)))
  (groups) (variants) (libparts ...) (libraries ...)
  (nets
    (net (code "1") (name "3V3") (class "Default")
      (node (ref "R1") (pin "1") (pintype "passive")))
    (net (code "5") (name "unconnected-(U1-GPIO0-Pad3)") (class "Default")
      (node (ref "U1") (pin "3") (pinfunction "GPIO0_3")
            (pintype "passive+no_connect")))))
```

Two further facts constrain the change. `compile_netlist` drops every class of
fewer than two nodes ("a net of one node is an unconnected pin, not a net"), so a
KiCad file's `unconnected-(...)` nets vanish on re-emission. And KiCad offers no
headless netlist import: `kicad-cli` has no such command, and the 10.0.4 `pcbnew`
Python bindings expose no netlist reader, so the suite cannot ask KiCad to load a
file Fang wrote.

## Goals / Non-Goals

**Goals:**

- Import every component, net, and node of a netlist KiCad exported.
- Emit KiCad's nested form, deterministically.
- Keep importing the flat form earlier Fang releases wrote.
- Report every construct the reader accepts but does not store.
- Round-trip a net the source named even when it has one node.
- Test against a file KiCad actually wrote.

**Non-Goals:**

- Modelling pin names, pin electrical types, no-connect intent, net classes,
  fitted state, or sheet membership. Those are record changes under RFC 3
  version 1.4 and belong to the schematic-import change.
- Reading `.kicad_sch` or `.kicad_pcb` files.
- Netlist formats other than KiCad's s-expression export.
- Proving in the suite that KiCad's loader accepts an emitted file (see Risks).

## Decisions

### D1. `Node.pairs()` reads nested fields, with flat pairs as the fallback

A child list of exactly two items whose second item is an atom, such as
`(name "GND")`, is a field. `pairs()` returns those, then fills any key still
missing from flat atom pairs. A key present in both forms takes the nested value:
KiCad never mixes them, so a mixed file is malformed input, and the nested reading
is the tool's own. A longer child such as `(node ...)` is never a field.

Alternative considered: a new `fields()` method, leaving `pairs()` flat. Rejected:
`pairs()` is documented as reading pairs "as KiCad writes them", which is exactly
what it fails to do, and a correct method beside a misnamed one leaves the same
trap for the next adapter. It has two callers, both in the netlist reader.

### D2. The emitter writes KiCad's structure with Fang's whitespace

Every element Fang writes is nested as KiCad nests it:

```
(export (version "E")
  (design (source "...") (tool "fang ...") (snapshot "sha256:...") (project "PRJ-..."))
  (components
    (comp (ref "R1") (value "10 kOhm") (footprint "R_0603")
      (fields (field (name "MPN") "RC0603FR-0710KL"))
      (property (name "fang_id") (value "CMP-..."))))
  (nets
    (net (code "1") (name "Net-(R1-Pad1)")
      (node (ref "R1") (pin "1")))))
```

Indentation stays two spaces rather than KiCad's tabs. Whitespace carries no
meaning in an s-expression, emission stays byte-identical for unchanged input, and
the committed example outputs stay readable in review. Alternative considered:
tabs, to look like `kicad-cli` output byte for byte. Rejected as cosmetic, and it
would churn every output again whenever KiCad changes its layout.

`snapshot` and `project` stay inside `design`. They are how a file on disk names
the graph state it came from ("The Netlist Is A Projection"), and they are not
KiCad elements; see Risks.

### D3. Known means stored

The reader's known sets name only what it stores:

- top level: `version` (read; a value other than `E` is reported), `design`,
  `components`, `nets`. `groups`, `variants`, `libparts`, and `libraries` stay
  reported, as today.
- `design`: `source`, `date`, `tool`, `sheet`, `snapshot`, `project`. These
  describe the file, not the design; the file's identity is already recorded as
  every entity's source location.
- component: `ref`, `value`, `footprint`, and `property` only when its name is
  `fang_id`. A `field` is reported by its name, a `datasheet` is reported, a
  `property` with any other name is reported by its name, and `libsource`,
  `sheetpath`, `tstamps`, and `units` stay reported.
- net: `code`, `name`, `node`; a `class` is reported.
- node: `ref`, `pin`; a `pinfunction` or a `pintype` is reported.

Each occurrence is one entry naming the construct and where it appeared, as the
report already works. A large board therefore reports a long list; summarizing it
is a projection's job, not the report's.

### D4. A single-node net survives when its source named it

`compile_netlist` keeps a class of one node when one of its pins carries a name
recorded from the source (the `_recorded_names` lookup), and drops it otherwise.
A name a source gave a net is engineering data, which is the rule `_net_name`
already states. KiCad's `unconnected-(...)` nets record which pins the designer
left open, and dropping them breaks the unchanged-import round trip on any real
file. A single node Fang merely inferred is still dropped, so no netlist compiled
from a program changes.

Alternative considered: compare only multi-pin nets in AT-K1. Rejected: it hides a
real difference in order to pass a test.

### D5. The fixture is a real KiCad export, normalized in two lines

`examples/imported/reference.net` is replaced by what
`kicad-cli sch export netlist --format kicadsexpr` (KiCad 10.0.4) wrote for
`test/fixtures/open-key/hardware/open-key.kicad_sch` in the copperhead repository
at commit `8ad2daa` (Apache-2.0). Two non-semantic lines are normalized: the
`(source ...)` absolute path becomes the file name, and `(date ...)` becomes a
fixed timestamp. Nothing else is edited. The folder's README records the command,
the KiCad version, the source commit, and those two edits.

The project is small (3 components, 8 nets, 12 nodes), redistributable, and
exercises every path this change touches: multi-pin nets, KiCad-named single-pin
nets, properties, fields, pin functions, and pin types. The flat-form case stays
as an inline string in `tests/test_import.py`. Alternative considered: rewriting
the old fixture into nested form by hand. Rejected: that repeats the original
mistake of testing against a file no CAD tool wrote.

### D6. Tests assert structure, not text

Tests that matched flat strings parse the emitted text and assert element shape,
so a whitespace change cannot break them and a structural regression cannot pass
them. A conformance test compares, for each element Fang emits, the heads of its
children against the same element in the real fixture.

## Risks / Trade-offs

- [KiCad's own loader is not exercised] → Structural conformance against a real
  export (D6), plus one manual check before archive: load an emitted netlist into
  KiCad's PCB editor and record the result in `tasks.md`.
- [`snapshot` and `project` inside `design` are not KiCad elements, and a strict
  loader could reject them] → Settled by the same manual check. If KiCad rejects
  them, this change moves both into a carrier KiCad keeps, rather than dropping
  the snapshot link.
- [Loss reports grow long on real boards] → Accepted. The schematic-import change
  shortens them by modelling pin names, pin types, and net classes.
- [`fang export` output changes form] → Recorded in `CHANGELOG.md` as a breaking
  output change. The reader still imports the flat form.
- [`pairs()` now sees nested children] → Its only callers are the two reader
  sites this change rewrites, and flat input reads as before.

## Migration Plan

Run `python examples/regenerate.py` to rewrite every `examples/*/out/*.net`. There
is no persisted data to migrate: `.copperhead/design.jsonl` holds entities, not
netlists, and a workspace's cached `design.net` is rebuilt by the next
`fang build`. Rolling back leaves files written in the new form unreadable by the
old reader, which is acceptable before 1.0 and is noted in `CHANGELOG.md`.

## Open Questions

- Does KiCad's netlist loader accept `snapshot` and `project` inside `design`?
  Resolved: KiCad 10.0.4's PCB editor loads an emitted netlist with "Load and
  Test Netlist" and processes every symbol, and neither element raises anything.
  The fallback under Risks is not needed.
- Carried to the schematic-import change: KiCad links netlist symbols to board
  footprints by `tstamps` by default, and Fang writes no `tstamps` or `sheetpath`
  yet. Updating an existing board from a Fang netlist therefore needs
  reference-designator linking until symbol UUIDs are carried (RFC 12
  Section 14.4).
