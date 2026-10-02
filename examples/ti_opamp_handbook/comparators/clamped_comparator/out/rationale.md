# clamped_comparator: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.diode_drop (`DEC-ef5315fd1474`)

**What does each 1N4148 drop while it clamps?** → 0.394 V: the 1N4148 model at the 15 uA the summing point sends through it for E_I = 3 V (CR_1) or 0 V (CR_2)

- the clamp level moves by 1.7 V per volt of drop on the negative side and 1.2 V per volt on the positive, so the drop is not negligible
- the drop is the model's at the current it actually carries
- Rejected 0 V, as the printed clamp formulas assume: the output then clamps at -10 V and +3 V, which neither the simulation nor the figure's own waveform shows
- Rejected 0.6 V, the usual rule of thumb: that is a diode at around a milliamp; at 15 uA a 1N4148 drops about 0.4 V

## Calculations

### system.clamps (`CALC-4d8626ad0ab8`)

`E_O = the divider's output with its tap one diode drop past the summing point, plus the diode's current through R_b`

Result: -(10/15)(15.394) - 0.394 - 10 kOhm x 15 uA = -10.807 V, and (3/15)(15.394) + 0.394 + 3 kOhm x 15 uA = +3.518 V

- Over `system.r_a_prime` (Resistor, `CMP-32ec3106ee98`)
- Over `system.cr_1` (SignalDiode, `CMP-3e4b90336913`)
- Over `system.r_b_prime` (Resistor, `CMP-4578b9429a66`)
- Over `system.r_b` (Resistor, `CMP-491f26900685`)
- Over `system.cr_2` (SignalDiode, `CMP-b8d398ccfff2`)
- Over `system.r_a` (Resistor, `CMP-ce0027290805`)

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> Threshold = -(R_2 / R_1) V_ref = -(1 MOhm / 100 kOhm)(-15 VDC) = 1.5 VDC; Negative clamping level = -(+V_sup) Rb / Ra = -15 VDC 10 kOhm / 15 kOhm = -10 VDC; Positive clamping level = -(-V_sup) Rb / Ra = +15 VDC 3 kOhm / 15 kOhm = +3 VDC; E_O = -10 VDC for E_I > 1.5 VDC; E_O = +3 VDC for E_I < 1.5 VDC

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 47, Figure 54, Fully Clamped Voltage Comparator.
