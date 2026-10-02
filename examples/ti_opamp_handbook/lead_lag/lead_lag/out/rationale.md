# lead_lag: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.settings (`DEC-f4acfbdfa71a`)

**Where are the two wipers when the claims are held?** → D1 = 1/2 in the feedback (zero at 40 rad/s, 6.37 Hz) and D2 = 0.1 at the input (pole at 111 rad/s, 17.7 Hz): a lead of up to 28 degrees

- the page gives no settings
- distinct zero and pole make the composite shape visible on the bench
- Rejected both at 1/2: the zero and the pole cancel and the stage is a plain inverter: nothing to see
- Rejected D1 = 0.1 and D2 = 1/2: a lag instead of a lead; equally valid, and the lag has its own page

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O = (1 + (D1 - D1^2) R C1 P) / (1 + (D2 - D2^2) R C2 P); composite lead and lag network

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 86, Lead-Lag.
