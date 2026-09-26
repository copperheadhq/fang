# current_injector: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.load (`DEC-bf109e8b1fc8`)

**What is R_L?** → 1 kOhm by default, and 100 Ohm and 4.7 kOhm in the runs

- the figure draws R_L between two terminals with no value
- at 4.7 kOhm the + input is at -4.7 V and the output at -10.4 V, inside the swing
- Rejected one fixed load: the claim is that the current does not depend on R_L, which one value cannot show
- Rejected 10 kOhm: at 1 mA the + input would sit at -10 V and the output at -21 V, past the swing: the common-mode limit the page warns of

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> I = -E_I / R_L = -E_I mA; R1 / R2 = R0 / R3. Single terminal current available to ground. Observe common mode voltage limit.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 80, Current Injector.
