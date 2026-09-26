# linear_current_source: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.load (`DEC-bf109e8b1fc8`)

**What is R_L?** → 100 Ohm

- the current falls short by R_L / R2, 0.1% at 100 Ohm
- at 10 mA per volt the load sits at 1 V, and the second output at 2 V
- Rejected 10 kOhm: the upper R2 would then take 10% of the current, where the formula assumes R_L << R2

### system.c_o_value (`DEC-dd20e58c53f9`)

**What is C_O?** → 100 pF, across the first amplifier's R0

- the figure draws C_O across R0 and gives no value
- 100 pF against 100 kOhm rolls the first stage off at 16 kHz, far above anything the d.c. runs ask of it
- Rejected leave it out: the page says it is there for stability; the d.c. claims do not depend on it, but the drawn circuit has it

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> When R_L << R2, I_L / E_I = R2 / (R1 R3) = 1 mA / Volt. C_O added for high frequency stability. Change R3 for current scaling: 1 kOhm, 1 mA / Volt; 100 Ohm, 10 mA / Volt; 10 Ohm, 100 mA / Volt.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 81, Linear Current Source, and Table 2.
