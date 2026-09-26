# integrator: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.start (`DEC-3a3db017d176`)

**Where does the output start?** → at zero, from an initial condition the transient run sets

- with nothing across C_O the op amp integrates any offset, so the starting point has to be said rather than left to the solver
- Rejected a reset switch: the page 55 figure draws none; pages 56 onward add one

### system.values (`DEC-f7c4162de03e`)

**What are R_I and C_O?** → 10 kOhm and 0.1 uF: R_I C_O = 1 ms, -1000 V/s per volt, unity gain at 159 Hz

- the figure names the parts and gives no values
- a unity-gain frequency in the audio band is far below the op amp's 10 MHz, so the ideal algebra is what the bench should measure
- Rejected 100 kOhm and 1 uF, as on page 56: page 56 is its own program; a different pair shows the formula is general
- Rejected leave them unknown: a rate nobody can compute is not a claim anything can check

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O = -Z_O/Z_I E_I = -E_I/(R_I C_O p) = -1/(R_I C_O) integral E_I dt

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 55, Integrators.
