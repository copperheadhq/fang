# double_rolloff: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.reading (`DEC-0c77f0d9ebef`)

**The drawn values give C_1 R_1 = 1 s and C_2 R_2 = 0.1 s; which does the program follow?** → the drawn values, and the rule is recorded as not met

- the figure prints 1 uF, 100 kOhm, 100 uF and 10 kOhm
- the bench shows what the mismatch costs: a 9.3 dB peak
- Rejected change C_2 to 10 uF so that the rule holds: the figure is the source of truth for values; the rule is the page's intent, and the gap is reported

### system.topology (`DEC-741010fe333a`)

**Where do C_1 and R_2 connect?** → C_1 from the - input to a junction, R_1 from the junction to ground, and R_2 from the + input to the junction

- the dot at the C_1 R_1 junction has R_2's wire arriving from the left
- Rejected alternative: the figure brings R_2's lower end across to the C_1 R_1 junction, not to the ground line

## Calculations

### system.response (`CALC-0028a81b46e2`)

`E_O / E_I = s T_2 (1 + R_1/R_2 + s (R_0 + R_1) C_1) / (s^2 T_1 T_2 + s T_2 (1 + R_1/R_2) + 1)`

Result: 10 in the midband; poles at f_0 = 1/(2 pi sqrt(T_1 T_2)) = 0.50 Hz with Q = 2.9, a peak of 29.2 (9.3 dB over 10) at 0.52 Hz; 40 dB/decade below that down to the zero at 0.0175 Hz, 20 dB/decade below it

- Over `system.r_1` (Resistor, `CMP-1116cb228fe1`)
- Over `system.r_2` (Resistor, `CMP-37372974c055`)
- Over `system.c_2` (Capacitor, `CMP-777fb775623d`)
- Over `system.r_0` (Resistor, `CMP-9f649540f4bc`)
- Over `system.c_1` (Capacitor, `CMP-d3b596962e6c`)

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> Similar to above. C_1 R_1 = C_2 R_2

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 77, Double Rolloff.
