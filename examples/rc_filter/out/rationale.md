# rc_filter — rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Requirements

### system.corner_spec — `REQ-5ecddeec2af0`

> The anti-aliasing filter's -3 dB corner lies between 1.5 kHz and 1.7 kHz

MUST, state KNOWN, validation by simulation.

- Verified by `system.corner_check` (`VER-ebeff65dcd46`): **UNKNOWN** by simulation

## Calculations

### system.by_hand — `CALC-a9c0a4831f90`

`f_c = 1 / (2 pi R C)`

Result: 1.59 kHz for 10 kOhm and 10 nF

- Over `system.c` — Capacitor (`CMP-95c5a91616a7`)
- Over `system.r` — Resistor (`CMP-cebf1455e844`)
