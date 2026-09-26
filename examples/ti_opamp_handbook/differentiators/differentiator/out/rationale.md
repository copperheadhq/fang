# differentiator: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.values (`DEC-f7c4162de03e`)

**What are C_I and R_O?** → 0.1 uF and 100 kOhm, a 10 ms time constant

- the figure names C_I and R_O and gives no values
- the same page's differentiator with stop uses 0.1 uF and 100 kOhm
- Figure 43 draws X_C = R_O near 16 Hz, which 1/(2 pi 100k 0.1u) is
- Rejected leave them unknown: a derivative with no time constant is not a claim anything can check
- Rejected a shorter time constant, such as 0.1 uF and 10 kOhm: it moves the peak up to 40 kHz and does not change what the figure shows

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O = -R_O C_I dE_I/dt. The ideal differentiator circuit is not generally usable in its simple form

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 61, Differentiators.
