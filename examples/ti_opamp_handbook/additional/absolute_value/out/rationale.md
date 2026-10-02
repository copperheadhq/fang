# absolute_value: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.reading (`DEC-0c77f0d9ebef`)

**The figure puts E_I, both cathodes and the - input on one node. How is it wired?** → E_I on the upper diode's anode and the left R; both cathodes on the + input; the lower diode's anode on ground; the - input between the two Rs

- it keeps every part the figure draws, and the orientation of both diodes
- it is a follower for +E_I and an inverter for -E_I, as the page says
- reversing both diodes makes the + input take the lower of E_I and 0, which gives -|E_I|, the page's last sentence
- Rejected alternative: the left R and the upper diode close on themselves, the - input is held at E_I by the source and the + input at ground, and the output has nothing to control; it saturates
- Rejected alternative: the upper diode then passes only negative E_I into the inverter and the lower diode shorts the source there: a half-wave rectifier, not |E_I|

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> +E_I follower circuit, -E_I inverter circuit, E_O = |E_I|; full wave rectification. Reverse diodes to give E_O = -|E_I|

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 87, Absolute Value.
