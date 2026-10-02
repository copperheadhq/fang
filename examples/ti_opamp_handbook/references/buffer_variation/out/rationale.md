# buffer_variation: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.cell (`DEC-819561347c8a`)

**What is Eref, and which way round is it?** → a saturated Weston cell, 1.0183 V, + terminal on the output, so E_O = +Eref

- the figure gives the cell no value and its plates are not marked
- the output terminal is labelled Eref
- Rejected + terminal on the - input: gives E_O = -Eref; the figure labels the output Eref, not -Eref

### system.amp_model (`DEC-841897e540d2`)

**What offset does the TLC265x have?** → 1 uV, the maximum a chopper-stabilized TLC2652A is specified to

- the figure names the TLC265x
- offset adds to E_O undivided
- Rejected the bench default of 0 V: the figure names a chopper-stabilized part because its offset is small, not zero; E_O carries all of it

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> Low current drift of chopper - stabilized amplifiers improves stability and cell protection.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 52, Buffer Variation.
