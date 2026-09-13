## 1. Reader

- [x] 1.1 Make `Node.pairs()` read nested `(key atom)` children first and fill any
      missing key from flat atom pairs (design D1); cover nested, flat, mixed
      (nested wins), and a longer child that is not a field in `tests/test_sexpr.py`
- [x] 1.2 Read the top-level `version` in `read_netlist`, and report a value other
      than `E`
- [x] 1.3 Restrict the reader's known sets to what it stores and report each
      accepted-but-unstored construct by occurrence (D3): a component `field` by
      name, a `datasheet`, a `property` other than `fang_id` by name, a net
      `class`, and a node `pinfunction` or `pintype`
- [x] 1.4 Make `_recover_fang_id` read `(property (name "fang_id") (value ...))`
      as well as the flat form, with a test for each

## 2. Netlist compiler

- [x] 2.1 In `compile_netlist`, keep a one-node class when one of its pins carries
      a source-recorded name, and drop it otherwise (D4)
- [x] 2.2 Test that a source-named single-pin net survives import, compile, and
      emit, and that a pin a program leaves unconnected yields no net

## 3. Emitter

- [x] 3.1 Rewrite `emit_netlist` to write `version`, the `design` fields, the
      `comp` fields, `field`, `property`, `net`, and `node` as nested lists with
      two-space indentation (D2), keeping emission byte-identical for unchanged
      input
- [x] 3.2 Replace the flat-string assertions in `tests/test_kicad.py`,
      `tests/test_cli.py`, `tests/test_runtime.py`, and `tests/test_examples.py`
      with assertions on the parsed structure (D6)

## 4. Fixture and conformance

- [x] 4.1 Export copperhead's `test/fixtures/open-key/hardware/open-key.kicad_sch`
      at commit `8ad2daa` with `kicad-cli sch export netlist --format kicadsexpr`
      (KiCad 10.0.4), normalize only `(source ...)` to the file name and
      `(date ...)` to a fixed timestamp, and replace
      `examples/imported/reference.net` with the result (D5)
- [x] 4.2 Rewrite `examples/imported/README.md` to record the command, the KiCad
      version, the source repository and commit, the license, and the two
      normalized lines
- [x] 4.3 Add a test that the fixture imports with 3 components, 8 nets, and 12
      nodes, each net carrying the name the file gives it
- [x] 4.4 Update AT-R1 in `tests/test_acceptance.py` to the fixture's components,
      its eight net names, and the exact set of unrepresented constructs; confirm
      AT-R3 and AT-K1 pass on it, with AT-K1 comparing all eight nets
- [x] 4.5 Add a conformance test: every child Fang emits in `export`, `design`,
      `comp`, `fields`, `field`, `property`, `net`, and `node` appears in the
      same element of the fixture, apart from `snapshot` and `project` in
      `design`
- [x] 4.6 Convert the hand-written netlists in `tests/test_import.py` and
      `tests/test_acceptance.py` to KiCad's nested form, keeping one flat-form
      test for the legacy scenario

## 5. Outputs, changelog, and verification

- [x] 5.1 Run `python examples/regenerate.py` and keep every rewritten
      `examples/*/out/*.net`
- [x] 5.2 Add `CHANGELOG.md` entries under Unreleased: Fixed (KiCad netlists
      import with their nets; accepted-but-unstored constructs are reported;
      source-named single-pin nets survive) and Changed (`fang export` writes
      KiCad's nested form, a breaking output change; the reader still imports
      the flat form)
- [x] 5.3 Run `python -m pytest` and confirm the suite passes with no new skips
- [x] 5.4 Import a larger KiCad export locally, without committing it, and confirm
      every component, net, and node is recovered with nothing dropped silently
- [x] 5.5 Manual check in the KiCad GUI: load an emitted netlist into KiCad's PCB
      editor and record here whether it loads and whether `snapshot` and
      `project` inside `design` are accepted; if they are rejected, apply the
      fallback in design D2's risk before archive

      Result, 2026-09-13, KiCad 10.0.4: the PCB editor started standalone, File →
      Import → Netlist, "Load and Test Netlist" on
      `examples/usb_uart_bridge/out/usb_uart_bridge.net`. KiCad read the file and
      processed all 16 symbols; `snapshot` and `project` inside `design` raised
      nothing, so the fallback is not needed. All 16 errors are "footprint not
      found", expected for the examples' generic `Package:` footprints. KiCad
      linked symbols by `tstamps`, which Fang does not write yet; see design Open
      Questions.
