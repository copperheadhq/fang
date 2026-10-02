# presettable_voltage_source: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.cell (`DEC-819561347c8a`)

**What is Eref?** → a saturated Weston cell, 1.0183 V, so R_I = 1000 x Eref = 1018.3 Ohm

- the figure labels the cell Eref and gives no value
- Rejected a 1.2 V bandgap: the page's other circuits are standard-cell circuits

### system.decade_box (`DEC-b818abdf237d`)

**How is a decade box drawn in parts?** → a potentiometer with its wiper tied to its far end, set to full travel

- a rheostat is a potentiometer with its wiper on one end
- the bench can override a potentiometer's resistance for one run
- Rejected a fixed resistor: a run could not turn the dial without editing the program

### system.dial (`DEC-c945eb9b7225`)

**Where is the decade box set?** → 8981.7 Ohm, for E_O = 10.000 V

- the figure draws a decade box and no setting
- 10 V is the reference such a circuit is usually asked for
- Rejected a round 9000 Ohm: gives 10.0183 V; the dial exists to land on a round output

## Calculations

### system.scale (`CALC-6edee13fdeae`)

`i_set = Eref / R_I, with R_I = 1000 x Eref`

Result: 1 mA whatever the cell, so E_O = Eref + R_O x 1 mA: each ohm on the decade box is a millivolt above Eref

- Over `system.e_ref` (Cell, `CMP-90e203cf744d`)
- Over `system.r_in` (Resistor, `CMP-ba02db80e645`)

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O = (R_I + R_O) / R_I x Eref. Gives wide range of very stable reference voltages.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 52, Presettable Voltage Source.
