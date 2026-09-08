# i2c_bus — rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Requirements

### system.unique_addresses — `REQ-547cf553051e`

> No two devices on the bus answer to the same address

MUST, state KNOWN, validation by analysis.

- No verification closes this requirement yet.

## Evidence

### system.memory.thresholds — `EVD-49a6da89fb15`

> VIH is 2.0 V minimum over the 1.7-5.5 V supply range

Cited from SRC-DS-24AA02, table 1-2, DC characteristics.

### system.temperature.thresholds — `EVD-da4350d2a12e`

> VIH is 0.7 x VDD and VIL is 0.3 x VDD

Cited from SRC-DS-TMP102, table 7.5, electrical characteristics.
