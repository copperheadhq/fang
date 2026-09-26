# differentiator_with_stop: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> Input resistor sets high frequency cutoff. High frequency cutoff: F_O = 1/(2 pi R_I C_I) = 0.6 kHz. Low frequency cutoff: F_I = 1/(2 pi R_O C_I) = 16 kHz

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 61, With "Stop".
