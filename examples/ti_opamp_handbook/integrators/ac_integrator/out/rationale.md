# ac_integrator: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.reading (`DEC-0c77f0d9ebef`)

**What is the bubbled output at the bottom of the op amp, and what do R2 and C_I do?** → an inverted output (the op amp has complementary outputs); R2 and C_I low-pass -E_O onto the + input, a DC servo that holds the DC gain at -1

- only the inverted reading makes the stated function true: DC gain -1, integration above the corner
- the handbook uses op amps with two outputs elsewhere (page 69), and a bubble is the usual mark of the inverting one
- Rejected alternative: then R2 and C_I feed +E_O back to the + input, positive feedback at DC: the transfer function has a pole at +1/sqrt(tau_1 tau_2) and the output runs to a rail
- Rejected alternative: that is an ordinary integrator, which ramps on a DC input; it cannot integrate the AC component only

## Calculations

### system.response (`CALC-0028a81b46e2`)

`E_O/E_I = -(1 + p R2 C_I) / (1 + 2 p R_I C_O + p^2 R_I C_O R2 C_I)`

Result: -1 at DC; -1/(p R_I C_O) above the corner, unity gain at 159 Hz and 1.59 at 100 Hz; a resonance at 1.59 Hz with Q = 50, whose peak the AC sweep shows near 5000

- Over `system.r2` (Resistor, `CMP-1749a5a18a37`)
- Over `system.c_i` (Capacitor, `CMP-ade6de650003`)
- Over `system.r_in` (Resistor, `CMP-ba02db80e645`)
- Over `system.c_out` (Capacitor, `CMP-d0f40f6fc9a3`)

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> Integrates AC component only.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 59, AC Integrator.
