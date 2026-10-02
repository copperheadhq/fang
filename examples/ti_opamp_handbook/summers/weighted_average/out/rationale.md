# weighted_average: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.setting (`DEC-091f1d56fe0f`)

**Where is R_O' set?** → 0.3545 of its 1 kOhm travel, 354.5 Ohm, so R_O + R_O' = R1 || R2 || R3

- the figure draws the pot and gives the rule that sets it, not a setting
- R1 || R2 || R3 is 5.4545 kOhm, and 5.1 kOhm leaves 354.5 Ohm for the pot
- Rejected the pot at its midpoint, 500 Ohm: 5.6 kOhm of feedback makes the weights add to 1.027, and equal inputs come out 2.7% large
- Rejected the pot's full 1 kOhm: 6.1 kOhm of feedback makes the weights add to 1.118

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> For E1 = E2 = E3, set R_O' so E_O = E_I. Then, R_O + R_O' = R1 || R2 || R3. E_O = -(R_O + R_O')E1/R1 - (R_O + R_O')E2/R2 - (R_O + R_O')E3/R3 = -(16.4 E1 + 8.2 E2 + 5.4 E3)/30

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 66, Weighted Average.
