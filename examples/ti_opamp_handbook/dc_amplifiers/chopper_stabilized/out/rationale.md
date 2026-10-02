# chopper_stabilized: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.offsets (`DEC-9a453d41f191`)

**What input offsets does the comparison use?** → 1 uV for the TLC265x, and 2 mV for a general-purpose op amp put in its place for one run

- 1 uV is the TLC2652's maximum input offset at 25 C in its datasheet (typically about 0.5 uV)
- 2 mV is the order of a general-purpose bipolar or JFET op amp's offset; it stands for the class, not a named part
- Rejected the model's default of no offset: then both parts give 0 V out and the page's claim shows nothing
- Rejected a drift in uV per degree, swept over temperature: the model has no temperature dependence; an offset at one temperature is what it can carry, and drift is that offset moving

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O = -(R_O/R_I) E_I (R_I 1 kOhm, R_O 100 kOhm, TLC265x). Improved drift and stability

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 70, Chopper Stabilized.
