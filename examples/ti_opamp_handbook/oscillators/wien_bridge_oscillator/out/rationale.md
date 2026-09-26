# wien_bridge_oscillator: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.lamp_model (`DEC-3f20e5801834`)

**How does the GE 1869 behave?** → 10 V and 14 mA rated, so 714 Ohm hot; 70 Ohm cold, a tenth of hot; resistance linear in the power it has taken, filtered with a 50 ms thermal time constant

- the handbook names the lamp and no model; its rating is 10 V at 14 mA
- tungsten runs about ten to one hot to cold
- what the oscillator uses is the lamp's resistance at its operating point, which is pinned by the gain condition, not by the model
- Rejected a power law in the filament's power: closer to tungsten over the whole range, but near the rating, where this circuit runs the lamp, both give the same resistance, and a power law has no slope at zero to start from
- Rejected a thermal time constant of a few ms: the resistance would then follow each cycle, and at 100 Hz that is distortion, where the page claims high purity

### system.gain_trim (`DEC-4e31a90f7587`)

**Where is the R1 rheostat set?** → 50 Ohm in circuit, so the lamp must settle at 705 Ohm

- gain 3 needs R3 + R_lamp = (R1 + R2) / 2; with R2 at 1.8 kOhm and R3 at 220 Ohm the lamp needs 680 Ohm even with R1 at zero
- 50 Ohm is as much of R1 as a 714 Ohm lamp leaves room for
- Rejected half its travel, 250 Ohm: the lamp would have to reach 805 Ohm, past its 714 Ohm rating, and burn out before the gain came down to 3

### system.tuning (`DEC-5df3b067cbbb`)

**What are R and C?** → two 100 kOhm rheostats and two 15.9 nF capacitors; 0.1 of the travel (10 kOhm) is 1 kHz, all of it 100 Hz, and 1/60 of it 6 kHz

- one rheostat of 60:1 with a fixed capacitor covers exactly the range the page prints
- Rejected fixed resistors: the figure draws R and C as variable, and a range of 100 to 6000 Hz is a tuning range

### system.swing (`DEC-d07f8eaf8944`)

**What output swing does the op amp have?** → +/-13.5 V in the first run, as elsewhere in the handbook; +/-60 V in the runs that show the lamp regulating

- with a 705 Ohm lamp and 220 Ohm beside it, the - input carries 14 mA and the output 3 x 14 mA x 925 Ohm, 39 V rms
- the first run shows what the drawn circuit does on the usual swing, and the others show what it was drawn to do
- Rejected change the resistors so the lamp regulates on +/-15 V supplies: that is a different circuit from the one drawn
- Rejected a lamp model that is hot at a lower current: a GE 1869 is 714 Ohm only at its 14 mA rating; a model that got there sooner would be a different lamp

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> f_O = 1 / (2 pi R C), 100 to 6000 Hz. High purity sine wave generation.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 83, Wien Bridge Oscillator.
