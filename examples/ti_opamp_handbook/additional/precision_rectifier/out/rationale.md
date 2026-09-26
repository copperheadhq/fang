# precision_rectifier: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.reading (`DEC-0c77f0d9ebef`)

**Which way do the two diodes point?** → both point up the page: the upper from the op amp output to the E_O node, the lower from the lower R_O to the op amp output

- under this reading only one path conducts at a time, which is what makes the other half of the output zero
- E_O is a positive hump, -5 times the negative half of E_I, as the sketch under the figure draws it
- Rejected alternative: the triangles point up with the bar above them; reversed, E_O would be a negative hump for a positive E_I, not the positive hump the page sketches

### system.bench (`DEC-c5e3bfe8b131`)

**What drives E_I?** → a DC sweep from -2 V to 2 V, and a 1 V peak, 1 kHz sine

- the sweep gives the two slopes exactly; the sine shows the half-wave
- Rejected a 2 V peak sine: 5 x 2 V is 10 V, near enough the swing to muddy the peak

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O peak = -(R_O/R_I) E_I peak = -5 E_I peak. Half wave with amplification if desired. Placing rectifiers in feedback loop decreases non-linearity to very small value.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 88, Precision Rectifier.
