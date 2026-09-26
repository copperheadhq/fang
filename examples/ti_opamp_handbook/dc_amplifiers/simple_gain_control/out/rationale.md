# simple_gain_control: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.setting (`DEC-091f1d56fe0f`)

**Where is the wiper?** → at the centre by default, where the page says the gain is unity; the bench moves it to 0.1, 0.25, 0.75 and 0.9 of the travel from the E_I end

- the pot's travel is its only adjustment, and the page names none
- Rejected one fixed setting only: the page's claims are about how gain and Z_in move with the setting, which one setting cannot show
- Rejected the wiper at either end: at the E_I end the gain is unbounded and the op amp saturates; at the E_O end the input is shorted to the summing point and the gain is 0 with a 10 kOhm load on the output

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> Wide range gain or attenuation. Unity gain with R centered. The gain is not linear with potentiometer setting. Zin drops as gain is increased. (Pot drawn as 10 kW)

Cited from SBOA092B, Handbook of Operational Amplifier Applications, pages 70 and 71, Simple Gain Control.
