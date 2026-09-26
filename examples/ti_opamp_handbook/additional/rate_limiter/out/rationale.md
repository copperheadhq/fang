# rate_limiter: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.reading (`DEC-0c77f0d9ebef`)

**How is the figure wired?** → E_I through R_1 to the first op amp's + input, R_0 from E_O back to that same + input, R_2 from its - input to ground; the bridge's left corner on its output, top corner to +Supply through R_3, bottom to -Supply through R_4, right corner through R_5 to the integrator's summing point; every diode points from the top corner down to the bottom one

- the loop: E_O too high puts the + input above ground, the first op amp rises, the bridge pushes current into the integrator, E_O falls
- the bridge's top two diodes have their anodes on the R_3 corner and the bottom two their cathodes on the R_4 corner, which is the orientation that limits in both directions
- Rejected alternative: R_0's left end drops onto the node where R_1 meets the + input; with the integrator inverting, feedback to + is what makes the loop negative
- Rejected alternative: nothing returns from the first op amp's output to its - input; R_2 only returns that input to ground

### system.supplies (`DEC-e28b18de1aaa`)

**What are +Supply and -Supply?** → +15 V and -15 V

- the handbook's op amps swing +/-13.5 V on +/-15 V supplies
- Rejected +/-12 V: the 7.5 V/s the page prints is 15 V over R_3 + R_5 and C_0

## Calculations

### system.limit (`CALC-cdc0ecd1b9a6`)

`rate = (supply - V_D) / ((R_3 + R_5) C_0)`

Result: the page's 7.5 V/s is 15 V / (200 kOhm x 10 uF), with no diode drop; the diode the current passes through costs about 0.45 V at 73 uA, so the circuit slews about 3% slower, near 7.27 V/s

- Over `system.supply_pos` (Cell, `CMP-1cdeb813e200`)
- Over `system.c_0` (Capacitor, `CMP-21f147af860d`)
- Over `system.r_3` (Resistor, `CMP-4cd5e4d4b60d`)
- Over `system.r_5` (Resistor, `CMP-dcb643d14409`)

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O = -(R_O/R_I) E_I = -E_I. Rate limit = 7.5 V/sec

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 89, Rate Limiter.
