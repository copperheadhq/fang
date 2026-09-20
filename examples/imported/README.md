# imported

Not an example program: a KiCad netlist read *into* the kernel.

[`reference.net`](reference.net) is a netlist in KiCad's `export`
s-expression form, written the way Eeschema writes one: a keyed value is a
nested list, `(net (code "1") (name "+3V3"))`, not a run of flat atoms. The
import path in [`fang/importing.py`](../../fang/importing.py) reads it into
entities, meaning components, nets and the pads that join them, under `imported`
identity rather than derived identity. It writes a mapping table and an import
report beside them.

Four acceptance criteria in
[`tests/test_acceptance.py`](../../tests/test_acceptance.py) are demonstrated on
it: that an import reports whatever it could not carry (AT-R1), that reformatting
the source text leaves the derived identifiers alone (AT-R3), that every imported
entity carries a conforming provenance record (AT-R9) and that importing an
existing project reports every mismatch (AT-K1).

```bash
python -m pytest tests/test_acceptance.py
```
