# double_integrator

SBOA092B page 58, *Double Integrator*: two T networks and one op amp (a
TLC265x). The input T is R_I, R_I (1 MΩ each) with C_I (1 µF) from their
junction to ground. The feedback T is C_O, C_O (1 µF each) with R_O (10 kΩ)
from their junction to ground.

```
E_O = -4/(R_I C_I)² ∬ E_I dt = -4 ∬ E_I dt,   where C_O = C_I/2, R_O = R_I/2
```

## What the program says

Working the two tees as transfer admittances gives

```
E_O/E_I = -(1 + 2p C_O R_O) / (R_I (2 + p R_I C_I) p² C_O² R_O)
```

With the page's rule the two first-order factors cancel and the transfer is
exactly -4/(p R_I C_I)². The drawn values do not follow the rule, though
(1 µF and 10 kΩ where it asks for 0.5 µF and 500 kΩ). The program keeps the
drawn values (`reading`) and claims what they give:
`k_drawn = -1/(2 R_I R_O C_O²) = -50 /s²` at low frequency. It holds the
rule's values as parameters (`c_o_rule`, `r_o_rule`) and the printed
coefficient as `k_rule = -4 /s²`.

The rule's circuit is simulated as a copy written in raw cards beside the
drawn one. The bench can override parameters only on the parts it writes
itself, and fang writes the resistors and capacitors. The op amp gets 140 dB
of open-loop gain (`op_amp`). The circuit has no DC feedback, and at 120 dB
the low-frequency coefficient comes out 1.2% high.

## What the simulation found

[`out/simulation.txt`](out/simulation.txt), from the decks under [`out/spice/`](out/spice/):

| Run | Measured | Claimed |
| --- | ---: | ---: |
| `drawn`, -\|E_O/E_I\| (2π f)² at 10 mHz | -50.04 /s² | -50 /s² (`k_drawn`), holds |
| `drawn`, gain at 0.1 Hz | 120.8 | 120.84, holds (the rule would give 10.13) |
| `drawn`, gain at 1 Hz | 0.3872 | 0.38717, holds (the rule would give 0.1013) |
| `rule`, -\|E_O/E_I\| (2π f)² at 0.1 Hz and 1 Hz | -4 /s² | -4 /s² (`k_rule`), holds |
| `rule`, phase at 1 Hz | 0 rad | 0, holds |
| `rule_step`, 0.1 V step, E_O at 2 s over (0.1 × 2²/2) | -4 /s² | -4 /s² (`k_rule`), holds |

## Where the handbook is off

The drawn C_O (1 µF) and R_O (10 kΩ) do not satisfy the page's own
C_O = C_I/2, R_O = R_I/2. As drawn, the circuit double-integrates at low
frequency with a coefficient of 50, not 4. Above 0.3 Hz the input T's pole
adds a third integration. The printed -4 ∬ E_I dt holds with C_O = 0.5 µF and
R_O = 500 kΩ.

## Running it

```bash
fang check examples/ti_opamp_handbook/integrators/double_integrator/double_integrator.py
python examples/regenerate.py ti_opamp_handbook/integrators/double_integrator   # needs ngspice
```
