# time_delay_relay: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.setting (`DEC-091f1d56fe0f`)

**Where is R_7 set?** → K = 0.1, for a page delay of 5 s, and a second run at K = 0.5

- the formula's approximations cost least at small K: the ramp's end point and the wiper's resistance both scale with K
- Rejected K near 1: the ramp ends at R_5 K E / R_1, 1.5 V at K = 1, a fifth of the start

### system.reading (`DEC-0c77f0d9ebef`)

**How is the figure wired?** → C_0 from the - input to the R_5 node T, not to the output; a diode from S into T; R_6 from the supply to S; the switch from S to the output; R_4 and R_3 from the supply to the output, with a diode from the - input into their junction; the coil from ground through a diode into S

- this reading times, and gives the page's formula: T starts at half the supply and ramps down at K E / (R_1 C_0)
- the relay sees the op amp's clamped low output, about -7.9 V less a diode, which is enough for a 6 V coil; the diode keeps the positive output off it while timing
- Rejected alternative: the wire from C_0's + plate hops over the R_3 lead and the vertical from T hops over the output wire: neither joins
- Rejected alternative: the triangle points up, bar above; reversed, R_6 could put at most 15 V / 11 kOhm, 1.3 mA, through a 6 V, 1 kOhm coil, which never pulls it in
- Rejected alternative: its triangle points right, away from the - input; that way it would clamp the output high, where the timing ramp needs it

### system.supply (`DEC-84bca5dbf6e6`)

**What is +Supply?** → 15 V

- the formula does not depend on it: E cancels between start and slope
- Rejected 12 V: nothing on the page asks for it; the handbook's op amps run on 15 V

### system.relay (`DEC-a6e7aecb217e`)

**How is the relay modelled, and when does it pull in?** → its coil as a 1 kOhm meter, whose current is the reading; pull-in taken at 4.5 mA, 75% of the 6 mA a 6 V, 1 kOhm coil draws

- 75% of rated voltage is the usual must-operate figure for a small relay
- the coil sees about 7 V once the output clamps, well past it
- Rejected a coil with inductance and a contact that switches: the delay is set by the timer, not the relay; a coil's own milliseconds are beside a delay of seconds

## Calculations

### system.shortfall (`CALC-1944167e26f5`)

`Delay = C_0 (T_0 - R_5 I) / I, with I = K E / (R_1 + R_7 K (1 - K)) and T_0 = (E - V_D) R_5 / (R_5 + R_6)`

Result: T resets to 7.2 V, E/2 less half a diode drop. At K = 0.1 the ramp runs at 1.487 V/s down to 0.149 V: 4.75 s, 5% short of the page's 5 s. At K = 0.5 it runs at 7.32 V/s down to 0.73 V: 0.886 s against 1 s

- Over `system.r_1` (Resistor, `CMP-1116cb228fe1`)
- Over `system.c_0` (Capacitor, `CMP-21f147af860d`)
- Over `system.r_5` (Resistor, `CMP-dcb643d14409`)
- Over `system.r_7` (Potentiometer, `CMP-ea407d511240`)
- Over `system.supply_cell` (Cell, `CMP-f59851525a20`)

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> Delay = R_I C_O / (2 K_I), where K is setting of R_I, 0 < K < 1. Time operated relay. Open switch to reset, close to begin timing.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 90, Time Delay.
