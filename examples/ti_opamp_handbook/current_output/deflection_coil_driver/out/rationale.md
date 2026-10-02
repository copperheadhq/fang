# deflection_coil_driver: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.coil (`DEC-eac574e8ba13`)

**What is the load?** → a 10 mH coil with 5 Ohm of winding, as an inductor and a resistor in series

- the figure names the load R_L and gives no value
- 10 mH over 5 Ohm is a 2 ms time constant, an 80 Hz corner, so at 1 kHz a voltage-driven current would lag by 85 degrees
- at 50 mA and 1 kHz the coil needs 3.2 V, inside the swing
- Rejected a plain resistor, as drawn: a deflection coil is an inductance, and the reason to drive one with current is the lag its inductance causes

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> I / E_I = -R0 / (R1 R3) = -100 mA / Volt. Load must be 'floating', i.e. ungrounded.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 82, Deflection Coil Driver.
