# power_booster: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.models (`DEC-0e8476966e02`)

**What does each op amp's model hold?** → Table 1's columns: OPA277 +/-13 V swing and 20 uV offset, OPA512 +/-35 V swing and 6 mV offset; gain-bandwidth 1 MHz for the OPA277 and 4 MHz for the OPA512, from their data sheets; open-loop gain left at the bench's 120 dB

- the table gives swing and offset for each part
- the table gives no bandwidth; 1 MHz and 4 MHz are the OPA277's and OPA512's data-sheet figures
- Rejected the bench's default op amp for both: its +/-13.5 V swing is the very limit the booster exists to pass, and its 10 MHz would hide whether the two loops are stable at the parts' real speeds
- Rejected model slew rate and output current limit too: the bench's macro-model has neither; the table's 2.4 V/us and 10 A are recorded here and not simulated

### system.load (`DEC-bf109e8b1fc8`)

**What does E_O drive?** → 10 Ohm to ground, so 30 V out is 3 A, well past the OPA277's 5 mA

- the figure draws no load
- Rejected no load: a power stage with nothing to drive shows nothing a single OPA277 could not do, except swing
- Rejected a lower resistance, near the 10 A the table allows: the macro-model has no current limit, so a heavier load would prove nothing more

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> G = +21. The compound amplifier: V_OS 20 uV, V_OUT +/-35 V, I_OUT 10 A (Table 1). The 47pF capacitor provides a small amount of phase shift to help stabilize the system.

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 72, Power Booster (Table 1, Compound Amplifier, Resulting Performance).
