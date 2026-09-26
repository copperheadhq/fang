# time_delay

SBOA092B page 86, *Time Delay*: an inverting stage built to approximate a pure
delay. The input is a ladder, R/6, 3.6C to ground, 2R/3, 3.6C to ground, R/6;
the feedback is R beside a T of 0.8C, 0.8C with R/4 to ground. The page prints
no formula, only "Unity gain phase or time shift" and a sketch: the step comes
out inverted after RC and completes its edge over 1.1 RC.

## What the program says

The figure gives only symbols, so the program chooses R = 60 kΩ and C = 10 nF
(`values`), RC = 600 µs, which makes R/6, 2R/3 and R/4 10k, 40k and 15k. Each
part is held to its fraction of the parameters `r` and `c`. At DC the three
input resistors add to R, so `a_v = -1`: it inverts, as the sketch draws. The
delay claims are `rc` for the 50% point and `rise = 1.1 RC` for the 10% to 90%
time, each held to 5% because the page gives a sketch, not a formula.

## What the simulation found

[`out/simulation.txt`](out/simulation.txt), a 1 V step at t = 0:

| Run | Measured | Claimed |
| --- | ---: | ---: |
| `dc_gain` | -1 | -1 (`a_v`), holds |
| `step`, 50% point | 589 µs (0.98 RC) | 600 µs (`rc`), holds |
| `step`, 10% to 90% | 671 µs (1.12 RC) | 660 µs (`rise`), holds |
| `step`, settled | -1 V | -1 V, holds |
| `step`, 10% point | 275 µs | not a claim |
| `step`, overshoot | -1.022 V | not a claim |

The sketch draws the output flat until RC. The simulated edge is smoother:
already 10% of the way at 0.46 RC, centered on RC, and it overshoots by 2%.

## Running it

```bash
fang check examples/ti_opamp_handbook/lead_lag/time_delay/time_delay.py
python examples/regenerate.py ti_opamp_handbook/lead_lag/time_delay   # needs ngspice
```
