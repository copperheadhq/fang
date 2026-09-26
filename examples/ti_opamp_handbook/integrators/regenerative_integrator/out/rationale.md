# regenerative_integrator: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.reading (`DEC-0c77f0d9ebef`)

**Where do R2, R3, R4, R5, R6 and R7 connect?** → R6 from the R8 wiper to the - input and R7 from the wiper to the + input; R3 from the output to node X, R2 from X to the + input, and R4 plus the rheostat R5 from X to ground

- the handbook's procedure only makes sense with positive feedback: more R5 must mean more regeneration, and (R4 + R5)/R3 rises with R5
- Rejected alternative: the vertical wire at the left end of R2 comes down from the + input's junction dot, and a resistive path across C_O would make the regeneration negative feedback that shortens the hold
- Rejected alternative: the two resistors end on separate dots, one on each op amp input

### system.op_amp (`DEC-cfa315e44293`)

**What open-loop gain does the op amp have?** → 5000 (74 dB)

- the network brackets 1/A for A between about 3700 and 11000, so it was sized for an op amp of that era's gain
- with 5000, k = 1/A at R5 = 1.2 kOhm, 60% of its travel
- Rejected the bench default, 1e6: the smallest feedback fraction the network can set, with R5 at zero, is 0.9e-4, ninety times 1/A: the output runs away at every setting and the regeneration control does nothing useful
- Rejected 1e4: the balance would fall at 10% of R5's travel, not near the centre the procedure starts from

### system.settings (`DEC-f4acfbdfa71a`)

**Where are R8 and R5 set?** → R8 centred (the op amp is given no offset, so zero is the centre); R5 at a quarter of its travel

- a quarter of the travel is regeneration short of balance: a longer hold, still decaying
- Rejected R5 at the balance, 60%: the hold there is as long as the setting is exact, which is no number to claim

## Calculations

### system.hold_estimate (`CALC-2da9c3721dce`)

`tau = R6 C_O (1 - k) / (1/A - k), k = (R4 + x R5)/(R3 + R4 + x R5) R7/(R2 + R7)`

Result: k = 0 without regeneration: A R6 C_O = 5000 s. With R5 at a quarter (500 Ohm), k = 1.364e-4 and tau = 15,700 s, about three times longer. The zero control's 7.5 kOhm source resistance and R7's pull on the wiper are left out; the simulation puts tau 2.3% lower

- Over `system.r2` (Resistor, `CMP-1749a5a18a37`)
- Over `system.r7` (Resistor, `CMP-2122ee180827`)
- Over `system.r6` (Resistor, `CMP-3411ae333c6c`)
- Over `system.r5` (Potentiometer, `CMP-52cb475cbc08`)
- Over `system.r3` (Resistor, `CMP-99ef3f8b2557`)
- Over `system.r4` (Resistor, `CMP-c139a9a6fa47`)
- Over `system.c_o` (Capacitor, `CMP-cffe260ed560`)
- Over `system.amp` (OpAmp, `CMP-ed601b553153`)

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> Regeneration may be used to increase open loop DC gain to infinity. If integrator output decays toward zero, increase regeneration by increasing R5. If output continues to grow, decrease regeneration.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, pages 56-57, Simple Integrators (regeneration).
