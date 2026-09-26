# balanced_output_amplifier: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.values (`DEC-f7c4162de03e`)

**What are R_I and R_O?** → 10 kOhm and 100 kOhm in both legs, a differential gain of 10

- the figure names the resistors and gives no values
- a gain of 10 keeps each output far inside the swing for the drives used
- Rejected leave them unknown: a gain nobody can compute is not a claim anything can check
- Rejected different pairs in the two legs: the page's subtraction of the two leg equations needs the same R_I and R_O in both; the figure labels them alike

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O = (R_O/R_I)(E2 - E1). Note that the values of E_f and E_P are not uniquely determined by the above equations

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 69, The Differential (Balanced) Output Amplifier.
