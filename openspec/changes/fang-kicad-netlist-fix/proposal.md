## Why

Fang cannot read a netlist KiCad writes. `read_netlist` recovers the components
of a `kicad-cli sch export netlist` file but no nets at all: KiCad nests every
field as `(key "value")`, and `Node.pairs()` reads only flat `"key" "value"`
atoms, so every node is dropped as "a node without ref and pin". On a 245-part
board exported by KiCad 10.0.4, 1,053 of 1,053 nodes were dropped; on
copperhead's `open-key` test project, 12 of 12.

The suite never noticed because nothing in it is a KiCad file. `emit_netlist`
writes the same flat form, and the only import fixture,
`examples/imported/reference.net`, was written by hand in it, so every round
trip exchanges Fang's own format with itself. The reader also accepts a
component's `fields`, `property`, and `datasheet`, a net's `class`, and a node's
`pinfunction` and `pintype`, and neither stores nor reports any of them, which
is the silent loss "Imports Report What They Could Not Represent" forbids.

This is the first of five changes implementing RFC 12 version 1.2. Every change
after it checks an import against the netlist the CAD tool exports for the same
sources (RFC 12 Section 14.4), so the adapter has to read KiCad's own files
before anything is measured against them.

## What Changes

- **Reading KiCad's form.** `Node.pairs()` reads nested `(key "value")` fields
  and falls back to flat atom pairs, so `read_netlist` recovers every component,
  net, and node of a KiCad-exported netlist. A file in the flat form earlier Fang
  releases wrote still imports.
- **Writing KiCad's form.** `emit_netlist` writes the export, design, component,
  field, property, net, and node elements nested as KiCad writes them:
  `(export (version "E") ...)`, `(net (code "1") (name "GND") (node (ref "R1")
  (pin "1")))`, `(property (name "fang_id") (value "CMP-..."))`. **BREAKING**
  for anything that matches `fang export` output textually in the flat form; the
  reader keeps accepting that form.
- **Honest loss reporting.** A construct the reader accepts but does not store
  is reported: a component's `fields` and `datasheet`, a `property` other than
  `fang_id`, a net's `class`, and a node's `pinfunction` and `pintype`. The
  reader's known sets name only what it stores. The top-level `version` block is
  read rather than reported.
- **Source-named single-pin nets survive.** The netlist compiler keeps a
  one-node net whose name the snapshot records from its source, such as KiCad's
  `unconnected-(U1-GPIO0-Pad3)`, so an unchanged import re-emits unchanged. A
  one-node net Fang only inferred from connections is still dropped.
- **A real fixture.** `examples/imported/reference.net` becomes a netlist that
  KiCad 10.0.4 exported from copperhead's `open-key` test project (Apache-2.0),
  with its provenance recorded in the folder's README. AT-R1, AT-R3, and AT-K1
  then run against KiCad's own output.
- Every committed `examples/*/out/*.net` is regenerated in the new form.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `fang-kernel`: adds a requirement that the KiCad netlist adapter reads and
  writes KiCad's own form, including the legacy flat form and the round trip of
  a source-named single-pin net; and extends "Imports Report What They Could Not
  Represent" to constructs a reader accepts but does not store.

## Impact

- Code: `fang/sexpr.py` (`Node.pairs`), `fang/kicad.py` (the reader's known sets,
  loss reporting, the emitter), `fang/netlist.py` (source-named one-node nets).
  The callers `fang/cli.py` (`fang export`) and `fang/runtime.py` (the emitted
  `design.net`) change output format only.
- Tests: `tests/test_kicad.py`, `tests/test_import.py`, `tests/test_acceptance.py`
  (AT-R1's expected set of unrepresented constructs), `tests/test_cli.py`,
  `tests/test_runtime.py`, `tests/test_examples.py`, `tests/test_sexpr.py`.
- Data: `examples/imported/reference.net` and its `README.md`; every
  `examples/*/out/*.net`; `CHANGELOG.md`.
- No EIR schema change: a netlist is an interchange encoding, and imported
  entities keep their shape. No new dependency.
- Out of scope, and left to the schematic-import change under RFC 3 version 1.4:
  modelling pin names, pin electrical types, no-connect intent, net classes, and
  fitted state; reading `.kicad_sch` files.
