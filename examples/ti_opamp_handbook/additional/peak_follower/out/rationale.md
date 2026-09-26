# peak_follower: rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### system.drop (`DEC-a7acbc148b84`)

**What forward drop does the held value lose to the diode?** → 0.5 V, the 1N4148's drop at the tens of microamps still charging the capacitor when the peak ends, claimed to 0.1 V

- the handbook draws a plain diode and names no part; the bench uses the 1N4148 it names on page 47
- the drop depends on how the input approaches its peak, so the claim is a band, not a number
- Rejected none, as the page's E_O = E_I maximum says: the diode is outside the loop; its drop is in the held value, and the bench measures it
- Rejected 0.7 V, the textbook silicon drop: that is the drop at milliamps; the charging current has died to tens of microamps by the time the peak passes

## Evidence

### system.figure (`EVD-fe92fa0675d8`)

> Peak value memory. Use low leakage capacitor. E_O = E_I maximum. Common mode input voltage must be observed

Cited from SBOA092B, Handbook of Operational Amplifier Applications, page 87, Peak Follower.
