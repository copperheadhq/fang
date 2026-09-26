# full_wave_rectifier

SBOA092B page 89, *Full Wave Rectifier*: a precision half-wave rectifier (R_4,
R_3, R_5, all 1 kΩ, and two diodes) followed by a summer that adds E_I through
R_1 (2 kΩ) and the half-wave through R_2 (1 kΩ) into R_O (2 kΩ). The page
prints no formula, only "Precision absolute value circuit."

## What the program says

The half-wave counts twice as much as E_I at the summer, which is what turns a
half-wave into an absolute value. Its sign depends on the diodes. As drawn
(`reading`), both point up the page, so a negative E_I gives a half-wave of
+|E_I| and a positive E_I gives zero, and

```
E_O = -E_I              for E_I > 0
E_O = -E_I - 2|E_I| = E_I   for E_I < 0
```

which is E_O = -|E_I|. Two parameters hold the two slopes to the parts:
`a_positive = -R_O/R_1 = -1` and `a_negative = -R_O/R_1 + R_O R_3 / (R_2 R_4) = 1`.

## What the simulation found

[`out/simulation.txt`](out/simulation.txt):

| Run | Measured | Claimed |
| --- | ---: | ---: |
| `transfer`, slope for E_I > 0 | -1 | -1 (`a_positive`), holds |
| `transfer`, slope for E_I < 0 | 1 | 1 (`a_negative`), holds |
| `transfer`, E_O at E_I = +10 mV | -9.998 mV | -10 mV ± 0.1 mV, holds |
| `transfer`, E_O at E_I = -10 mV | -9.993 mV | -10 mV ± 0.1 mV, holds |
| `sine`, lowest E_O, 1 V peak in | -1 V | -1 V, holds |
| `sine`, average E_O | -636.6 mV | -2/π V, holds |

Ten millivolts in comes out within 7 µV of ten millivolts: no diode drop shows,
which is the point of the circuit against the simple absolute value one.

## Where the handbook is off

Not off, but not what a reader expects: the drawn diodes give -|E_I|, not
+|E_I|. Turned round, both give the positive absolute value. The program keeps
the figure and says which sign it gives.

## Running it

```bash
fang check examples/ti_opamp_handbook/additional/full_wave_rectifier/full_wave_rectifier.py
python examples/regenerate.py ti_opamp_handbook/additional/full_wave_rectifier   # needs ngspice
```
