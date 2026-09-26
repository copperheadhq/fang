# simple_meter_amplifier: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.movement (`DEC-2d8bf82ad129`)

**What is the meter's resistance?** → 100 Ohm

- the meter's share is R_O / (3 R_O + R_M); 100 Ohm against 14.1 kOhm keeps it within 1% of the handbook's third
- Rejected a zero-ohm meter: no movement has none, and the formula's third is the limit a real one approaches
- Rejected a 2 kOhm, 50 uA movement: the meter takes R_O / (3 R_O + R_M) of the current, which at 2 kOhm is 0.29 rather than a third, 12% low

### system.diodes (`DEC-360de057404f`)

**Which way do the two diodes point?** → the upper one from the top corner into the summing point, the lower one from the summing point into the bottom corner

- the diode symbols are too small in the figure to read their direction, so the only readings are the ones that close the loop for both polarities
- Rejected alternative: then one polarity of input current has no path back to the output and the loop opens for half of every cycle
- Rejected alternative: that works too and reverses the meter current; the reading taken makes it flow bottom to top, the way the meter's arrow points

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> I_meter = E_I / (3 R_I) = E_I / 30 mA. Linear current meter reads AC input voltage.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 79, Simple Meter Amplifier.
