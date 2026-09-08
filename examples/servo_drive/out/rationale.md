# servo_drive — rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Requirements

### system.thermal — `REQ-efd31b2c73a1`

> Conduction loss per bridge stays under 2 W at 15 A continuous

MUST, state KNOWN, validation by analysis.

- No verification closes this requirement yet.
