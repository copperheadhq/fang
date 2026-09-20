# noninverting_amp — rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Requirements

### system.answer — `REQ-eec820d998c5`

> The input impedance is 68.75 kOhm and Av is 16, non-inverting

MUST, state KNOWN, validation by analysis.

- Verified by `system.answered` (`VER-299b3c990905`): **PASS** by analysis
  - on `system.question` (`EVD-3ee3847ba3f2`)

## Decisions

### system.reading — `DEC-0c77f0d9ebef`

**Where does the upper 220 k return to?** → to the bias node, beside the 100 k, so both land on the + input at one end and on the .5 uF's node at the other

- under this reading both the 220 k and the 100 k run from the input node to a node the .5 uF holds at a.c. ground, which puts them in parallel across the input
- the answer is a reading of the drawing before it is arithmetic, so the reading is recorded rather than assumed
- Rejected alternative: the figure's top wire comes down to the left of the symbol, onto the + input, not to the output on its right
- Rejected alternative: no rail is drawn anywhere in the figure, and the lower 220 k already returns the + input's bias current to ground on its own

## Calculations

### system.voltage_gain — `CALC-32483b5f3622`

`Av = 1 + Rf/Rg, with the 1 uF shorting the 2 k leg to ground`

Result: 1 + 30k/2k = 16, or +24 dB, non-inverting. At d.c. the 1 uF is an open and the stage falls to unity gain, which is what keeps the output offset small. The 12 k load does not enter it

- Over `system.r_gain` — Resistor (`CMP-4b1aad7cd2b4`)
- Over `system.c_gain` — Capacitor (`CMP-9efa396e94ee`)
- Over `system.r_feedback` — Resistor (`CMP-d344d52555c1`)

### system.corner_frequencies — `CALC-c5b8ba961794`

`f = 1 / (2*pi*R*C), once per capacitor`

Result: 23.1 Hz at the input, 1.4 Hz at the bias node, 79.6 Hz at the gain leg, 66.3 Hz into the load. The 1 uF against 2 k is the highest of the four, so the midband both answers are claimed over starts about a decade above it

- Over `system.c_bias` — Capacitor (`CMP-65ee0edcbc2a`)
- Over `system.c_in` — Capacitor (`CMP-80ddc77eef74`)
- Over `system.c_gain` — Capacitor (`CMP-9efa396e94ee`)
- Over `system.c_out` — Capacitor (`CMP-d0f40f6fc9a3`)

### system.input_impedance — `CALC-e314da57bae2`

`Zin = 220k || 100k, both returning to the a.c. ground the .5 uF makes`

Result: 68.75 kOhm. The lower 220 k does not appear: the .5 uF is across it, and the op amp's own + input draws nothing

- Over `system.r_bias_upper` — Resistor (`CMP-1886ca15d13a`)
- Over `system.r_series` — Resistor (`CMP-1974a36a0bec`)
- Over `system.c_bias` — Capacitor (`CMP-65ee0edcbc2a`)

## Evidence

### system.question — `EVD-3ee3847ba3f2`

> What is the input impedance in Figure 4.44? What is Av?

Cited from problem set, question 40, figure 4.44 -- the circuit as drawn, no frequency given.
