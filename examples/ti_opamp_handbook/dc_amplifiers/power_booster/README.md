# power_booster

SBOA092B pages 71 and 72, *Power Booster*: a compound amplifier. A precision
OPA277 runs the outer loop at G = 1 + 20k/1k = +21; a power OPA512 inside it
runs a local loop at 1 + 10k/4.7k = 3.13 (10 pF across its 10 kΩ); two
0.1 Ω in parallel sit between the OPA512 and E_O, inside both loops; 47 pF
from the OPA277's output to its - input adds phase lead for stability.
E_I is on the OPA277's + input with 100 kΩ to ground.

```
G = +21
Table 1, compound: V_OS 20 µV, V_OUT ±35 V, I_OUT 10 A, SR 2.4 V/µs
```

## What the program says

`models` gives each op amp its column of Table 1: the OPA277 swings ±13 V
with 20 µV of offset, the OPA512 ±35 V with 6 mV. The table gives no
bandwidth, so the gain-bandwidths are the parts' data-sheet figures, 1 MHz
and 4 MHz. The macro-model has no slew rate or current limit, so those rows
are recorded and not simulated. `load` adds the 10 Ω the figure does not
draw. The constraints hold G = 21 and the local 3.13 to the resistors; say
that 30 V out needs 1.4286 V in, is beyond the OPA277's own +13 V and inside
the OPA512's +35 V, while the OPA277 itself supplies only E_O / 3.13 = 9.6 V;
and put the compound's output offset at 21 times the OPA277's.

## What the simulation found

[`out/simulation.txt`](out/simulation.txt), from the decks under
[`out/spice/`](out/spice/):

| Run | Measured | Claimed |
| --- | ---: | ---: |
| `thirty_volts`, gain, E_I = 1.4286 V into 10 Ω | 21 | 21 (`g`), holds |
| `thirty_volts`, E_O | 30 V (3 A) | 30 V (`e_out`), holds |
| `thirty_volts`, OPA277 output | 9.598 V | 9.6 V (`e_front`), holds |
| `thirty_volts`, OPA512 output | 30.15 V | not a claim |
| `offset`, E_O with E_I = 0 | -420.1 µV | -420 µV (`v_os_out`), holds |
| `stability`, gain at 100 Hz | 26.44 dB | 20 log 21, holds |
| `stability`, peak above the DC gain | 0 dB | at most 1 dB, holds |
| `stability`, -3 dB point | 139 kHz | not a claim |
| `step`, 0.1 V step, final value | 2.1 V | 2.1 V, holds |
| `step`, overshoot | 0 | under 5%, holds |

The OPA277 swings 9.6 V while the load gets 30 V and 3 A, and the output
offset is the OPA277's 20 µV times 21 (negative here only because the model
subtracts its offset from the + input); the OPA512's 6 mV shows up at the
OPA277's output, not at E_O. With single-pole models at 1 MHz and 4 MHz the
two loops do not peak and the step does not overshoot: the response is
monotonic, rolling off at 139 kHz. That is a statement about these models;
a real OPA512's extra poles and its slew rate are not in them.

## Running it

```bash
fang check examples/ti_opamp_handbook/dc_amplifiers/power_booster/power_booster.py
python examples/regenerate.py ti_opamp_handbook/dc_amplifiers/power_booster   # needs ngspice
```
