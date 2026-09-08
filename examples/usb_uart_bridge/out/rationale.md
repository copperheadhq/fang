# usb_uart_bridge — rationale

Every line below is an entity in the elaborated graph, projected by
`python examples/regenerate.py`. Nothing here is prose kept beside the
design; it is the design.

## Requirements

### system.bus_powered — `REQ-b7a9b0b97172`

> The board draws no more than 100 mA before USB enumeration

MUST, state KNOWN, validation by analysis.

- No verification closes this requirement yet.

## Decisions

### system.bridge_choice — `DEC-84d581f8693d`

**Which USB-UART bridge?** → CH340C

- integrated clock removes the crystal from the BOM on the -C variant
- known driver support on all three host operating systems
- Rejected FT232RL: four times the unit cost at this volume
- Rejected CP2102N: needs an external oscillator we would pay for
- Serves `system.bus_powered` (`REQ-b7a9b0b97172`)

## Evidence

### system.dp_pullup_value — `EVD-7ad910c95ff6`

> A full-speed device signals its speed with 1.5k from D+ to 3.3 V

Cited from SRC-USB-2.0, section 7.1.5.1.
