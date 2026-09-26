# inverting_buffer_adjustable_gain: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.trim (`DEC-2becb3c534eb`)

**Where is the wiper?** → at the centre of its travel, where the gain is exactly -1

- the figure draws the wiper and gives no setting
- with matched 10 kOhm resistors the centre is where the trim lands
- Rejected at either end: the ends are the trim's limits, not a setting anyone would leave it at; the bench runs both to show the range

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> Potentiometer in feedback allows gain trimming to compensate for tolerance in resistor values.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 50, Inverting Buffer Adjustable Gain.
