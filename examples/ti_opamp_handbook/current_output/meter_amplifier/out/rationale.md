# meter_amplifier: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.movement (`DEC-2d8bf82ad129`)

**What is the meter's resistance?** → 100 Ohm, a 1 mA movement

- the figure draws a meter and gives it no rating
- a 100 mV rms input into 100 Ohm puts the average near 0.45 mA, half of a 1 mA scale
- Rejected a 50 uA, 2 kOhm movement: R8 (68 kOhm) across it would then take 3% of the current the meter should, where across 100 Ohm it takes 0.15%

### system.names (`DEC-805f971fe768`)

**The figure labels two capacitors C1, one 1 uF and one 10 uF. Which is which?** → the 1 uF at the input is `c_in`; the two 10 uF in the bridge are `c_left` (drawn C1) and `c_right` (drawn C2)

- the values are unambiguous where they are drawn; only the names collide
- Rejected alternative: the value printed beside the input capacitor is 1 uF; only its name repeats

### system.calibration (`DEC-88d4bb587bbf`)

**Where is R5 set?** → 0.47 of its travel, 53 Ohm in circuit, so R4 + R5 is 100 Ohm

- R5 is drawn as a rheostat: its wiper is tied to the end at R4, so what is in circuit is the part from the wiper to ground
- a round 100 Ohm makes the reading a round number
- Rejected the whole 100 Ohm: used as a second run, to show the reading follows R4 + R5 as the calibration control moves

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> Meter reading = 0.9 E_I / (R4 + R5) (rms). R5: gain control (calibration). Fully developed average reading meter.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 80, Meter Amplifier.
