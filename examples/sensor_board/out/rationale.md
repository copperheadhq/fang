# sensor_board — rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Decisions

### connection.0007.line.right — `DEC-0402724fb97e`

**Which pin of `system.mcu` carries electrical.line?** → `system.mcu.PB8` (`PIN-6093c2974cd4`)

- first candidate in the part's declared preference order that was not already assigned within this lowering
- Rejected alternative: a higher-preference candidate was available

### connection.0003.sda.left — `DEC-153411794df9`

**Which pin of `system.mcu` carries i2c.sda?** → `system.mcu.PB9` (`PIN-55f9f908a69a`)

- first candidate in the part's declared preference order that was not already assigned within this lowering
- Rejected alternative: a higher-preference candidate was available

### connection.0003.scl.left — `DEC-d9ddc2ea2268`

**Which pin of `system.mcu` carries i2c.scl?** → `system.mcu.PB8` (`PIN-6093c2974cd4`)

- first candidate in the part's declared preference order that was not already assigned within this lowering
- Rejected alternative: a higher-preference candidate was available

### connection.0009.line.right — `DEC-e032d230dbb4`

**Which pin of `system.mcu` carries electrical.line?** → `system.mcu.PB9` (`PIN-55f9f908a69a`)

- first candidate in the part's declared preference order that was not already assigned within this lowering
- Rejected alternative: a higher-preference candidate was available
