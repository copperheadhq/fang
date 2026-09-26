# augmenting_integrator: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.bench (`DEC-c5e3bfe8b131`)

**What input shows both terms?** → a 0.1 V step at 10 ms, from rest

- a step makes the proportional term a jump and the integral a ramp, each read directly
- Rejected a sine: the two terms add in quadrature and have to be separated again

## Calculations

### system.integral_term (`CALC-24cd826367f7`)

`1/(C_O R_I) = 1/(10 uF x 10 kOhm)`

Result: 10 per second. The handbook's second line prints the integral with a coefficient of 1, which would need C_O R_I = 1 s (100 uF, or R_I = 100 kOhm, which would also change the first term to -1)

- Over `system.r_in` (Resistor, `CMP-ba02db80e645`)
- Over `system.c_out` (Capacitor, `CMP-d0f40f6fc9a3`)

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O = -(R_O E_I)/R_I - 1/(C_O R_I) integral E_I dt = -10 E_I - integral E_I dt. Sums the input signal and its time integral.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, pages 59-60, Augmenting Integrator.
