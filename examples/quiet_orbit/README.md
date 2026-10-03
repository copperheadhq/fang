# quiet_orbit

copperhead's Quiet Orbit QO-R1, a four-light USB lamp on an ATtiny84A, and its
own firmware run against it in simavr. Read it after
[`sensor_node/`](../sensor_node/), which runs firmware in Renode: Renode models
no AVR core, so this board's questions route to fang's second emulator, and
they find a defect nobody had seen, because the firmware had never been
compiled, let alone run.

## The board

QO-R1 ([copperheadhq/copperhead-quiet-orbit](https://github.com/copperheadhq/copperhead-quiet-orbit)
at `056933b`) is a 57 mm board designed with copperhead: four amber LEDs at
the corners of a 40 mm square, each sunk by one of the ATtiny84A's four
hardware-PWM outputs through a 680 ohm resistor from VCC, fading on four
phases. It is powered from a power-only USB-C receptacle through a 100 mA
polyfuse and a 1N4148W reverse blocker, and programmed through a six-pin AVR
ISP header, two of whose lines are shared with LEDs. It has never been built.

[`quiet_orbit.py`](quiet_orbit.py) is QO-R1's schematic intent and bill of
materials, part for part and net for net: all 16 of its nets, with the same
members. fang assigns its own reference designators, so they differ from
QO-R1's (its D2 to D5 are DS1 to DS4 here, for instance). The connectors are
reduced to one pin per function: the receptacle's four VBUS and four GND
contacts and its shell are joined on the board, and its D+, D- and SBU contacts
are not connected.

The ATtiny84A's part declares its SOIC-14 pins and names each compare output by
the light it drives, `led_nw` on PB2 (OC0A), `led_ne` on PA7 (OC0B), `led_se` on
PA6 (OC1A, also MOSI) and `led_sw` on PA5 (OC1B, also MISO), cited from
Microchip's DS40002269A: the pinout, the ports' alternate functions, and how
the part ships.

## The firmware, run against the board

[`firmware/qo-r1/`](firmware/qo-r1/) is QO-R1's firmware as published, under
its own licence, GPL-3.0-only (see [`firmware/README.md`](firmware/README.md)).
It runs Timer/Counter0 and Timer/Counter1 in 8-bit fast PWM at clk/64 and fades
each LED through a 256-step triangle, a step every 4 ms, the four a quarter
cycle apart. It assumes an 8 MHz clock: `F_CPU` is 8 MHz, and it checks so at
compile time. The ELF in [`firmware/elf/`](firmware/elf/) is that firmware's
first build, and `make` in `firmware/` rebuilds it byte for byte.

The part's emulation model is fang's ATtiny84A platform, which runs on simavr.
An ATtiny84A's clock is set by its fuses, so the model will not plan a run
until they are stated. QO-R1's README says to change the clock-divide fuse if
the part ships with it set, so the board binds the firmware with the low fuse
0xE2, the 8 MHz oscillator undivided:

```python
Firmware("firmware/elf/quiet-orbit-qo-r1.elf", target="attiny84a", fuses={"low": 0xE2})
```

Two questions run it for 2 s and take the same measures: NW's rising edges
between 1 s and 2 s, which are its PWM rate, and for each LED the fraction of a
16 ms window its pin is low, which is how lit it is, at the time it should be
brightest, a quarter cycle apart:

```python
"pwm_rises": Count(Rises("mcu.led_nw"), within=(1 * s, 2 * s)),
"ne_lit": Duty("mcu.led_ne", level=0, within=(257 * ms, 273 * ms)),
```

- **orbit**, with the fuse set: NW's PWM is within 5 % of the firmware's
  8 MHz / 64 / 256 = 488 Hz, and each LED is at least 90 % lit at its peak.
  It passes: 489 edges a second, each LED 98.4 % lit, SE, NE, NW and SW in turn.
- **as_shipped**, the same firmware on a part with the fuses it ships with
  (`fuses="factory"`). The ATtiny84A ships with its clock divided by eight,
  and nothing in QO-R1's build programs the fuse, so a lamp flashed over ISP
  and nothing else runs at 1 MHz. It fails: 60 edges a second, a PWM slow
  enough to flicker, and a fade eight times as slow, so at the times NE, NW
  and SW should be brightest they are 55 %, 13 % and 32 % lit.

The fix is either half of QO-R1's own README: program the low fuse 0xE2 as part
of the factory flash, or have the firmware undo the division itself with
`clock_prescale_set(clock_div_1)` from `<avr/power.h>` before it starts the
timers. simavr does not model the clock prescaler, so fang's runner does, by
the timed sequence the datasheet gives; the suite checks it with a firmware
that makes the change.

Neither question asserts an LED dark. simavr holds a fast-PWM output at its
compare-match level for a period whose compare value is TOP, where the part
holds it at its other level, so the instant an LED should go dark it lights for
one PWM period. That and the other differences from the part are listed with
every run:

- a write to a compare register takes effect at once, where the part buffers it
  to the end of the PWM period;
- a prescaler change takes effect at the write, where the part takes a cycle or
  two of each clock;
- simavr warns once per timer that it has no mode when QO-R1's firmware writes
  a compare register before starting its timers; the value is stored as on the
  part, so the warning is expected and withdraws nothing;
- the LEDs and the ISP header share nets with the pins the questions observe,
  have no emulation model, and are abstracted;
- the oscillator is taken to run at its nominal 8 MHz, and time zero is the
  first instruction, 64 ms after the part leaves reset with these fuses.

A pass is a finding on a model tested in emulation, at confidence 0.8. It is not
the lamp working.

## What comes out

23 parts, 16 nets, 237 entities, 15 checks. None failed, **twelve undecided**:
the constraints over what the firmware does, until a run measures them.

- [`out/quiet_orbit.net`](out/quiet_orbit.net), [`out/netlist.txt`](out/netlist.txt)
- [`out/checks.txt`](out/checks.txt): 15 checks, twelve of them undecided
- [`out/verification.txt`](out/verification.txt): what `fang verify` found,
  `orbit` passing and `as_shipped` failing
- [`out/simavr/`](out/simavr/): each question's plan and the configuration
  fang's runner reads
- [`out/rationale.md`](out/rationale.md): the two requirements, the questions
  and the citations
- [`out/graph.txt`](out/graph.txt): 237 entities

![the interfaces view](out/views/interfaces.svg)

The MCU's links: its four compare outputs to the LEDs, MOSI and MISO shared
with SE and SW on the ISP header, SCK and RESET to the header and the reset
pull-up, and the CC terminations on the receptacle.

![the power view](out/views/power.svg)

VBUS from the receptacle to the polyfuse, its input capacitor and test point;
VCC from the blocker to the MCU and the header's sense pin.

## Running it

```bash
fang check   examples/quiet_orbit/quiet_orbit.py
fang netlist examples/quiet_orbit/quiet_orbit.py
fang verify  examples/quiet_orbit/quiet_orbit.py     # needs simavr 1.8 and a C compiler
fang emulate examples/quiet_orbit/quiet_orbit.py --bundle-only -o bundles
make -C examples/quiet_orbit/firmware                 # needs avr-gcc and avr-libc
```

simavr is found by its `simavr` executable, with its headers and library
installed beside it; fang builds its runner against them for each run. Ubuntu's
simavr package is 1.6, which wires the ATtiny84's compare outputs to the wrong
pins, and is refused; build 1.8 from source with `make install`.
