# problem_1 — rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Requirements

### system.answer — `REQ-eec820d998c5`

> All four options hold: (A), (B), (C) and (D)

MUST, state KNOWN, validation by analysis.

- Verified by `system.answered` (`VER-299b3c990905`): **PASS** by analysis
  - on `system.operating_point` (`EVD-242edf6457df`)
  - on `system.question` (`EVD-3ee3847ba3f2`)

## Calculations

### system.options — `CALC-19be8d7d685e`

`each claimed current against the branch it names`

Result: (A) r1 7.2 A — correct; (B) r2 1.2 A — correct; (C) r3 4.8 A — correct; (D) r5 2.4 A — correct. All four options are right, which is what the paper's key says

- Over `system.r2` — Resistor (`CMP-1749a5a18a37`)
- Over `system.r1` — Resistor (`CMP-390a79be1fe2`)
- Over `system.r5` — Resistor (`CMP-52cb475cbc08`)
- Over `system.r3` — Resistor (`CMP-99ef3f8b2557`)

### system.branch_currents — `CALC-a159ec2a03a9`

`I = (V_here - V_there) / R, once per branch`

Result: every resistor is 1 ohm: r1 7.2 A, r2 1.2 A, r3 4.8 A, r4 1.2 A, r5 2.4 A, r6 2.4 A, r7 3.6 A, r8 3.6 A

- Over `system.r2` — Resistor (`CMP-1749a5a18a37`)
- Over `system.r7` — Resistor (`CMP-2122ee180827`)
- Over `system.r6` — Resistor (`CMP-3411ae333c6c`)
- Over `system.r1` — Resistor (`CMP-390a79be1fe2`)
- Over `system.r5` — Resistor (`CMP-52cb475cbc08`)
- Over `system.r3` — Resistor (`CMP-99ef3f8b2557`)
- Over `system.r4` — Resistor (`CMP-c139a9a6fa47`)
- Over `system.r8` — Resistor (`CMP-d7073486dd1c`)

### system.node_potentials — `CALC-bf2a3c73fac1`

`the operating point, taken against the centre node`

Result: centre 0 V, left -1.2 V, top 1.2 V, right 4.8 V, bottom 1.2 V, from batteries of 12 V and 6 V

- Over `system.e1` — Battery (`CMP-5cf608e39c4e`)
- Over `system.e2` — Battery (`CMP-d16d8ff7af01`)
- Over `system.reference` — GroundReference (`CMP-fe129c51b056`)

## Evidence

### system.operating_point — `EVD-242edf6457df`

> ngspice reports 7.2, 1.2, 4.8, 1.2, 2.4, 2.4, 3.6 and 3.6 A through R1 to R8

Cited from examples/jee_advanced/problem_1/solve.py, the operating point fang.simulation lowered and ran.

### system.question — `EVD-3ee3847ba3f2`

> Which of the following statement(s) is(are) correct? (A) the current through R1 is 7.2 A; (B) the current through R2 is 1.2 A; (C) the current through R3 is 4.8 A; (D) the current through R5 is 2.4 A

Cited from JEE (Advanced) 2022, Paper 1, question 1 — multiple correct, four options.
