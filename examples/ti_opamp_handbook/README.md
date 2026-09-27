# ti_opamp_handbook

Every circuit in TI's [SBOA092B, *Handbook of Operational Amplifier
Applications*](https://www.ti.com/lit/an/sboa092b/sboa092b.pdf) (Carter and
Brown, revised 2016), written in fang and simulated in ngspice through
`fang.simulation`. That is 72 circuits from the handbook's circuit collection
(pages 49 to 91) plus the fully clamped comparator of Figure 54. Each one is an
example folder of its own. This folder groups them and is not itself an example.

**73 circuits, 339 claims, every one holding in simulation.** About a third of
the pages print something the drawn circuit does not do, and each of those is
written down in the circuit's README under "Where the handbook is off".

## How a circuit is written

Each program says three things:

- **The circuit.** It is drawn with the parts in [`handbook.py`](handbook.py):
  an op amp, terminals, the ground, diodes, potentiometers, switches, meters
  and cells.
- **The claims.** These are parameters of the system, tied to the parts by
  constraints, so `fang check` fails the moment a value and its claim disagree.
- **What the program had to decide.** Many figures are symbolic, and some are
  ambiguous or misprinted. Each such decision is recorded as a `Chooses` with
  the alternatives it rejected, and the handbook's printed claim is quoted as
  a `Cites`.

The page is the citation. The simulation is the arbiter.

## How it is simulated

A program declares a `BENCH`. Its runs are what `examples/regenerate.py` runs
when it writes the example's `out/`. Each run:

1. Compiles a plan and lowers the snapshot to SPICE with `fang.simulation`.
   fang writes the resistors, capacitors, inductors and cells itself, and names
   every other part as abstracted, which puts it in the plan's assumptions.
2. Adds a card for each abstracted part: the op amp's macro-model (one pole,
   clamped swing, offset), a 1N4148 or a zener, a potentiometer's two halves,
   a switch. It also adds the drive the figure implies but does not draw.
   Node numbers come from `spice_nodes`, the function the deck was written
   with.
3. Runs ngspice across a process boundary and reads its measurements.
4. Checks each measurement against a claim. Where a claim names a system
   parameter, the value is read from the snapshot, so the number checked is
   the one the graph holds.

What each circuit's `out/` adds to the usual files:

| File | What it is |
| --- | --- |
| `views/interconnect.svg` | fang's interconnect view, with the parts named as the program names them |
| `spice/<run>.cir` | The deck ngspice ran: fang's lowering, then the bench's cards |
| `simulation.txt` | Each measurement against its claim, and what the plan abstracted |

The default op amp is close to ideal: 120 dB of gain, 10 MHz of gain-bandwidth,
±13.5 V of swing and no offset. The handbook's algebra is therefore what a run
measures, and where a real limit is the point of the circuit it shows up.
Examples are the differentiator's peaking, the chopper's offset, and the power
booster's two parts. A circuit whose point depends on a real part sets that
part's numbers and records where they came from.

[`tests/test_handbook.py`](../../tests/test_handbook.py) fails if any committed
`simulation.txt` reports a claim that does not hold.
[`tests/test_examples.py`](../../tests/test_examples.py) rebuilds every
`out/` and compares it, so a committed result cannot drift from its program.

## How it is drawn

Each circuit's schematic is drawn by [copperhead](https://github.com/copperheadhq/copperhead)'s
drafting engine, not by fang, and sits in `figure/` beside `out/`:

| File | What it is |
| --- | --- |
| `figure/schematic.intent.json` | The circuit's netlist, with each part given the KiCad symbol that draws it |
| `figure/<name>.kicad_sch` | The sheet copperhead drew from it |
| `figure/schematic.svg` | KiCad's render of that sheet, shown in the circuit's README |

[`draw_figures.py`](../draw_figures.py) writes all three. It maps each kind of part to a KiCad
library symbol (the table is `SYMBOLS` in it), hands copperhead the result,
and writes the sheet only if KiCad reads back from it exactly the connections
the circuit has. Copperhead is not a dependency of fang, so `draw_figures.py` is
not part of `regenerate.py`; it needs a copperhead checkout (`COPPERHEAD_DIR`) and
`kicad-cli`. The drawings here come from copperhead at `acf53d8` on
`fix/draft-handbook-legibility`, with that branch's uncommitted edits to the
drafting engine, which draw an inverting stage the way a textbook does.
[`tests/test_handbook.py`](../../tests/test_handbook.py) fails if a circuit's
program no longer matches the intent its drawing was made from.

## The circuits

| Section | Circuit | Page | Claims | Handbook off? |
| --- | --- | ---: | ---: | --- |
| Comparators | [`clamped_comparator`](comparators/clamped_comparator/) | 47 | 7 | threshold ratio inverted; clamps ignore the diode drop |
| Buffers | [`voltage_follower`](buffers/voltage_follower/) | 49 | 3 | |
| | [`inverting_buffer_adjustable_gain`](buffers/inverting_buffer_adjustable_gain/) | 50 | 3 | |
| | [`balanced_output`](buffers/balanced_output/) | 50 | 7 | "4E_I p-p" holds only with E_I as a peak |
| References | [`isolated_standard_cell`](references/isolated_standard_cell/) | 51 | 3 | |
| | [`constant_current_generator`](references/constant_current_generator/) | 51 | 5 | op amp inputs drawn swapped; R1 formula; "R_L min" is a maximum |
| | [`buffer_variation`](references/buffer_variation/) | 52 | 3 | |
| | [`presettable_voltage_source`](references/presettable_voltage_source/) | 52 | 5 | |
| | [`reference_voltage_supply`](references/reference_voltage_supply/) | 52 | 3 | |
| Basic amplifiers | [`noninverting_amplifier`](basic_amplifiers/noninverting_amplifier/) | 53 | 2 | |
| | [`inverting_amplifier`](basic_amplifiers/inverting_amplifier/) | 54 | 2 | |
| Integrators | [`integrator`](integrators/integrator/) | 55 | 4 | |
| | [`simple_integrator`](integrators/simple_integrator/) | 56 | 2 | |
| | [`zeroed_integrator`](integrators/zeroed_integrator/) | 56 | 6 | C_O printed as 1 mF |
| | [`regenerative_integrator`](integrators/regenerative_integrator/) | 57 | 3 | |
| | [`summing_integrator`](integrators/summing_integrator/) | 58 | 2 | |
| | [`double_integrator`](integrators/double_integrator/) | 58 | 7 | drawn values break the page's rule: -50, not -4 |
| | [`differential_integrator`](integrators/differential_integrator/) | 59 | 2 | E_I for E_1 in the formula |
| | [`ac_integrator`](integrators/ac_integrator/) | 59 | 8 | |
| | [`augmenting_integrator`](integrators/augmenting_integrator/) | 60 | 2 | integral term is 10x, not 1x |
| Differentiators | [`differentiator`](differentiators/differentiator/) | 61 | 4 | |
| | [`differentiator_with_stop`](differentiators/differentiator_with_stop/) | 61 | 5 | corners printed 0.6 kHz / 16 kHz; they are 1.59 kHz / 15.9 Hz |
| | [`low_noise_differentiator`](differentiators/low_noise_differentiator/) | 62 | 4 | |
| | [`augmented_differentiator`](differentiators/augmented_differentiator/) | 62 | 5 | |
| Summers | [`voltage_summer`](summers/voltage_summer/) | 63 | 7 | |
| | [`adder`](summers/adder/) | 64 | 5 | |
| | [`scaling_adder`](summers/scaling_adder/) | 64 | 7 | a stray leading -100 |
| | [`direct_addition`](summers/direct_addition/) | 65 | 6 | |
| | [`averager`](summers/averager/) | 65 | 4 | |
| | [`weighted_average`](summers/weighted_average/) | 66 | 5 | 5.45 truncated to 5.4; the output is -E_I, not E_I |
| Differential input | [`differential_input_amplifier`](differential_input/differential_input_amplifier/) | 67 | 4 | |
| | [`adder_subtractor`](differential_input/adder_subtractor/) | 68 | 6 | |
| | [`balanced_output_amplifier`](differential_input/balanced_output_amplifier/) | 69 | 3 | |
| DC amplifiers | [`simple_inverting`](dc_amplifiers/simple_inverting/) | 70 | 3 | bias resistor named, not drawn |
| | [`chopper_stabilized`](dc_amplifiers/chopper_stabilized/) | 70 | 3 | |
| | [`simple_gain_control`](dc_amplifiers/simple_gain_control/) | 70 | 10 | |
| | [`linear_gain_control`](dc_amplifiers/linear_gain_control/) | 71 | 7 | |
| | [`simple_non_inverting`](dc_amplifiers/simple_non_inverting/) | 71 | 5 | |
| | [`power_booster`](dc_amplifiers/power_booster/) | 72 | 8 | |
| | [`differential_output`](dc_amplifiers/differential_output/) | 73 | 3 | a difference amp, not a floating-load driver |
| | [`gain_control`](dc_amplifiers/gain_control/) | 73 | 5 | |
| | [`inverting_gain_control`](dc_amplifiers/inverting_gain_control/) | 73 | 11 | |
| Differential amplifiers | [`subtractor`](differential_amplifiers/subtractor/) | 74 | 3 | |
| | [`difference_amplifier`](differential_amplifiers/difference_amplifier/) | 74 | 3 | |
| | [`common_mode_rejection`](differential_amplifiers/common_mode_rejection/) | 75 | 6 | as drawn no trim can null it; read R1 as 10 kΩ |
| | [`differential_input_output`](differential_amplifiers/differential_input_output/) | 75 | 3 | |
| AC amplifiers | [`simple_ac_amplifier`](ac_amplifiers/simple_ac_amplifier/) | 76 | 4 | |
| | [`single_supply`](ac_amplifiers/single_supply/) | 76 | 6 | |
| | [`ac_non_inverting`](ac_amplifiers/ac_non_inverting/) | 77 | 6 | the printed corner is not the one that dominates |
| | [`double_rolloff`](ac_amplifiers/double_rolloff/) | 77 | 5 | drawn values break C1R1 = C2R2: +9.3 dB peak |
| | [`ac_preamplifier`](ac_amplifiers/ac_preamplifier/) | 78 | 6 | gain is 509 to 546, not 500; corner 0.8 Hz, not 1.6 |
| Current output | [`feedback_loop`](current_output/feedback_loop/) | 79 | 7 | |
| | [`simple_meter_amplifier`](current_output/simple_meter_amplifier/) | 79 | 2 | |
| | [`meter_amplifier`](current_output/meter_amplifier/) | 80 | 2 | a two-diode bridge reads 0.45 E_rms, not 0.9 |
| | [`current_injector`](current_output/current_injector/) | 80 | 3 | I = -E_I/R2, not -E_I/R_L |
| | [`linear_current_source`](current_output/linear_current_source/) | 81 | 5 | |
| | [`deflection_coil_driver`](current_output/deflection_coil_driver/) | 82 | 3 | -100.1 mA/V: the load also carries E_I/R1 |
| Oscillators | [`simple_oscillator`](oscillators/simple_oscillator/) | 83 | 3 | |
| | [`wien_bridge_oscillator`](oscillators/wien_bridge_oscillator/) | 83 | 8 | the lamp regulates only near 55 V peak |
| Lead and lag | [`lag_element`](lead_lag/lag_element/) | 84 | 3 | drawn R_O/R_I is 0.01, not 10 |
| | [`adjustable_lag`](lead_lag/adjustable_lag/) | 84 | 8 | |
| | [`linear_lag`](lead_lag/linear_lag/) | 85 | 4 | |
| | [`adjustable_lead`](lead_lag/adjustable_lead/) | 85 | 5 | formula drops the 1 |
| | [`lead_lag`](lead_lag/lead_lag/) | 86 | 4 | formula drops the minus sign |
| | [`time_delay`](lead_lag/time_delay/) | 86 | 4 | |
| Additional | [`absolute_value`](additional/absolute_value/) | 87 | 9 | as drawn the op amp saturates |
| | [`peak_follower`](additional/peak_follower/) | 87 | 4 | holds a diode drop below the peak |
| | [`precision_rectifier`](additional/precision_rectifier/) | 88 | 4 | |
| | [`ac_to_dc_converter`](additional/ac_to_dc_converter/) | 88 | 2 | |
| | [`full_wave_rectifier`](additional/full_wave_rectifier/) | 89 | 6 | as drawn it gives -\|E_I\| |
| | [`rate_limiter`](additional/rate_limiter/) | 89 | 4 | 7.27 V/s, not 7.5: a diode drop |
| | [`time_delay_relay`](additional/time_delay_relay/) | 90 | 5 | delay formula runs about 5% long |
| | [`selective_amplifier`](additional/selective_amplifier/) | 91 | 3 | 965 Hz, not 1000; gain 31.3, not 33 |

The handbook's theory chapters draw more figures (Figures 10 to 53). Most are
the same circuits with symbolic parts, used to explain Bode plots and
stability, and so they are not repeated here. Figure 54 is the one with a full
set of values, and it is the comparator above.

## Running it

```bash
fang check examples/ti_opamp_handbook/summers/scaling_adder/scaling_adder.py
python examples/regenerate.py ti_opamp_handbook/summers/scaling_adder   # needs ngspice
python examples/draw_figures.py scaling_adder                             # needs copperhead and kicad-cli
python -m pytest tests/test_handbook.py
```
