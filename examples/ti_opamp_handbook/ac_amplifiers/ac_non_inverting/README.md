# ac_non_inverting

SBOA092B page 77, *Non-Inverting*: E_I through C_2 1 µF onto the + input,
R_2 100 kΩ from there to ground; R_0 90 kΩ from the output to the - input,
and R_1 10 kΩ in series with C_1 100 µF from there to ground.

```
E_O = (R_O + R_I) / R_I x E_I = 10 E_I
f_-3dB = 1 / (2 pi R_I C_I) = 0.16 Hz
```

## What the program says

The gain is 1 + 90k/10k = 10 (`a_v`). There are two low-frequency corners.
`f_gain` is the printed one, within 1% of 1/(2 pi R_1 C_1) = 0.159 Hz: the
gain network's, below which the gain falls toward 1. `f_input` is the input
network's, 1/(2 pi R_2 C_2) = 1.59 Hz, and a constraint says it is at least
five times higher. `f_low`, where the whole circuit is 3 dB down, is set
equal to `f_input`.

## What the simulation found

[`out/simulation.txt`](out/simulation.txt):

| Run | Measured | Claimed |
| --- | ---: | ---: |
| `response`, gain at 1 kHz | 10 | 10 (`a_v`), holds |
| `response`, phase at 1 kHz | 0.0007 rad | 0, holds |
| `response`, circuit -3 dB point | 1.608 Hz | 1.6 Hz (`f_low`) ±1%, holds |
| `response`, E_O / E_+ at 0.159 Hz | 7.106 | 7.106, holds |
| `response`, E_+ at 1.59 Hz | 0.707 V | 0.7071 V, holds |
| `dc`, E_O with E_I = 1 V d.c. | 0 V | 0 V, holds |

At 0.159 Hz the gain network is 3 dB down from 10, which is the corner the
page prints, but by then C_2 and R_2 have already cut E_I by 20 dB. The
source sees the input network's 1.59 Hz corner first.

## Where the handbook is off

The printed f_-3dB = 0.16 Hz is the gain network's corner (and the formula
names R_I and C_I where the figure has R_1 and C_1). The drawn circuit is
3 dB down at 1.6 Hz, set by C_2 R_2, ten times higher. To make 0.16 Hz the
circuit's corner, C_2 would need to be 10 µF or R_2 1 MΩ.

## Running it

```bash
fang check examples/ti_opamp_handbook/ac_amplifiers/ac_non_inverting/ac_non_inverting.py
python examples/regenerate.py ti_opamp_handbook/ac_amplifiers/ac_non_inverting   # needs ngspice
```
