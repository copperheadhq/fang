# simple_oscillator: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.trim (`DEC-2becb3c534eb`)

**Where is R/2 set?** → a 10 kOhm rheostat at 0.49 of its travel: 4.9 kOhm, 2% below R/2

- the page says to trim R/2 until the oscillation is barely sustained; below R/2 is the side that sustains it
- a 10 kOhm pot is R, so its mid-travel is R/2 and 0.49 is just below
- Rejected exactly R/2: a balanced twin-T passes nothing at f, so nothing comes back to sustain an oscillation
- Rejected R/2 set high: the transmission at f is then positive, the feedback negative, and the circuit is still
- Rejected 0.499 of the travel, nearer barely sustained: the growth is then so slow that a run long enough to see it settle is mostly waiting; 2% low moves f by 0.5%

### system.values (`DEC-f7c4162de03e`)

**What are R and C?** → 10 kOhm and 15.9 nF, so 1 / (2 pi R C) is 1.001 kHz; 2C is 31.8 nF

- the figure names R, C and 2C and gives no values
- 1 kHz is a round frequency and 10 kOhm keeps the network well above the op amp's output resistance
- Rejected leave them symbolic: a frequency nobody can compute is not a claim a run can check

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> f = 1 / (2 pi R C). Double integrator circuit with regenerative feedback. Components R, C, and 2C should be very low tolerance. Trim R/2 until oscillation is barely sustained.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 83, Simple Oscillator.
