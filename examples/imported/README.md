# imported

Not an example program: a KiCad netlist read *into* the kernel.

[`reference.net`](reference.net) is a hand-written netlist in KiCad's `export`
s-expression form. The import path in [`fang/importing.py`](../../fang/importing.py)
reads it into entities — components, nets, and the pads that join them — with
`imported` identity rather than derived identity, and produces a mapping table
and an import report beside them.

It is what four acceptance criteria in
[`tests/test_acceptance.py`](../../tests/test_acceptance.py) are demonstrated
on: that an import reports whatever it could not carry (AT-R1), that
reformatting the source text leaves the derived identifiers alone (AT-R3), that
every imported entity carries a conforming provenance record (AT-R9), and that
importing an existing project reports every mismatch (AT-K1).

```bash
python -m pytest tests/test_acceptance.py
```
