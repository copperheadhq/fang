# differential_output: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.reading (`DEC-0c77f0d9ebef`)

**Which side of the circuit floats?** → the input: E_I is applied between the two left-hand terminals, and E_O is taken from the output to ground

- the lower left terminal goes to the + input through R_I, not to ground
- the drawing is the source of truth; the caption does not match it
- Rejected alternative: the figure has one op amp with one output, and the lower right terminal is on the ground symbol; there is no second output for a floating load to sit between

### system.polarity (`DEC-938a67ac3fca`)

**Which input terminal is E_I positive at?** → the bottom one, which reaches the + input, so E_O = +10 E_I as printed

- the figure marks no polarity
- Rejected the top one: E_O would be -10 E_I, and the page prints a positive gain

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O = R_O / R_I E_I = 10 E_I. For driving floating load.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 73, Differential Output.
