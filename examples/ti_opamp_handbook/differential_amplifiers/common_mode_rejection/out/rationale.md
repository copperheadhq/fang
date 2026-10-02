# common_mode_rejection: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.reading (`DEC-0c77f0d9ebef`)

**Which of the figure's values is misprinted?** → R1: it is 10 kOhm, not the 1 kOhm drawn. Then R0/R1 = 10 as printed, and R2 + R3 = R1 at R3 = 0.9 kOhm, inside the 5 kOhm pot

- the page prints two equations, a gain of 10 and R2 + R3 = R1, and the drawn values satisfy neither
- R1 = 10 kOhm is the one change that satisfies both, and matches R4 and R5 beside it
- Rejected R1 = 1 kOhm, as drawn: the gain is then 100, not the printed 10, and R2 + R3 is at least 9.1 kOhm, so it can never equal R1: the E2 path is worth at most 11 against E1's 100, and no trim nulls E1 = E2
- Rejected R0 = 10 kOhm, with R1 = 1 kOhm: gives the printed gain of 10 but leaves R2 + R3 = R1 = 1 kOhm out of the pot's reach, so it fixes one printed equation of two
- Rejected R2 = 910 Ohm and R3 = 500 Ohm, with R1 = 1 kOhm: makes the trim reachable but leaves the gain at 100, and needs two values misprinted where the chosen reading needs one

### system.trim (`DEC-2becb3c534eb`)

**Where is the R3 rheostat set?** → 0.82 of its travel from the summing-point end, which leaves 0.9 kOhm in circuit and makes R2 + R3 = R1

- the page says to set R3 for zero output when E1 = E2
- the wiper is tied to the end at the summing point, so the part left in circuit is the travel from the wiper to R2
- Rejected mid-travel: 2.5 kOhm in circuit makes R2 + R3 = 11.6 kOhm and leaves 1.38 V out for 1 V on both inputs; the bench shows it, untrimmed

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O = -(R_O/R_1)(E1 - E2) = 10(E2 - E1); R2 + R3 = R1. R3 - common mode adjustment. Set for zero output when E1 = E2. (R1 drawn as 1 kOhm, R0 100 kOhm, R2 9.1 kOhm, R3 5 kOhm, R4 and R5 10 kOhm)

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 75, Common Mode Rejection.
