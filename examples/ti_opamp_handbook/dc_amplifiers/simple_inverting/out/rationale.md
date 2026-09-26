# simple_inverting: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.bias (`DEC-3a080235c9ed`)

**What input bias current does the bias-error run apply?** → 100 nA into the inverting input, applied by a card, in one run only

- 100 nA is the order of a general-purpose bipolar input; it is an illustration, not a part's datasheet value
- the + input is on ground as drawn, so there is no resistor there for the matching current to cross, and the error is the whole I_B R_O
- Rejected none, and say nothing about the undrawn resistor: the page prints its value, so a program that ignores it leaves a line of the page unexplained
- Rejected a bias-current parameter on the op amp: the shared model has an input offset voltage and no bias current, and the harness is not this program's to change

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O = -(R_O/R_I) E_I = -100 E_I; resistor = R_O R_I/(R_I + R_O) = 1 kOhm; Z_in = R_I = 1 kOhm

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 70, Simple Inverting sign changing amplifier.
