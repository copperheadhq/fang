# time_delay: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.values (`DEC-f7c4162de03e`)

**What are R and C?** → R = 60 kOhm and C = 10 nF, RC = 600 us

- the figure gives every part as a multiple of R or C and no values
- 60 kOhm makes R/6, 2R/3 and R/4 10k, 40k and 15k
- Rejected R = 10 kOhm: R/6 and 2R/3 would be 1.667 k and 6.667 k, values nobody stocks
- Rejected leave them symbolic: a delay nobody can compute is not a claim anything can check

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> Unity gain phase or time shift; E_O follows the E_I step, delayed by RC, rising over 1.1 RC

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 86, Time Delay.
