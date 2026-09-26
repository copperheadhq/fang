# feedback_loop: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.load (`DEC-bf109e8b1fc8`)

**What is R_L?** → 1 kOhm by default, and 100 Ohm, 10 kOhm and 20 kOhm in the runs

- the figure draws R_L between two terminals with no value: it is the thing driven, not part of the source
- 10 kOhm at 1 mA puts the output at -10 V, inside the swing; 20 kOhm asks for -20 V and shows where the claim stops
- Rejected one fixed load: the claim is that the current does not depend on R_L, which one value cannot show

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> I = E_I / R_I = E_I mA; Z_in = R_I = 1 kOhm

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 79, Feedback Loop.
