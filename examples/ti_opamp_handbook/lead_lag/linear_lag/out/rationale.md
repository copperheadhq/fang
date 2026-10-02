# linear_lag: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.rheostat (`DEC-18372ff92b1f`)

**Which end of the pot does the setting count from, and where are the claims held?** → end 1 on the + input, wiper and end 3 on E_I, so the path is setting x 10 kOhm; the claims are held at full travel, the page's 10/(10 + P)

- the figure ties the wiper to the end at E_I, a rheostat
- 10/(10 + P) is R C = 0.1 s, all of the pot in the path
- Rejected count the setting from the E_I end: the lag would still be linear but would shrink as D rises, the reverse of D R C

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O = E_I / (1 + D R C P) = 10 E_I / (10 + P); non-inverting low distortion

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 85, Lag value linear with R setting.
