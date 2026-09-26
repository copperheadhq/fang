# presettable_voltage_source

SBOA092B page 52, *Presettable Voltage Source*: the cell Eref from the node
R_I and R_O share to the inverting input, R_O (a decade box) on to the
output, R_I to ground, and the non-inverting input on ground. The op amp is
a TLC265x.

```
E_O = (R_I + R_O) / R_I x Eref
```

## What the program says

The inverting input sits at ground, so the shared node stands at +Eref and
R_I carries Eref / R_I, all of it from the output through R_O. The figure
sizes R_I at 1000 x Eref ohms, which makes that current 1 mA whatever the
cell is: each ohm on the decade box is a millivolt of E_O above Eref. The
handbook does not say so; the program records it as a calculation (`scale`)
and a constraint (`i_set = 1 mA`).

Recorded choices: `cell`, a Weston cell at 1.0183 V, so R_I = 1018.3 Ω;
`dial`, R_O at 8981.7 Ω for E_O = 10.000 V; and `decade_box`, the decade box
modelled as a potentiometer with its wiper on its far end, so a run can turn
the dial. The op amp has a chopper's 1 µV offset.

## What the simulation found

[`out/simulation.txt`](out/simulation.txt):

| Run | R_O | Measured | Claimed |
| --- | ---: | ---: | ---: |
| `ten_volts`, E_O | 8981.7 Ω | 10.000 V | 10 V (`e_out`), holds |
| `ten_volts`, current in R_I | | 1 mA | 1 mA (`i_set`), holds |
| `ten_volts`, cell current | | 1e-17 A | 0 (`i_cell`) ± 1 nA, holds |
| `five_volts`, E_O | 3981.7 Ω | 5.000 V | 5 V, holds |
| `dial_at_zero`, E_O | 0 Ω | 1.0183 V | Eref, holds |

The outputs are held to 100 ppm: a noise gain near 10 costs 10 ppm of
loop-gain error and the offset another 1 ppm. The lowest output the circuit
gives is Eref itself.

## Running it

```bash
fang check examples/ti_opamp_handbook/references/presettable_voltage_source/presettable_voltage_source.py
python examples/regenerate.py ti_opamp_handbook/references/presettable_voltage_source   # needs ngspice
```
