# single_supply: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.supply (`DEC-84bca5dbf6e6`)

**What is +Supply, and what can the op amp swing on it?** → 15 V, and an output from 0 V to 13.5 V: to ground at the bottom, and 1.5 V short of the rail at the top, like the bench's op amp on +/-15 V

- the figure labels the rail +Supply and gives no value
- 15 V is the rail the handbook's other circuits run from
- Rejected the bench's default +/-13.5 V swing: a single-supply part cannot go below its only other rail, ground
- Rejected a rail-to-rail 0 to 15 V swing: the handbook's op amps are not rail-to-rail; the headroom is the conservative reading

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> Equivalent to above, with the supply "floated" above ground. (Above: E_O = -10 E_I, f_-3dB = 1 / (2 pi R_I C_I) = 16 Hz.)

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 76, Single Supply.
