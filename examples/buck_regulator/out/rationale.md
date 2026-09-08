# buck_regulator — rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Requirements

### system.rail_tolerance — `REQ-84ef88a5fbc2`

> The 3V3 rail holds 3.3 V within 3% for 0 to 1.5 A over a 6 to 15 V input

MUST, state KNOWN, validation by analysis.

- Verified by `system.load_regulation` (`VER-b8aa7b6feb2f`): **PASS** by analysis
  - on `system.ripple_current` (`EVD-b4e90b2ab592`)
  - on `system.absolute_maximum` (`EVD-ff1f80f58e6b`)

## Decisions

### system.part_choice — `DEC-f748a65ae91c`

**Which converter makes the 3V3 rail?** → TPS62130

- 17 V absolute maximum against a 15 V worst case input
- 3 A capability against a 1.5 A load, so the part is not the limit
- Rejected LM2596: asynchronous, and too tall for the enclosure
- Rejected MP2315: no power-good output, and the sequencing needs one
- Serves `system.rail_tolerance` (`REQ-84ef88a5fbc2`)

## Calculations

### system.inductor_value — `CALC-7d60a2e8f772`

`L = v_out * (1 - v_out / v_in) / (f_sw * ripple_current)`

Result: 4.7 uH at 1.25 MHz for 30% ripple at 1.5 A

- Over `system.inductor` — Inductor (`CMP-64dfc4cd840c`)
- Over `system.controller` — BuckController (`CMP-78f22adc1404`)

### system.divider_ratio — `CALC-b1640610e734`

`v_out = v_ref * (1 + top / bottom)`

Result: 3.3 V from a 0.8 V reference at 3.125

- Over `system.fb_top` — Resistor (`CMP-427611a561a7`)
- Over `system.fb_bottom` — Resistor (`CMP-fbfdf0649f0c`)

## Evidence

### system.ripple_current — `EVD-b4e90b2ab592`

> Recommended inductor ripple is 20 to 40% of the maximum output current

Cited from SRC-DS-TPS62130, section 9.2.2.1, inductor selection.

### system.absolute_maximum — `EVD-ff1f80f58e6b`

> VIN absolute maximum is 17 V, recommended operating is 3 to 17 V

Cited from SRC-DS-TPS62130, section 6.1, absolute maximum ratings.
