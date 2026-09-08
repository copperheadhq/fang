# Parity: the same board, built by both toolchains

This is an [atopile](https://github.com/atopile/atopile) project whose boards mirror two Fang
examples instance for instance — [`examples/divider/`](../divider/) and
[`examples/blinky/`](../blinky/). Both toolchains are given the same design, and
[`tests/test_parity.py`](../../tests/test_parity.py) asserts that what they produce agrees.

## What is compared, and what is not

A Fang build emits a KiCad netlist. An atopile build emits a `.kicad_pcb` — atopile has no
netlist target, and the layout is its artifact. Reduced to what a board *is*, both say the same
two things, and those are what the test compares:

- which instances become components, named by their path in the source (`top`, `mcu`), which the
  atopile build writes onto every footprint as its `atopile_address` property;
- the partition of `(instance, pad)` into nets.

Three things are deliberately **not** compared, because they are each toolchain's own business
and a test that asserted on them would be asserting a difference rather than an agreement:

- **Designators.** Both assign them deterministically, in different orders. atopile sorts by
  module locator, so the divider's `bottom` is `R1` and `top` is `R2`; Fang assigns in
  declaration order and calls them the other way round. Neither is wrong.
- **Net names.** atopile names a net after the signal that reaches it (`supply`, `ground`); Fang
  names an unnamed net after its first node (`Net-(R1-Pad1)`). The membership is what matters.
- **Part identity.** atopile picks a vendor part; Fang leaves a generic part generic until
  someone selects one. That difference is the point of both designs, not a defect in either.

A pad joined to nothing is dropped from both sides before comparing: KiCad gives it net 0 and
Fang gives it a net of its own, and neither is connectivity.

## Why the parts are atomic

Every component in [`elec/src/parts/parts.ato`](elec/src/parts/parts.ato) is an atomic part: its
footprint and pins are declared here rather than picked. atopile 0.15's picker requires an
account, and a test that needs a login is not a test. Declaring the parts also removes the last
excuse for a difference — both toolchains are handed the same parts, so a disagreement is a
disagreement about the design.

The footprints are minimal: pads only, on `F.Cu`, in the right count and with the right names.
The build warns that they have no silk outline, which is true and does not matter here.

## Rebuilding the atopile side

The `.kicad_pcb` files under `elec/layout/` are checked in, so the suite runs without atopile
installed and without network access. To refresh them:

```bash
pip install atopile              # 0.15.8 is what these were built with
cd examples/parity
ato --non-interactive build      # updates elec/layout/<build>/<build>.kicad_pcb in place
cd ../.. && python -m pytest tests/test_parity.py
```

`build/` is generated and ignored; the layout is the artifact.

## Adding a board

1. Write the Fang example under [`examples/`](..).
2. Mirror it here as `elec/src/<name>.ato`, using the same instance names, and add it to
   `builds:` in [`ato.yaml`](ato.yaml). Add any part it needs to `parts.ato` with a footprint
   beside it.
3. Add the name to `BOARDS` in [`tests/test_parity.py`](../../tests/test_parity.py).

Keep every part in a board distinguishable — the comparison is by instance path, so two
identical parts are fine, but a board written so that no instance can be told from another
proves less than it appears to.
