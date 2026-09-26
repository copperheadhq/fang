# voltage_follower

SBOA092B page 49, *The Voltage Follower*: E_I on the non-inverting input, the
output wired straight back to the inverting input.

```
E_O = E_I
```

## What the program says

There are no resistors, so nothing is chosen. The whole output is fed back,
so the gain is 1, held as the parameter `a_v = 1`. The figure's lower pair of
terminals are drawn as two terminals on the grounded return.

## What the simulation found

[`out/simulation.txt`](out/simulation.txt), from the three decks under
[`out/spice/`](out/spice/):

| Run | Measured | Claimed |
| --- | ---: | ---: |
| `gain`, operating point, E_I = 1 V | 1 | 1 (`a_v`), holds |
| `large_signal`, operating point, E_I = 10 V | 1 | 1 (`a_v`), holds |
| `bandwidth`, gain at 1 kHz | 1 | 1 (`a_v`), holds |
| `bandwidth`, -3 dB point | 9.976 MHz | not a claim |

With 120 dB of open-loop gain the follower's gain is A / (1 + A), 1 less a
part in 10^6. Its noise gain is 1, so its bandwidth is the op amp's whole
10 MHz gain-bandwidth.

## Running it

```bash
fang check examples/ti_opamp_handbook/buffers/voltage_follower/voltage_follower.py
python examples/regenerate.py ti_opamp_handbook/buffers/voltage_follower   # needs ngspice
```
