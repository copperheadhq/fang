# ac_preamplifier: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.trim (`DEC-2becb3c534eb`)

**Where is R_4 set?** → full travel, 10 kOhm in series with R_3, for a gain of 509, the nearest the trim comes to the printed 500

- R_4 is drawn as a rheostat: its wiper runs to the grounded end
- the page gives no setting
- Rejected the setting that gives 500: there is none: R_3 + R_4 in parallel with R_1 can only lower 200 Ohm, and raise the gain above 501
- Rejected leave R_3 and R_4 out, as the printed formula does: the figure draws them, and a trim that is not there trims nothing

### system.load (`DEC-bf109e8b1fc8`)

**What does C_3 drive?** → 100 kOhm to ground, the input of a following stage; its corner with C_3 is 0.16 Hz

- the figure draws no load
- Rejected nothing: the output node would have no d.c. path, and the simulator cannot solve it
- Rejected 10 kOhm: its 1.6 Hz corner with C_3 would sit on top of the stage's own and be mistaken for it

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> Completely developed AC amplifier with high Z_in and double rolloff rate and gain trim. E_O / E_I = (R_0 + R_1) / R_1 = 500. R4 - Fine gain adjust. Low Frequency rolloff begins f_-3dB = 1 / (2 pi R_1 C_1) = 1.6 Hz. R_1 C_1 = R_2 C_2

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 78, AC Preamplifier.
