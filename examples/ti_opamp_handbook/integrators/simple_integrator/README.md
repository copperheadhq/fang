# simple_integrator

SBOA092B page 56, *Simple Integrators* (the first figure): E_I through R_I
(100 kΩ) into the summing point, C_O (1 µF) from the output back to it, and a
switch across C_O. "Close switch to reset to zero."

```
E_O = -1/(R_I C_O) ∫ E_I dt = -10 ∫ E_I dt
```

## What the program says

The claim is a parameter, `rate = -10 /s` (volts of output per second, per
volt of input), held to the parts by one constraint:

```python
require(equals(self.rate, negative(over(1 * ratio, product(self.r_in.resistance, self.c_out.capacitance)))))
```

The figure gives no drive and no timing for the switch, so the program records
the bench as a decision (`bench`): the switch is closed at t = 0 and opens at
10 ms, with a steady 0.1 V already on E_I. That makes a ramp of -1 V/s, which
stays inside the swing for the whole run.

## What the simulation found

[`out/simulation.txt`](out/simulation.txt), from the deck under [`out/spice/`](out/spice/):

| Run | Measured | Claimed |
| --- | ---: | ---: |
| `ramp`, output with the switch closed | -1 µV | 0 V ± 1 mV, holds |
| `ramp`, slope from 0.1 s to 1.1 s over E_I | -10 /s | -10 /s (`rate`), holds |

While the switch is closed the 1 Ω across C_O holds the output at zero even
with the input applied. Once it opens the output falls 1 V/s for 0.1 V in.

## Running it

```bash
fang check examples/ti_opamp_handbook/integrators/simple_integrator/simple_integrator.py
python examples/regenerate.py ti_opamp_handbook/integrators/simple_integrator   # needs ngspice
```
