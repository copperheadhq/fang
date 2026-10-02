# lag_element: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.reading (`DEC-0c77f0d9ebef`)

**The drawn values give -0.01/(1 + 0.1 P); the page prints -10/(10 + P), a DC gain of -1. Which is simulated?** → the drawn values, R_I 1 MOhm, R_O 10 kOhm, C_O 10 uF: a DC gain of -0.01 and a corner at 10 rad/s, 1.59 Hz

- R_O C_O = 0.1 s agrees with the printed pole at P = -10, so the lag is right and only the gain is off
- -10/(10 + P) needs R_O/R_I = 1; 10k/1M is 0.01
- Rejected R_I = 10 kOhm, which makes the printed -10/(10 + P) true: it is the likeliest intent, but it changes a value the figure prints; the program simulates what is drawn and says where the formula parts from it
- Rejected R_I and R_O swapped: 1 MOhm across 10 uF is a 10 s time constant and a gain of -100: -100/(1 + 10 P), further from the printed form than the drawing is

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> E_O = -(R_O / R_I) E_I / (1 + R_O C_O P) = -10 E_I / (10 + P); integrating type phase lag

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 84, Lag Element.
