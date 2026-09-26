# differential_input_amplifier: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.values (`DEC-f7c4162de03e`)

**What are R1, R_O, R2 and R3?** → R1 = R2 = 10 kOhm and R_O = R3 = 100 kOhm, a differential gain of 10

- the figure names the resistors and gives no values
- R2 = R1 and R3 = R_O is the condition the page reduces the formula under
- Rejected four unrelated values, to exercise the general formula: the page's point is the matched case, where the output is the difference alone; unmatched values pass part of the common-mode voltage
- Rejected leave them unknown: a gain nobody can compute is not a claim anything can check

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O = (R3/R1)((R1 + R_O)/(R2 + R3)) E2 - (R_O/R1) E1; for R2 = R1 and R3 = R_O, E_O = (R_O/R1)(E2 - E1)

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 67, The Differential Input Amplifier.
