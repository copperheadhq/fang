# gain_control: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.setting (`DEC-091f1d56fe0f`)

**Which end does the pot's setting count from, and where is the claim held?** → end 1 on ground and end 3 on the output, so the setting is k, the fraction below the wiper; the claim is held at k = 0.1, a gain of 10

- the figure gives the pot's value and no setting
- counting from ground makes the setting the feedback fraction itself
- Rejected end 1 on the output: the setting would be 1 - k, and the gain 1 / (1 - setting) reads less directly
- Rejected hold the claim at mid travel, a gain of 2: the page's other amplifiers are shown at a gain of 10; mid travel is checked on the bench

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> Equivalent to replacing both resistors in the non-inverting amplifier. Observe common mode voltage limit.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 73, Gain Control.
