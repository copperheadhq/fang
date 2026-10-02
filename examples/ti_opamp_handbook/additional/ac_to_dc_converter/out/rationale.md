# ac_to_dc_converter: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.reading (`DEC-0c77f0d9ebef`)

**How is the figure wired?** → R_3 runs from E_I to the second summing point; R_1 from E_I to the first; R_2 from the first summing point to a node whose diode points down into the first op amp's output, and R_6 from that node to the second summing point; R_4 returns through a diode pointing left, from the output; R_7 and R_8 in series, with C across them, from the second summing point to E_O

- under this reading E_H is -E_I for E_I > 0, and R_6 = R_3 / 2 makes the sum -|E_I| / R_3 on both halves: a full wave, as the page says
- Rejected alternative: R_6 leaves from the junction of R_2 and the downward diode; R_4's diode joins the output below it

### system.trim (`DEC-2becb3c534eb`)

**Where is the rheostat R_8 set?** → at zero, so the feedback is R_7 alone and the gain is exactly 1

- the full-wave average is already 0.9003 of the rms at unity gain
- R_8 only adds to R_7, so it is there to trim up for resistors that come out low; the simulated ones do not
- Rejected mid-travel, 1 kOhm: a gain of 1.1, which reads 0.99 E_I rms: 10% high with the drawn resistors exact

### system.bench (`DEC-c5e3bfe8b131`)

**How long does the filter take, and what is E_I?** → a 100 Hz sine at 6 V rms and at 6 mV rms, each run for 10 s, with the average taken over the last second

- C against R_7 is 1 s; after 9 s the start-up error is e^-9, about 0.01%
- 100 Hz is inside the page's 10 to 1000 Hz, and the ripple at 200 Hz through a 1 s filter is a few tenths of a millivolt per volt
- Rejected an initial condition on C at the expected output: it would assume the answer the run is there to check
- Rejected 1 kHz: ten times as many cycles to step through for the same settling

## Calculations

### system.average (`CALC-bd647312e298`)

`E_O average / E_I rms = (2 sqrt(2) / pi) (R_7 + R_8') / R_3`

Result: 0.9003 with R_8 at zero, which the page prints as 0.9

- Over `system.r_3` (Resistor, `CMP-4cd5e4d4b60d`)
- Over `system.r_8` (Potentiometer, `CMP-9924474c8263`)
- Over `system.r_7` (Resistor, `CMP-ea407d511240`)

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O average = 0.9 E_I rms. E_I = 6 mV to 6 V rms @ 10 to 1000 Hz. Precision conversion for measurement or control. Full wave rectifier with a smoothing filter.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 88, AC to DC Converter.
