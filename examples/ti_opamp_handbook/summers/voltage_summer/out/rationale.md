# voltage_summer: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.values (`DEC-f7c4162de03e`)

**What are R1, R2, R3 and R_O?** → R1 10 kOhm, R2 20 kOhm, R3 50 kOhm, R_O 100 kOhm: weights -10, -5, -2

- the figure names the resistors and gives no values
- three different weights, so an input wired to the wrong resistor fails
- standard values, and weights that keep E_O inside the swing for inputs under a volt
- Rejected all four equal: that is the adder on the next page, and equal weights cannot show that each input gets its own
- Rejected leave them unknown: a weight nobody can compute is not a claim anything can check

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O = -R_O (E1/R1 + E2/R2 + E3/R3 + ...). Thus, each input, E_n, is multiplied by a factor, -R_O/R_n, before summing

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 63, The Voltage Summer.
