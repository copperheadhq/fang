# averager: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O = -R_O/R_I (E1 + E2 + E3) = -(E1 + E2 + E3)/3. R_O = R_I divided by number of inputs. Output is inverted average of input signals. Ground unused inputs to preserve scale

Cited from SBOA092B, Handbook of Operational Amplifier Applications, pages 65 and 66, Averager.
