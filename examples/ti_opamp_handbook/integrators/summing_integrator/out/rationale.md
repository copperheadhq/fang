# summing_integrator: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.bench (`DEC-c5e3bfe8b131`)

**What goes on the three inputs, and when does the integrator start?** → steady inputs whose sum is 0.6 V in one run and 0.4 V (with one negative input) in another; the reset switch opens at 10 ms

- the figure gives the parts and no drive
- a mixed-sign run shows the output follows the algebraic sum
- Rejected one input at a time: that checks three integrators, not that the inputs are summed

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O = -1/(RC) integral (E1 + E2 + E3) dt = -10 integral (E1 + E2 + E3) dt. One amplifier replaces separate summer and integrator circuits.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 58, Summing Integrator.
