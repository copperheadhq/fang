# imported

Not an example program: a KiCad netlist read *into* the kernel.

[`reference.net`](reference.net) is a netlist KiCad itself wrote, not one written
by hand, so the import path in [`fang/kicad.py`](../../fang/kicad.py) and
[`fang/importing.py`](../../fang/importing.py) is tested against the form a CAD
tool actually produces. It reads the file into entities — components, nets, and
the pins that join them — with `imported` identity rather than derived identity,
and produces a mapping table and an import report beside them.

The board is small and carries every construct the reader has to handle: three
components, four nets that join pins, four nets of a single pin that KiCad names
`unconnected-(...)`, and the fields, properties, pin functions, and pin types the
reader reports rather than stores.

It is what four acceptance criteria in
[`tests/test_acceptance.py`](../../tests/test_acceptance.py) are demonstrated
on: that an import reports whatever it could not carry (AT-R1), that
reformatting the source text leaves the derived identifiers alone (AT-R3), that
every imported entity carries a conforming provenance record (AT-R9), and that
importing an existing project reports every mismatch (AT-K1).

```bash
python -m pytest tests/test_acceptance.py
```

## Where the file came from

| | |
| --- | --- |
| Source project | `test/fixtures/open-key/hardware/open-key.kicad_sch` in [copperheadhq/copperhead](https://github.com/copperheadhq/copperhead) |
| Source commit | `8ad2daa` |
| License | Apache-2.0, the same as this repository |
| Tool | KiCad 10.0.4 |
| Command | `kicad-cli sch export netlist --format kicadsexpr -o reference.net open-key.kicad_sch` |

Two lines differ from what the command wrote, and neither carries meaning:

- `(source ...)` in the `design` block held the absolute path of the exporting
  machine; it is now the file name, `open-key.kicad_sch`.
- `(date ...)` in the `design` block held the time of the export; it is now the
  fixed `2026-09-13T00:00:00`, so re-exporting does not change the file.

Nothing else was edited. To refresh the file, run the command above from the
source project's directory and apply the same two substitutions.
