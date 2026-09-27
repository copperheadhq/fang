# linear_gain_control

SBOA092B page 71, *Linear Gain Control*: an inverting amplifier with R_I
10 kΩ in and a 100 kΩ potentiometer wired as a rheostat across it, its wiper
tied to the end at the output.

```
E_O = 0 to -10 E_I
Z_in = R_I = 10 kΩ
```

## The circuit

![the schematic, drawn by copperhead from the circuit's netlist](figure/schematic.svg)

The schematic is drawn by [copperhead](https://github.com/copperheadhq/copperhead)'s
drafting engine from this circuit's netlist, with KiCad's own library symbols,
and it opens in KiCad as [`figure/linear_gain_control.kicad_sch`](figure/linear_gain_control.kicad_sch).
The op amp is KiCad's generic one, since the handbook's are ideal, and each
terminal is a test point named as the program names it. KiCad reads back from
the sheet exactly the connections the circuit has; `draw.py` refuses to write
one that does not.

![the interconnect view, fang's own projection](out/views/interconnect.svg)

The interconnect view is fang's own projection. It names the parts as the
program does, so it reads against the code below.

## What the program says

The rheostat puts the setting times 100 kΩ in the loop, so the gain is -10
times the setting, a straight line. The figure gives no setting, so the
program records one decision (`rheostat`): the setting counts from the
summing-point end, and the claims are held at full travel, the printed -10.
Two constraints tie the claims to the parts:

```python
require(equals(self.a_v, negative(over(product(self.r_out.setting, self.r_out.resistance), self.r_in.resistance))))
require(equals(self.z_in, self.r_in.resistance))
```

## What the simulation found

[`out/simulation.txt`](out/simulation.txt), from the decks under
[`out/spice/`](out/spice/), each an operating point with E_I = 1 V:

| Setting | Gain | Z_in | Claimed |
| --- | ---: | ---: | --- |
| 1 (full travel) | -10 | 10 kΩ | -10 (`a_v`), 10 kΩ (`z_in`), hold |
| 0.75 | -7.5 | | -7.5, holds |
| 0.5 | -5 | | -5, holds |
| 0.25 | -2.5 | | -2.5, holds |
| 0 | E_O = -100 nV | 10 kΩ | 0 V, 10 kΩ, hold |

The gain is linear in the setting and Z_in does not move, which is the
difference from the simple gain control before it on page 70. At the bottom
of the range only the model's 1 mΩ wiper contact is in the loop.

## Running it

```bash
fang check examples/ti_opamp_handbook/dc_amplifiers/linear_gain_control/linear_gain_control.py
python examples/regenerate.py ti_opamp_handbook/dc_amplifiers/linear_gain_control   # needs ngspice
```
