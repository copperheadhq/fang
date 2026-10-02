# antenna_match: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Requirements

### system.match_spec (`REQ-c82edd25af93`)

> The antenna presents at least 10 dB of return loss at 2.44 GHz, the middle of the 2.4 GHz band

MUST, state KNOWN, validation by analysis.

- Verified by `system.matched` (`VER-24067c6b485f`): **UNKNOWN** by analysis

## Calculations

### system.l_match (`CALC-9175ee5ecaf2`)

`Q = sqrt(R0 / RL - 1); X_series = Q RL - X_antenna; B_shunt = Q / R0`

Result: 1.82 nH series and 1.47 pF shunt for 22 - j3.1 Ohm at 2.44 GHz; fitted with 1.8 nH and 1.5 pF

- Over `system.shunt_c` (Capacitor, `CMP-4e8847eff69d`)
- Over `system.series_l` (Inductor, `CMP-c56bbd49ae4f`)
- Over `system.antenna` (ChipAntenna, `CMP-eae764b0bc08`)
