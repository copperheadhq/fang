# reference_voltage_supply: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.cell (`DEC-819561347c8a`)

**What is Eref?** → a saturated Weston cell, 1.0183 V, for outputs of +/-10.183 V

- the figure labels the cell Eref and gives no value
- Rejected a 1.000 V reference, for round +/-10 V outputs: the page's circuits are standard-cell circuits, and the point of R_4 is protecting a cell

## Calculations

### system.bootstrap (`CALC-e692d52403a9`)

`i_cell = Eref / R_1 - (+E_O - Eref) / R_4`

Result: Eref / 10 kOhm - 9 Eref / 90 kOhm = 0: R_4 returns to the cell's node exactly the 101.8 uA that R_1 takes from it

- Over `system.r_1` (Resistor, `CMP-1116cb228fe1`)
- Over `system.r_2` (Resistor, `CMP-37372974c055`)
- Over `system.r_3` (Resistor, `CMP-4cd5e4d4b60d`)
- Over `system.e_ref` (Cell, `CMP-90e203cf744d`)
- Over `system.r_0` (Resistor, `CMP-9f649540f4bc`)
- Over `system.r_4` (Resistor, `CMP-e5d84f6363ba`)

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> Reference Voltage Supply: Eref; R1 10 kOhm, R0 100 kOhm, R3 10 kOhm, R2 10 kOhm, R4 90 kOhm; outputs -E_O and +E_O

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 52, Reference Voltage Supply.
