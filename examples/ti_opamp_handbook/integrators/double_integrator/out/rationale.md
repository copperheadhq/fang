# double_integrator: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.reading (`DEC-0c77f0d9ebef`)

**The drawn C_O (1 uF) and R_O (10 kOhm) break the page's rule C_O = C_I/2, R_O = R_I/2. Which values does the program hold?** → the drawn values, with a second run on a copy that has the rule's values (0.5 uF and 500 kOhm) to show the printed -4 double integral

- with the drawn values the low-frequency coefficient is 1/(2 R_I R_O C_O^2) = 50 per s^2, not 4
- with the rule's values the transfer is exactly -4/(p R_I C_I)^2
- Rejected change the parts to the rule's values: the figure is the source of truth for what is drawn; bending it hides the erratum
- Rejected only the drawn values: then the printed formula is never shown to hold anywhere

### system.op_amp (`DEC-cfa315e44293`)

**What open-loop gain stands in for the TLC265x?** → 140 dB (1e7), 20 dB above the handbook bench's default

- the figure names a chopper-stabilized part, whose open-loop gain is well above a general-purpose op amp's
- the double integrator has no DC feedback at all, so its low-frequency accuracy is the op amp's gain
- Rejected the default 120 dB: at 10 mHz the loop gain left is small enough that the measured coefficient comes out -50.6 rather than -50

## Calculations

### system.drawn_response (`CALC-c9d0d142ff72`)

`E_O/E_I = -(1 + 2 p C_O R_O) / (R_I (2 + p R_I C_I) p^2 C_O^2 R_O) = -100 (1 + 0.02 p) / (p^2 (2 + p)) with the drawn values`

Result: |E_O/E_I| = 120.84 at 0.1 Hz (phase -16.7 deg from 0) and 0.3872 at 1 Hz; the rule's -4/(p R_I C_I)^2 would give 10.13 and 0.1013

- Over `system.r_i2` (Resistor, `CMP-32235d428925`)
- Over `system.c_o2` (Capacitor, `CMP-73be26c5c0a8`)
- Over `system.r_o` (Resistor, `CMP-89c2061ba337`)
- Over `system.c_i` (Capacitor, `CMP-ade6de650003`)
- Over `system.r_i1` (Resistor, `CMP-b5831f705c5b`)
- Over `system.c_o1` (Capacitor, `CMP-e9818fd51d1c`)

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O = -4/(R_I C_I)^2 double integral E_I dt = -4 double integral E_I dt, where C_O = C_I/2, R_O = R_I/2. Integrates twice with one amplifier.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 58, Double Integrator.
