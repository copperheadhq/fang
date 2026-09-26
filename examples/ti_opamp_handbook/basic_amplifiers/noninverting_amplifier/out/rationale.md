# noninverting_amplifier: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.values (`DEC-f7c4162de03e`)

**What are R_I and R_O?** → 10 kOhm and 90 kOhm, for a gain of +10

- the figure names the resistors and gives no values
- a decade of gain keeps E_O far inside the swing for a 1 V drive
- Rejected 10 kOhm and 100 kOhm, as in the inverting example: gives 11, a gain nobody reads off at a glance
- Rejected leave them unknown: a gain nobody can compute is not a claim anything can check

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O / E_I = (R_O + R_I) / R_I = 1 + R_O / R_I

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 53, The Non-Inverting Amplifier.
