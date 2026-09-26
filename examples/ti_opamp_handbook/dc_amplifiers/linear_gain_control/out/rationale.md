# linear_gain_control: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.rheostat (`DEC-18372ff92b1f`)

**Which end of the 100 kOhm pot is in the loop, and at what setting are the claims held?** → end 1 on the summing point, wiper and end 3 on the output, so the loop sees setting x 100 kOhm; claims held at full travel, -10

- the figure ties the wiper to the end at the output, a rheostat
- the page prints the range, 0 to -10, and full travel is its end
- Rejected count the setting from the output end: the gain would still be linear but would fall as the setting rises; counting from the summing point makes the setting and the gain magnitude move together
- Rejected hold the claims at mid travel: the printed figure is the end of the range, -10; mid travel is checked on the bench

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O = 0 to -10 E_I, Z_in = R_I = 10 kOhm; variable from 0 to 10

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 71, Linear Gain Control.
