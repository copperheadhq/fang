# ac_non_inverting: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O in phase with E_I. E_O = (R_O + R_I) / R_I = 10 E_I. Low frequency rolloff f_-3dB = 1 / (2 pi R_I C_I) = 0.16 Hz

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 77, Non-Inverting.
