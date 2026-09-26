# simple_non_inverting

SBOA092B page 71, *Simple Non-Inverting*: E_I on the + input, R_O 90 kΩ from
the output to the - input and R_I 10 kΩ from there to ground.

```
E_O = (R_O + R_I) / R_I x E_I = 10 E_I
```

## What the program says

The figure gives both values, so nothing is chosen. The claim is a parameter,
`a_v = 10`, held to the parts by one constraint:

```python
require(equals(self.a_v, over(total(self.r_out.resistance, self.r_in.resistance), self.r_in.resistance)))
```

## What the simulation found

[`out/simulation.txt`](out/simulation.txt), from the decks under
[`out/spice/`](out/spice/):

| Run | Measured | Claimed |
| --- | ---: | ---: |
| `gain`, operating point, E_I = 1 V | 10 | 10 (`a_v`), holds |
| `gain`, the - input | 1 V | 1 V, holds |
| `swing`, E_O at E_I = 1 V in a sweep | 10 V | 10 (`a_v`), holds |
| `swing`, highest E_O | 13.51 V | 13.5 V, holds |
| `swing`, lowest E_O | -13.51 V | -13.5 V, holds |

Both inputs sit at E_I, which is why the page warns about the common-mode
limit. The bench's op amp has no such limit, so the sweep shows the limit it
does have: the output stops at its ±13.5 V swing once E_I passes 1.35 V.

## Running it

```bash
fang check examples/ti_opamp_handbook/dc_amplifiers/simple_non_inverting/simple_non_inverting.py
python examples/regenerate.py ti_opamp_handbook/dc_amplifiers/simple_non_inverting   # needs ngspice
```
