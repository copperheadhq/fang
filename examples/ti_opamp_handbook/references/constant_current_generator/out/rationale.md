# constant_current_generator: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.reading (`DEC-0c77f0d9ebef`)

**Which op amp input does the R_2 / R_L node go to?** → the - input, with the + input on ground

- I = V_Z / R_2 needs the node held at ground, which only negative feedback does
- the drawing's + and - markings are swapped against every formula on the page
- Rejected the + input, as drawn: R_L then returns the output to the + input, positive feedback, and the output latches at +13.5 V; a transient of that wiring does exactly that

### system.bias (`DEC-3a080235c9ed`)

**Is R_1 330 Ohm, as drawn, or 360 Ohm, as printed?** → 330 Ohm, as drawn

- the drawing is the circuit; the printed formula is wrong either way
- 330 Ohm leaves the zener 7.3 mA, which keeps it in breakdown
- Rejected 360 Ohm, the printed result: it comes from (15 - V_Z) / I_Z, which leaves out the 20 mA R_2 takes from the same node; it would leave the zener 5 mA, not 25 mA

### system.load (`DEC-bf109e8b1fc8`)

**What is R_L?** → a rheostat (a potentiometer with its wiper on one end) at 500 Ohm, turned to 800 Ohm for one run

- the figure gives R_L no value: it is whatever is being fed
- 500 Ohm is inside the 675 Ohm limit, 800 Ohm is past it
- Rejected a fixed resistor: a run could not take the load past its limit

## Calculations

### system.zener_current (`CALC-d0b1d3bca945`)

`I_Z = (15 - V_Z) / R_1 - V_Z / R_2`

Result: 9 / 330 - 6 / 300 = 27.3 mA - 20 mA = 7.3 mA. The handbook's R_1 = (15 - V_Z) / I_Z drops the second term

- Over `system.r_1` (Resistor, `CMP-1116cb228fe1`)
- Over `system.r_2` (Resistor, `CMP-37372974c055`)
- Over `system.zener` (Zener, `CMP-aa33ef0e7c12`)
- Over `system.supply` (Cell, `CMP-b3194d2c7473`)

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> Convenient current reference up to 20 mA: I = V_Z / R_2 = 6 / 300 = 20 mA; R_1 = (15 - V_Z) / I_Z = 9 / 25 = 360 Ohm; R_L min = Saturation Voltage / I = 13.5 V / 20 mA = 675 Ohm

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 51, Constant Current Generator.
