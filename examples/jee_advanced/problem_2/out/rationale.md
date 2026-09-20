# problem_2 — rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Requirements

### system.answer — `REQ-eec820d998c5`

> The current I through R (= 2 ohm) is 1 A

MUST, state KNOWN, validation by analysis.

- Verified by `system.answered` (`VER-299b3c990905`): **PASS** by analysis
  - on `system.operating_point` (`EVD-242edf6457df`)
  - on `system.question` (`EVD-3ee3847ba3f2`)

## Calculations

### system.balanced_branches — `CALC-014ca1c17539`

`a branch between two nodes at equal potential carries no current`

Result: r_bottom (10 ohm) bridges 3 V to 3 V and r_top_right_spoke (8 ohm) bridges 4 V to 4 V, so both carry 0 A and what is left is series-parallel — which is why I is a whole ampere

- Over `system.r_top_right_spoke` — Resistor (`CMP-81a8d38b564a`)
- Over `system.r_bottom` — Resistor (`CMP-aa1b7e8d99e4`)

### system.branch_currents — `CALC-a159ec2a03a9`

`I = (V_here - V_there) / R, once per branch`

Result: r (2 ohm) 1 A, r_top (1 ohm) 0.5 A, r_left (6 ohm) 0.25 A, r_right (2 ohm) 0.5 A, r_bottom (10 ohm) 0 A, r_top_left_spoke (2 ohm) 0.25 A, r_top_right_spoke (8 ohm) 0 A, r_bottom_right_spoke (4 ohm) 0.25 A, r_left_leg (12 ohm) 0.25 A, r_right_leg (4 ohm) 0.75 A

- Over `system.r_left_leg` — Resistor (`CMP-4cd91a17117e`)
- Over `system.r_right` — Resistor (`CMP-526797adc2d0`)
- Over `system.r_left` — Resistor (`CMP-819f18b962e2`)
- Over `system.r_top_right_spoke` — Resistor (`CMP-81a8d38b564a`)
- Over `system.r_right_leg` — Resistor (`CMP-92d463895ba1`)
- Over `system.r_top` — Resistor (`CMP-9ea70a3ed2b2`)
- Over `system.r_bottom` — Resistor (`CMP-aa1b7e8d99e4`)
- Over `system.r` — Resistor (`CMP-cebf1455e844`)
- Over `system.r_top_left_spoke` — Resistor (`CMP-e6bd3daff048`)
- Over `system.r_bottom_right_spoke` — Resistor (`CMP-f62f15397698`)

### system.node_potentials — `CALC-bf2a3c73fac1`

`the operating point, taken against the bottom rail`

Result: top left 4.5 V, top right 4 V, centre 4 V, bottom left 3 V, bottom right 3 V, bottom rail 0 V

- Over `system.battery` — Battery (`CMP-d1047166a495`)
- Over `system.reference` — GroundReference (`CMP-fe129c51b056`)

## Evidence

### system.operating_point — `EVD-242edf6457df`

> ngspice reports 1.000000 A through R1, the 2 ohm the question names

Cited from examples/jee_advanced/problem_2/solve.py, the operating point fang.simulation lowered and ran.

### system.question — `EVD-3ee3847ba3f2`

> In the following circuit, the current through the resistor R (= 2 ohm) is I Amperes. The value of I is

Cited from JEE (Advanced) 2015, question 13 — an integer answer, no options offered.
