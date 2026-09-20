# Examples

Eleven programs, smallest first. Each one is a folder: the program, a document
explaining what it is for and the files `fang` produces from it under `out/`.
Every one elaborates, passes the gate and is built by
[`tests/test_examples.py`](../tests/test_examples.py) on every run, so none of
them is a sketch that no longer works.

| Example | Shows | Parts | Nets |
| --- | --- | ---: | ---: |
| [`divider/`](divider/) | The smallest real board: two resistors and a capacitor | 4 | 2 |
| [`blinky/`](blinky/) | Declared surfaces, connections and a constraint that states intent | 6 | 4 |
| [`equations/`](equations/) | Values chosen by equation, then reused by inheritance | 7 | 6 |
| [`sensor_board/`](sensor_board/) | Interfaces lowering to pins, a recorded decision, a check left undecided | 7 | 4 |
| [`i2c_bus/`](i2c_bus/) | A multi-drop bus, addresses as constrained parameters | 9 | 4 |
| [`usb_uart_bridge/`](usb_uart_bridge/) | Part selection: manufacturer, MPN, distributor and datasheet | 17 | 11 |
| [`buck_regulator/`](buck_regulator/) | Requirement, decision, calculation and verification beside the circuit | 12 | 9 |
| [`servo_drive/`](servo_drive/) | Composition: one `HalfBridge` instantiated three times | 24 | 26 |
| [`jee_advanced/problem_1/`](jee_advanced/problem_1/) | Not a board: four claimed currents, all four decided | 11 | 7 |
| [`jee_advanced/problem_2/`](jee_advanced/problem_2/) | Not a board either: one claimed current, and the two branches that carry none | 12 | 7 |
| [`noninverting_amp/`](noninverting_amp/) | Not a board: two midband answers, and the reading of the figure they rest on | 13 | 8 |

The last three are the odd ones out: eight boards, then two exam questions
and a textbook figure, because the kernel decides a claim about a circuit the
same way whichever it is. The two exam questions share a folder —
[`jee_advanced/`](jee_advanced/) groups them and is not itself an example,
which is why an example's name here is its path below `examples/` rather than
just a folder name.

Two folders here are not programs. [`imported/`](imported/) is a KiCad netlist
read *into* the kernel. [`parity/`](parity/) is an atopile project built against
two of these boards, to compare the two toolchains.

## What is in an `out/`

| File | What it is | Command |
| --- | --- | --- |
| `<name>.net` | The KiCad netlist, the artifact a layout tool opens | `fang export` |
| `<name>.kicad_sch` | The KiCad schematic, the sheet Eeschema opens | `fang schematic` |
| `schematic.svg` | KiCad's own render of that sheet | `fang schematic --svg` |
| `netlist.txt` | The same projection as text: parts, then nets and their pads | `fang netlist` |
| `checks.txt` | Every check that ran, and every one left undecided | `fang check` |
| `graph.txt` | What the elaborated graph contains, by entity kind | `fang graph` |
| `views/*.svg` | The views worth looking at for this board | `fang view` |
| `rationale.md` | The requirements, decisions, calculations and evidence in the graph | none |

`rationale.md` is the one file with no command behind it. It is a projection of
the reasoning entities, rendered by the script below, and only the examples that
record any reasoning get one. A divider has nothing to explain.

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

An example that ships a schematic needs `kicad-cli` on the path to regenerate,
because KiCad is what draws it. The two under `jee_advanced/` are the ones
that do.

The committed outputs are built in the project namespace `PRJ-EXAMPLES`, which
is where the identifiers in them come from. A local `fang build` defaults to
`PRJ-LOCAL` and derives its own.

Two details in the files do not follow from the design. The compiler version
moves on release, and the snapshot hash covers provenance, so it also covers the
path this checkout sits at. The test that compares committed outputs against
freshly built ones normalizes exactly those two and nothing else.
