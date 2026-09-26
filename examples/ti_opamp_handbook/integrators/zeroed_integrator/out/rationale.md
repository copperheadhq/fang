# zeroed_integrator: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.error (`DEC-90d9ab5ef657`)

**What error does the pot cancel?** → a 1 mV input offset on the op amp

- with E_I at zero, 1 mV across R1 is 10 nA into C_O, which is the "current offset stored in the feedback capacitor" the handbook describes
- Rejected an input bias current: the op amp model has no bias-current term to set

### system.c_o_reading (`DEC-92b06de1c06f`)

**C_O is printed "1 mF". Is that 1 millifarad?** → 1 uF, a misprint: the simulation uses 1 uF

- the same page's first figure is R_I 100 kOhm and C_O 1 uF for -10 integral E_I dt
- older schematics wrote mF and mfd for microfarads, and the label reads like one of those
- Rejected 1 mF as printed: every other integrator on pages 56 to 59 pairs 100 kOhm with 1 uF, and a 1 mF film or polystyrene integrating capacitor is not a part anyone would reset through a switch

### system.network (`DEC-faafc327fa6d`)

**What are R3, and the + and - terminals?** → R3 is 10 kOhm; + and - are the +/-15 V supply rails

- with 10 kOhm the chain R2, R3, R4 is 30 kOhm across 30 V, and the wiper spans -5 V to +5 V: up to 0.5 uA either way through R5, fifty times the error it has to cancel
- the page 57 zero control uses a 10 kOhm pot between 10 kOhm resistors, the same shape
- Rejected a separate reference pair: the figure draws only terminals, and a zero control is fed from the rails

## Calculations

### system.either_reading (`CALC-e81dfa0ca9d3`)

`-1/(R1 C_O)`

Result: -10 per second with 1 uF, as simulated; -0.01 per second with 1 mF as printed

- Over `system.r1` (Resistor, `CMP-390a79be1fe2`)
- Over `system.c_o` (Capacitor, `CMP-cffe260ed560`)

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> This circuit reduces current offset in operational amplifiers without "Balance" controls. With zero input and switch open, set R3 for zero output drift. (R1 100 kOhm, C_O 1 mF, R2 and R4 10 kOhm, R3 POT, R5 10 MOhm)

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 56, Simple Integrators (second figure).
