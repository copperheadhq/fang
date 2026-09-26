# isolated_standard_cell: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.cell (`DEC-819561347c8a`)

**What is Eref?** → a saturated Weston standard cell, 1.0183 V

- the figure labels the cell Eref and gives no value
- the Weston cell is the standard cell the text has in mind
- Rejected a 1.2 V bandgap reference: the page is about standard cells, whose EMF is spoiled by current; a bandgap has an output stage of its own

### system.load (`DEC-bf109e8b1fc8`)

**What does the output drive?** → 20 kOhm to ground: a 20 kOhm/V meter on its 1 V range

- the text names 20 kOhm/V measuring devices as what damages the cell
- the figure draws the output terminals and no meter
- Rejected nothing: an unloaded follower says nothing about where the meter's current comes from, which is the point of the circuit

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> Prevent damage to standard cells induced by drawing current from them with low impedance (20 KOhm / Volt) measuring devices.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 51, Isolated Standard Cell.
