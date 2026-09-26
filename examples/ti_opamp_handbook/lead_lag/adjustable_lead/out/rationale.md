# adjustable_lead: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.setting (`DEC-091f1d56fe0f`)

**Where is the wiper when the claims are held?** → D = 1/2, where D - D^2 is largest: a zero at 40 rad/s, 6.37 Hz

- the page gives no setting for the lead; the lag beside it is quoted at D = 1/2
- at the center the zero sits lowest, so the lead is widest
- Rejected D = 0.1: less lead, the zero at 111 rad/s; the page's companion lag is quoted at D = 1/2

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O = -[(D - D^2) R C P] E_I; putting input network from adjustable lag circuit in feedback path gives lead element

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 85, Adjustable Lead.
