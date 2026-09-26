# inverting_gain_control: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.setting (`DEC-091f1d56fe0f`)

**Which end does R_2's setting count from, and where is the claim held?** → end 1 on the output and end 3 on ground, so the setting s is the fraction between the output and the wiper; the claim is held at s = 0.5, a gain of -2.5

- the figure gives R_2's value and no setting
- Rejected hold the claim at one end of the range: one end is -1, where R_2 does nothing, and the other is infinite; the middle is where the T network shows

## Calculations

### system.t_network (`CALC-f48124691b7b`)

`E_O / E_I = -(R_O / R_I) (1 + R_a / R_b + R_a / R_O)`

Result: -(1 / (1 - s) + s) with R_O = R_2: -1 at s = 0, -2.5 at 0.5, -5.8 at 0.8, -10.9 at 0.9, -20.95 at 0.95

- Over `system.r_2` (Potentiometer, `CMP-37372974c055`)
- Over `system.r_in` (Resistor, `CMP-ba02db80e645`)
- Over `system.r_out` (Resistor, `CMP-e566c1ef689e`)

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O = (-1 to infinity) E_I, Z_in = 10 kOhm. Convenient gain technique

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 73, Inverting Gain Control.
