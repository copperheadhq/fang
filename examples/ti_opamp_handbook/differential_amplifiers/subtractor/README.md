# subtractor

SBOA092B page 74, *Subtractor*: the differential input amplifier of page 67
with every resistor 10 kΩ. E1 goes through R_I into the inverting input with
R_O back from the output; E2 is divided by R_I over R_O onto the
non-inverting input.

```
E_O = E2 - E1
```

## What the program says

The figure gives every value, so nothing is chosen. Two constraints: the two
legs have the same R_O/R_I ratio, which is what makes the circuit subtract,
and that ratio is the gain, `a_d = 1`.

## What the simulation found

[`out/simulation.txt`](out/simulation.txt), from the decks under
[`out/spice/`](out/spice/):

| Run | Measured | Claimed |
| --- | ---: | ---: |
| `difference`, E1 = 1.5 V, E2 = 4 V: E_O | 2.5 V | 2.5 V, holds |
| `difference`: E_O / (E2 - E1) | 1 | 1 (`a_d`), holds |
| `common_mode`, E1 = E2 = 2 V: E_O | 0 V | 0 V ± 100 µV, holds |

## Running it

```bash
fang check examples/ti_opamp_handbook/differential_amplifiers/subtractor/subtractor.py
python examples/regenerate.py ti_opamp_handbook/differential_amplifiers/subtractor   # needs ngspice
```
