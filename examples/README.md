# Examples

Eight programs, smallest first. Each one is a folder: the program, a document
explaining what it is for, and the files `fang` produces from it under `out/`.
Every one of them elaborates, passes the gate, and is built by
[`tests/test_examples.py`](../tests/test_examples.py) on every run, so none of
them is a sketch that no longer works.

| Example | Shows | Parts | Nets |
| --- | --- | ---: | ---: |
| [`divider/`](divider/) | The smallest real board: two resistors and a capacitor | 4 | 2 |
| [`blinky/`](blinky/) | Declared surfaces, connections, and a constraint that states intent | 6 | 4 |
| [`equations/`](equations/) | Values chosen by equation, and reuse by inheritance | 7 | 6 |
| [`sensor_board/`](sensor_board/) | Interfaces lowering to pins, a recorded decision, a check left undecided | 7 | 4 |
| [`i2c_bus/`](i2c_bus/) | A multi-drop bus, addresses as constrained parameters | 9 | 4 |
| [`usb_uart_bridge/`](usb_uart_bridge/) | Part selection: manufacturer, MPN, distributor, datasheet | 17 | 11 |
| [`buck_regulator/`](buck_regulator/) | Requirement, decision, calculation and verification beside the circuit | 12 | 9 |
| [`servo_drive/`](servo_drive/) | Composition: one `HalfBridge` instantiated three times | 24 | 26 |

Two folders here are not programs: [`imported/`](imported/) is a KiCad netlist
read *into* the kernel, and [`parity/`](parity/) is an atopile project built
against two of these boards to compare the two toolchains.

## What is in an `out/`

| File | What it is | Command |
| --- | --- | --- |
| `<name>.net` | The KiCad netlist — the artifact a layout tool opens | `fang export` |
| `netlist.txt` | The same projection as text: parts, then nets and their pads | `fang netlist` |
| `checks.txt` | Every check that ran, and every one left undecided | `fang check` |
| `graph.txt` | What the elaborated graph contains, by entity kind | `fang graph` |
| `views/*.svg` | The views worth looking at for this board | `fang view` |
| `rationale.md` | The requirements, decisions, calculations and evidence in the graph | — |

`rationale.md` is the one file with no command behind it. It is a projection of
the reasoning entities, rendered by the script below, and it exists only for the
examples that record any — a divider has nothing to explain.

## Running one

```bash
fang check   examples/sensor_board/sensor_board.py
fang netlist examples/sensor_board/sensor_board.py
fang export  examples/sensor_board/sensor_board.py -o sensor_board.net
fang view    examples/sensor_board/sensor_board.py ground -o ground.svg
fang build   examples/sensor_board/sensor_board.py   # elaborate, gate, persist, run the plan
```

## Rebuilding the outputs

```bash
python examples/regenerate.py            # every example
python examples/regenerate.py divider    # one of them
```

The committed outputs are built in the project namespace `PRJ-EXAMPLES`, which
is where the identifiers in them come from; a local `fang build` defaults to
`PRJ-LOCAL` and derives its own. Two details in the files do not follow from the
design — the compiler version, which moves on release, and the snapshot hash,
which covers provenance and so covers the path this checkout sits at. The test that
compares committed outputs against freshly built ones normalizes exactly those
two and nothing else.
