# selective_amplifier: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.reading (`DEC-0c77f0d9ebef`)

**How is the twin-T wired?** → from the summing point to the output: R_a, R_a in series with 2 C_a from their junction to ground, beside C_a, C_a in series with R_a/2 from their junction to ground

- the page calls it twin T feedback, and a notch in the feedback is a peak in the gain
- Rejected alternative: its two outer nodes are on the summing point and on E_O, beside R_O; in the input it would notch, not peak

## Calculations

### system.notch (`CALC-5bf2a8b5b750`)

`f = 1 / (2 pi R_a C_a)`

Result: 964.6 Hz; the page prints 1000 Hz

- Over `system.r_a1` (Resistor, `CMP-d2c45e7e9c76`)
- Over `system.c_a1` (Capacitor, `CMP-e7d7ba19ddfc`)

### system.at_peak (`CALC-bf35d5a910e1`)

`|A| = R_O / |R_I + 1 / (j 2 pi f C_I)| at the notch`

Result: C_I's reactance at 964.6 Hz is 3.3 kOhm, so |Z_in| = 10.53 kOhm and |A| = 31.34 (29.9 dB); the page's R_O / R_I = 33 leaves C_I out

- Over `system.r_i` (Resistor, `CMP-5a2680414986`)
- Over `system.r_o` (Resistor, `CMP-89c2061ba337`)
- Over `system.c_i` (Capacitor, `CMP-ade6de650003`)

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> Frequency peak = 1/(2 pi R_a C_a) = 1000 Hz. Gain at peak = R_O/R_I = 33 = 30 dB. Set C_I so that C_I R_I > 2 C_a R_a and R_I < 100 kOhm. Z_in = R_I = 10 kOhm. Z_out < 200 Ohm.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 91, Selective Amplifier.
