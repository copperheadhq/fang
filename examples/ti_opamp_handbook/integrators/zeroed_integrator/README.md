# zeroed_integrator

SBOA092B page 56, *Simple Integrators* (the second figure). This is the
integrator above it, R1 100 kΩ into the summing point with C_O and a reset
switch, plus a trimmed current into the summing point. The + and - terminals
feed the ends of the pot R3 through R2 and R4 (10 kΩ each), and the wiper
reaches the summing point through R5 (10 MΩ). "With zero input and switch
open, set R3 for zero output drift."

## What the program says

The figure leaves four things open, and the program records each one as a
decision:

- `c_o_reading`: C_O is printed "1 mF" and is read as 1 µF. Every other
  integrator on these pages pairs 100 kΩ with 1 µF.
  -1/(R1 C_O) is -10 /s with 1 µF and -0.01 /s with 1 mF (`either_reading`).
- `network`: R3 is 10 kΩ, and + and - are the ±15 V rails, so the wiper spans
  -5 V to +5 V.
- `error`: the op amp model has no bias-current term, so it is given a 1 mV
  input offset instead. Across R1 that is 10 nA into C_O, the same current
  offset the handbook describes.

The constraints solve for the null. The wiper has to sit at
-Vos (1 + R5/R1) = -101 mV (`v_wiper_null`), and on the R2-R3-R4 chain that
is a setting of 0.5101. The program sets R3 there, and `drift_centred`
(-10.1 mV/s) is the drift with the wiper at its centre.

## What the simulation found

[`out/simulation.txt`](out/simulation.txt), from the decks under [`out/spice/`](out/spice/).
Zero input, reset switch open from 10 ms:

| Run | R3 setting | Wiper | Drift | Claimed |
| --- | ---: | ---: | ---: | ---: |
| `centred` | 0.5 | 0 V | -10.1 mV/s | -10.1 mV/s (`drift_centred`), holds |
| `nulled` | 0.5101 | -100.9 mV | -7.5 µV/s | 0 ± 0.1 mV/s, holds |
| `past_null` | 0.55 | -0.5 V | +39.9 mV/s | +39.9 mV/s, holds |
| `short_of_null` | 0.45 | +0.5 V | -60.1 mV/s | -60.1 mV/s, holds |
| `rate` (E_I = 0.1 V, nulled) | 0.5101 | | -10 /s per volt | -10 /s (`rate`), holds |

The pot can send current of either sign into the summing point, and at the
solved setting the drift is 0.07% of what it is with the wiper centred.

## Where the handbook is off

The figure prints C_O as "1 mF". Taken literally, the integrator would run at
-0.01 V/s per volt rather than the -10 of the figure above it. The program
simulates 1 µF and says so.

## Running it

```bash
fang check examples/ti_opamp_handbook/integrators/zeroed_integrator/zeroed_integrator.py
python examples/regenerate.py ti_opamp_handbook/integrators/zeroed_integrator   # needs ngspice
```
