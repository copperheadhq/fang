# differential_integrator: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.start (`DEC-3a3db017d176`)

**Where does the output start, with no reset drawn?** → at zero: `.ic` on the output and both op amp inputs

- the starting charge on both capacitors is part of the answer, so it is stated
- Rejected add a reset switch: the figure has none, and a reset for the E2 side would need a second one

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O = -1/(R_I C_O) integral (E_I - E_2) dt = 10 integral (E_2 - E_1) dt. Integrates difference between two signals.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 59, Differential Integrator.
