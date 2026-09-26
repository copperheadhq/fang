# full_wave_rectifier: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.reading (`DEC-0c77f0d9ebef`)

**Which way do the two diodes of the first stage point?** → both up the page, as drawn: the upper from the first op amp's output to the R_3/R_2 junction, the lower from R_5 to that output, which gives E_O = -|E_I|

- the page claims an absolute value and no sign; -|E_I| is one
- the precision, which is the page's point, is the same either way
- Rejected alternative: that gives +|E_I|, but the triangles on the page point up with the bar above them; the program does not redraw the figure to fit a sign the page never states

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> Precision absolute value circuit.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 89, Full Wave Rectifier.
