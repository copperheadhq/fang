# adjustable_lag: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.setting (`DEC-091f1d56fe0f`)

**Where is the wiper when the claims are held?** → D = 1/2, the page's own setting, where the lag is largest: 40 rad/s, 6.37 Hz

- the page prints -40/(40 + P), which is R C / 4 = 25 ms
- D - D^2 is symmetric, so which end D counts from does not matter
- Rejected D = 0.1: checked on the bench as a second point; the page prints its numbers at D = 1/2
- Rejected D at either end: D - D^2 is 0 there and the lag vanishes: the circuit is a plain inverter

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O = -E_I / (1 + (D - D^2) R C P) = -40 E_I / (40 + P); non-integrating type, constant inverting unity gain, maximum lag for R centered for D = 1/2

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 84, Adjustable Lag.
