# differential_input_output: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.load (`DEC-bf109e8b1fc8`)

**What load does the bench put across the outputs?** → 1 kOhm, across the two output terminals and nowhere near ground, in one run

- the figure draws no load
- the bench's outputs are ideal, so the load shows only that nothing needs a ground, not how a real part's outputs sag under it
- Rejected no load at all: the page's point is a floating load, and a run with one shows the difference does not need a ground to be measured
- Rejected a load from each output to ground: that is two grounded loads, not the floating one the page names

## Evidence

### system.gain_rule (`EVD-dde4bfda1441`)

> E_O = (R_O/R_I)(E2 - E1)

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 69, The Differential (Balanced) Output Amplifier.

### system.figure (`EVD-fe92fa0675d8`)

> For use in driving floating loads. Input may be floating source

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 75, Differential Input-Output.
