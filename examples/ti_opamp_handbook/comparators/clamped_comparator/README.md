# clamped_comparator

SBOA092B page 47, Figure 54, *Fully Clamped Voltage Comparator*: E_I through
R_1 (100 kΩ) and a -15 V reference through R_2 (1 MΩ) into the inverting
input; CR_1 (1N4148) from there to the tap of R_a/R_b (15 kΩ / 10 kΩ, from
+15 V to the output); CR_2 from the tap of R_b'/R_a' (3 kΩ / 15 kΩ, from the
output to -15 V) back to it.

```
Threshold = -(R_2 / R_1) V_ref = 1.5 V            (as printed)
Negative clamping level = -(+V_sup) R_b / R_a = -10 V
Positive clamping level = -(-V_sup) R_b' / R_a' = +3 V
```

## What the program says

The printed numbers are parameters tied to the drawn parts: `threshold`
(1.5 V, from -(R_1 / R_2) V_ref), `clamp_low_ideal` (-10 V) and
`clamp_high_ideal` (+3 V). Those two assume the tap sits at ground when the
diode conducts. It actually sits one diode drop past the summing point, and
the diode's current (15 µA at the two test inputs, 3 V and 0 V) also flows
in the divider:

```
E_O low  = -(R_b / R_a)(V_sup + V_D) - V_D - R_b I_D     = -10.807 V
E_O high = +(R_b' / R_a')(V_sup + V_D) + V_D + R_b' I_D  = +3.518 V
```

The drop is the one choice the program makes (`diode_drop`): 0.394 V, a
1N4148 model at 15 µA. `clamp_low` and `clamp_high` hold the two levels. The
three rails are cells.

## What the simulation found

[`out/simulation.txt`](out/simulation.txt):

| Run | Measured | Claimed |
| --- | ---: | ---: |
| `above_threshold` (E_I = 3 V), CR_1 drop | 0.394 V | 0.394 V (`v_diode`), holds |
| `above_threshold`, E_O | -10.81 V | -10.807 V (`clamp_low`), holds |
| `below_threshold` (E_I = 0 V), CR_2 drop | 0.394 V | 0.394 V (`v_diode`), holds |
| `below_threshold`, E_O | 3.518 V | 3.518 V (`clamp_high`), holds |
| `transfer`, E_I where E_O crosses mid-swing | 1.500 V | 1.5 V (`threshold`), holds |
| `figure_waveform` (2 V peak, 1 kHz), max E_O | 3.624 V | 3.624 V, holds |
| `figure_waveform`, min E_O | -10.62 V | -10.62 V, holds |

In the transient the clamps move with the diode current: at the -2 V trough
CR_2 carries 35 µA, at the +2 V crest CR_1 only 5 µA, and the same formula
gives both numbers. The figure's own trace sits near +3.7 V and -10.7 V.

## Where the handbook is off

- **The threshold formula is upside down.** -(R_2 / R_1) V_ref is
  -(10)(-15 V) = 150 V. The threshold, where E_I / R_1 cancels
  V_ref / R_2, is -(R_1 / R_2) V_ref = 1.5 V, which is the number printed.
- **The clamp levels leave out the diodes.** ngspice clamps at -10.81 V and
  +3.52 V (at 15 µA of diode current), not -10 V and +3 V. The negative
  clamp moves 1.67 V per volt of diode drop and the positive 1.2 V per volt.
  The page's own waveform agrees with the simulation, not the formulas.

## Running it

```bash
fang check examples/ti_opamp_handbook/comparators/clamped_comparator/clamped_comparator.py
python examples/regenerate.py ti_opamp_handbook/comparators/clamped_comparator   # needs ngspice
```
