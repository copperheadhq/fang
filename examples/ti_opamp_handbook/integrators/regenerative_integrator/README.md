# regenerative_integrator

SBOA092B page 57, the integrator page 56 introduces with "Regeneration may be
used to increase open loop DC gain to infinity". There is no formula, only a
four-step procedure for trimming the zero control R8 and the regeneration
control R5.

## What the program says

The program's reading of the drawing is recorded as a decision (`reading`):

- the integrator: E_I through R1 (100 kΩ) to the - input, C_O (1 µF) with a
  reset switch to the output;
- the zero control: R9 and R10 (10 kΩ) from the + and - terminals (read as
  ±15 V) to the ends of R8 (10 kΩ). The wiper feeds R6 (1 MΩ) to the - input
  and R7 (1 MΩ) to the + input;
- the regeneration: R3 (10 MΩ) from the output to a node X, R2 (100 kΩ) from
  X to the + input, and R4 (1 kΩ) plus the rheostat R5 (2 kΩ) from X to
  ground.

That is positive feedback of a fraction k ≈ (R4 + R5)/R3 × R7/(R2 + R7) of the
output. With the input open, the - input sits at E_O (k - 1/A), and R6 leaks
C_O's charge away with a time constant near R6 C_O / (1/A - k). Regeneration
makes that longer until k reaches 1/A. Past that point the output grows,
which is the handbook's step 3.

k runs from 0.9e-4 to 2.7e-4 over R5's travel, so the network suits an op
amp with a gain of 4000 to 11000. With the bench's default of 1e6 the output
would run away at every setting. The program gives the op amp a gain of 5000
(`op_amp`), which puts the balance at 60% of R5's travel, near the centre the
procedure starts from. R8 is centred and R5 is at a quarter (`settings`).

The claims: `rate = -10 /s`, `hold_open = A R6 C_O = 5000 s` with no
regeneration, and `hold_quarter = 15,710 s` with R5 at a quarter.

## What the simulation found

[`out/simulation.txt`](out/simulation.txt), from the decks under [`out/spice/`](out/spice/).
The hold runs follow step 2: 1 V through a switch the bench adds takes the
output to about -5 V, the input is opened at 0.51 s, and the output is read
100 s apart.

| Run | Measured | Claimed |
| --- | ---: | ---: |
| `rate`, slope over E_I | -9.995 /s | -10 /s (`rate`) ± 0.1%, holds |
| `hold_without_regeneration`, node X grounded by a card | 5015 s | 5000 s (`hold_open`) ± 3%, holds |
| `hold_with_regeneration`, R5 at 25% | 15,350 s | 15,710 s (`hold_quarter`) ± 3%, holds |
| `too_much_regeneration`, R5 at 100% | -14,530 s (grows) | not a claim |

Regeneration triples the hold. Turned too far, it makes the output grow
instead of decay. The 3% tolerance covers what the estimate leaves out: the
zero control's 7.5 kΩ source resistance and R7's path to the + input. The
program does not claim an infinite hold. Getting one needs an exact balance,
and that is not a number anyone can claim.

## Running it

```bash
fang check examples/ti_opamp_handbook/integrators/regenerative_integrator/regenerative_integrator.py
python examples/regenerate.py ti_opamp_handbook/integrators/regenerative_integrator   # needs ngspice
```
