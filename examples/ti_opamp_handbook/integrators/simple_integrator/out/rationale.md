# simple_integrator: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.bench (`DEC-c5e3bfe8b131`)

**How is the integrator reset and started?** → the switch closed at t = 0 and opened at 10 ms, with a steady 0.1 V already on E_I, so the ramp starts from zero when the switch opens

- the handbook says only to close the switch to reset to zero
- 0.1 V gives -1 V/s, a ramp that stays well inside the swing for the run
- Rejected no switch, an initial condition on C_O: the figure draws the switch, and the reset is what it is for
- Rejected a 1 V input: at -10 V/s the output would reach the -13.5 V swing in 1.35 s

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O = -(1/(R_I C_O)) integral E_I dt = -10 integral E_I dt. Close switch to reset to zero.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 56, Simple Integrators.
