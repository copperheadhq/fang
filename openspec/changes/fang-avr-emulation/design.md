# Design: A Second Emulator, for AVR Cores

## Context

See [proposal.md](proposal.md) for motivation. The normative text is copperhead
RFC 12 version 1.5 (Sections 4.1, 4.2, 4.4, 12.11 to 12.14, 16 and 17, and
Appendix B.14), on the branch `rfc12-avr-emulation` of
copperheadhq/copperhead-rfcs; this document is informative. Everything below
builds on `fang-emulation` (archived 2026-10-02), whose design holds for Renode
unchanged: the binding, the descriptors, `Emulates`, the plan, the event
schema `fang.events/v1`, the measures and the `renode` tool.

Today that machinery is Renode's alone in four places: `descriptors()` reads
only `fang/renode/models/`; `compile_plan` takes a target only from a
descriptor of kind `renode_platform`; `RenodeTool.covers` claims every
question whose method is `emulation`; and `fang emulate` and
`examples/regenerate.py` call `RENODE` by name. `route()` hands `covers` the
question and nothing else, and a `Question` is built from the dictionary
elaboration stores on the verification entity, so which engine a question
needs has to be in that dictionary.

The facts below were found by a spike on 2026-10-03, before any kernel code:
the Quiet Orbit QO-R1 firmware (copperheadhq/copperhead-quiet-orbit at
`056933b`), compiled for the first time and run in simavr under a hand-written
runner that logged every pin edge and every compare-register write by cycle,
held to what the firmware's source and the ATtiny84A datasheet predict.

### What simavr does and does not do

| Fact | Consequence for this design | Source |
| --- | --- | --- |
| simavr has no command-line bound on a run's length: `run_avr` loops until the core halts or crashes. | The stock front end cannot make a bounded, deterministic run. A runner linked against the library bounds the run in cycles. | `simavr/sim/run_avr.c` at v1.8 |
| simavr's native way to model a board is a C program linked against `libsimavr` that loads firmware and connects to IRQs (its `examples/board_*`). | That program is simavr's native input, as `.repl`/`.resc` are Renode's. fang ships one runner's source. | `examples/` at v1.8 |
| simavr is GPL-3.0-or-later; fang is Apache-2.0. RFC 12 Section 4.4 keeps linking and bundling decisions for the licence review. | fang never links simavr and distributes no binary linked against it: the runner's source is fang's, built on the host against the installed library, and run as its own process. | `COPYING`; `LICENSE`; RFC 12 Section 4.4 |
| **The 1.6 release maps the ATtiny24/44/84 compare outputs to PB0, PB1, PB1, PB2.** The part's are PB2, PA7, PA6, PA5. v1.7 (2021) fixed it. Ubuntu packages 1.6. | Under 1.6 three of QO-R1's four LEDs look dead and the fourth shows Timer 1's OC1B. 1.6 is refused by name, with the reason. | spike: 1.6 vs 1.8 traces; `cores/sim_tinyx4.h` at v1.6 and v1.7 |
| Fast PWM timing is right: 8 MHz / 64 / 256 = 488.28 Hz, on one 16 384-cycle grid, and every clean PWM period's on-time matches the compare value to the timer tick (1 191 of 1 195 per channel over 5 s). | Pin observations are trustworthy for PWM at the period level. | spike |
| **A compare write applies at once.** The part buffers OCRx in PWM modes and updates it at BOTTOM. 4 948 of 4 984 periods holding a write lie between the old and new duty; 36 glitch. | A coverage gap on every ATtiny84A run; a measure over a short window can be off by a period. | spike; datasheet Sections 11.5, 12.6 |
| **With OCRx = TOP in fast PWM, simavr holds the output at its compare-match level for the period;** the part holds it at its BOTTOM level ("constantly high or low", Section 11.7.3). For QO-R1 that lights a dark LED for one period per fade. | A coverage gap; the example's measures avoid asserting darkness. | spike; datasheet p. 81 |
| simavr models neither fuses nor `CLKPR`: the core runs at the frequency it is given, and a write to `CLKPR` is stored and ignored. | The plan takes the clock from the fuses, and the runner models `CLKPR`'s timed sequence and keeps time per segment. | `grep -ri clkpr simavr/` (none); spike |
| simavr gives no warning when firmware writes a register it does not model (`OSCCAL`, most of `PRR`). | The descriptor names those registers and the runner watches them. | `cores/sim_tinyx4.h` (only `PRTIM1` and the comparator's `PRADC` are wired) |
| The ATtiny x4 core models both ports with pin-change interrupts, Timer 0, Timer 1, the ADC, the analog comparator, the watchdog, INT0, the EEPROM, self-programming and the USI. | These are the descriptor's peripherals; nothing here needs another. | `cores/sim_tinyx4.c` |
| simavr's timer drives the compare-output IRQ whatever the pin's direction; the part drives the pin only when its DDR bit is set. | The runner records a pin's level only while the pin is an output, and records a pin made an input again as released. | spike; datasheet Section 11.5.3 |
| A version is reported as `CONFIG_SIMAVR_VERSION` in the installed `sim_core_config.h`: `"1.6"` for Ubuntu's, `"v1.8"` for a v1.8 build. `make install` puts `bin/simavr`, `include/simavr/`, `lib/libsimavr.{a,so}` under one prefix. | The backend finds simavr by its `simavr` executable, reads the headers and library beside it, and reads the version from that header. | v1.8 `Makefile`; Ubuntu `libsimavr-dev` 1.6 |
| `avr_global_logger_set` receives every log line with its level. | `LOG_ERROR` and `LOG_WARNING` lines become `model.warning` events; the rest go to the log. | `sim/sim_avr.h` at v1.8 |
| **simavr draws one value at random:** `avr_init` fills the core's device serial number from `getpid() + random()`. | Firmware that reads it would differ run to run. The runner seeds `random()` from the plan's seed before anything else and overwrites the serial number from it, which is the seed RFC 12 Section 12.12 has fixed first. | `sim/sim_avr.c:111-121` at v1.8 |
| Runs are deterministic: the same ELF and clock give byte-identical traces. 3 s of QO-R1 at 8 MHz takes 0.5 s of wall time. | Ten-run determinism is cheap to test. | spike |
| The QO-R1 firmware compiles under its own `-Wall -Wextra -Werror` with avr-gcc 14.3.0 and avr-libc 2.2.1: 246 bytes. Every one of 1 247 steps × 4 channels writes `255 − triangle(k + offset)`; a step is 32 102 or 32 103 cycles (4.013 ms); the fade is 1.027 s; the peaks run SE, NE, NW, SW. | The example's committed ELF and its questions' windows. | spike |

### What the ATtiny84A does

Microchip DS40002269A, *ATtiny24A/44A/84A Data Sheet Complete*, 2020:

| Fact | Locator |
| --- | --- |
| SOIC-14: 1 VCC, 2 PB0, 3 PB1, 4 PB3/RESET, 5 PB2 (OC0A), 6 PA7 (OC0B), 7 PA6 (OC1A/MOSI), 8 PA5 (OC1B/MISO), 9 PA4 (SCK), 10 PA3, 11 PA2, 12 PA1, 13 PA0, 14 GND | Figure 1-1, p. 8; Sections 10.3.1-10.3.2, pp. 66-70 |
| Shipped with CKSEL = 0010 (internal 8 MHz RC), SUT = 10 and CKDIV8 programmed: a 1.0 MHz system clock | Section 6.2.6, p. 36 |
| Low fuse default 0x62 (CKDIV8 bit 7, CKOUT 6, SUT1:0 5:4, CKSEL3:0 3:0); high fuse default 0xDF (RSTDISBL, DWEN, SPIEN, WDTON, EESAVE, BODLEVEL2:0); extended 0xFF (SELFPRGEN) | Tables 19-5, 19-4, 19-3, pp. 165-166 |
| CKSEL 0010 is the calibrated 8 MHz oscillator; 0100 the 128 kHz oscillator; 0000 an external clock | Table 6-1, p. 31; Table 6-4, p. 33 |
| SUT = 10 adds 14 CK + 64 ms from reset to the first instruction | Table 6-5, p. 33 |
| `CLKPR` at 0x26 (0x46): write CLKPCE = 1 with the other bits 0, then CLKPS within four cycles with CLKPCE = 0; division 2^CLKPS for CLKPS 0 to 8; CKDIV8 sets the initial CLKPS to 0011 | Section 6.5.2, pp. 37-38 |
| `OSCCAL` at 0x31 (0x51); `PRR` at 0x00 (0x20): PRTIM1 3, PRTIM0 2, PRUSI 1, PRADC 0 | Sections 6.5.1, 7.4.2; pp. 37, 43 |
| In fast PWM, OCR = MAX gives a constant output; OCRx is double buffered in PWM modes | Sections 11.5, 11.7.3, 12.8.3; pp. 77, 81, 97, 101 |

### Considered and set aside

| Option | Why not |
| --- | --- |
| **The stock `simavr` front end with VCD output** | No bound on a run's length; stopping it on wall-clock time makes the record's end host-timed. |
| **ctypes over `libsimavr.so`** | `avr_t` and `elf_firmware_t` are large structs whose layout moves between releases; a build against the installed headers cannot misread them. It would also load GPL code into a Python process that fang's own code shares. |
| **Linking simavr into fang** | RFC 12 Section 4.4: no linking decision before the licence review, and a process boundary where practical. |
| **simavr 1.6, as distributions package it** | Wrong compare-output pins on the ATtiny x4 (above). |
| **Correcting simavr's PWM departures in the runner** | The runner would then model the part rather than drive the engine, and fang would own a second timer model. Each departure is a coverage gap; a fix belongs upstream. |
| **QEMU** (`qemu-system-avr`) | Models ATmega boards (the Arduino Uno's ATmega328P and its kin), not the ATtiny84A. |
| **simulavr** | Models no ATtiny24/44/84: its tinyAVRs are the ATtiny2313 and ATtiny25/45/85. |
| **Wokwi** | A hosted product; not a local backend under a licence fang can name. |
| **One `emulation` tool dispatching to engines inside** | The route and the evidence would name "emulation" rather than the engine that ran, and RFC 12 Section 12.8 has the tool recorded on the verification. |
| **`Emulates(tool="simavr")` written by the author** | Restates what the platform model already says, and a question that forgets it would route to Renode and be refused there. |

## Goals / Non-Goals

**Goals:**

- One AVR part, the ATtiny84A, run end to end: descriptor, fuses, runner,
  backend, measures, the QO-R1 example and AT-F3.
- Renode's plans, bundles and jobs byte-identical to today's, so no recorded
  Renode measurement goes stale with this change.
- Everything but the run testable without simavr: the plan, the lowering, the
  flash image and the measures, against recorded event files.

**Non-Goals:**

- No other AVR part. The descriptor schema admits one per part; adding the
  ATtiny85 or an ATmega is data plus a pin table.
- No AVR bus in scope: the descriptor declares no peripheral instances, so an
  I2C port of an AVR target is refused as the plan refuses any bus its
  platform does not have. USI-based I2C is a later change.
- No stimuli or faults on AVR pins; no peripheral models beside the AVR.
- No correction of simavr's departures from the part; no start-up delay
  modelled.
- No reproducible firmware build: the ELF is committed with the toolchain that
  built it, as `sensor_node`'s is (RFC 12 Appendix C.2, open decision 15).

## Decisions

### A question records its engine; each tool covers its own

A platform descriptor gains `"engine": "renode" | "simavr"`, and the shipped
F401 descriptor says `"renode"`. `Emulates.question_fields(module)` walks the
module's parts while the tree is in hand, as surfaces are resolved, takes the
part whose `EmulationModel` names a platform descriptor and that carries a
`Firmware` binding (or the one platform part, if only one has a platform
model), and records `"engine"` in the question. A part whose descriptor is not
shipped records nothing, and the plan then refuses it as it does today.
`EmulationTool.covers(question)` is `question.method == "emulation" and
question.data.get("engine", "renode") == self.name`: a question recorded
before engines were is Renode's, since every one was. `compile_plan` checks the
recorded engine against the target it resolves and refuses a mismatch, so the
dictionary cannot route a question to an engine its target's model does not
name.

Recording the engine adds a key to every emulation question's dictionary, so
`sensor_node`'s verification entities change and so does its snapshot hash,
which the examples normalize. The plan does not carry the question
dictionary, so its hash does not move. The job's manifest does carry it, as
`asks`, and would move with it, making every recorded Renode measurement stale
for a change that does not touch its run; but the manifest already names the
job's `tool`, which routing chose by the recorded engine and the plan holds to
it, so `asks` leaves `engine` out and the job keeps its hash. (Found by
comparing the `sensor_node` jobs against `d04aabc`: with `engine` in `asks`
both hashes moved.)

### Descriptors come from every engine package

`descriptors()` reads `models/*.json` from `fang.renode` and `fang.simavr`,
and refuses one id shipped twice. The ATtiny84A descriptor (`fang:attiny84a`,
kind `simavr_platform`) carries `engine`, `target` (`attiny84a`), `mcu`
(simavr's core name, `attiny84`), `flash_bytes` (8192), `pins` (vendor name to
`{port: "A"|"B", index}`), an empty `peripherals`, `clock`, `watched`,
`not_modelled`, `expected_warnings` (none), `qualification` (`tested in
emulation`) and `provenance`. `clock` holds the oscillators by CKSEL value,
the factory fuses, and which bits are modelled:

```json
"clock": {
  "fuses": {"low": "0x62", "high": "0xDF", "extended": "0xFF"},
  "modelled": {"low": "0xBF", "high": "0x00", "extended": "0x00"},
  "clock_select": {"fuse": "low", "mask": "0x0F",
                   "oscillators": {"0x2": 8000000, "0x4": 128000}},
  "divide_by_8": {"fuse": "low", "bit": 7},
  "start_up": "14 CK + 64 ms from reset with SUT = 10, not modelled",
  "prescaler_register": "0x46"
}
```

A fuse's bits outside `modelled` must equal the factory value. SUT is inside
the low fuse's mask because it changes only the start-up time, which is an
assumption whatever it is set to; CKOUT is outside it, since programmed it
puts the system clock on PB2, which nothing models. `watched` names `OSCCAL`
(0x51, every write) and `PRR` (0x20, bits 0x07).

One warning is expected, found by the first live run of QO-R1: simavr gives a
timer no mode until its control register is first written, where the part
resets to normal mode with its clock stopped, so the compare writes QO-R1's
`led_pwm_all_off` makes before starting the timers log `TIMER:
avr_timer_write_ocr-0 mode 0 UNSUPPORTED`. The value is stored, as on the part
(`avr_timer.c`, `avr_timer_write_ocr`), so the descriptor expects the warning,
anchored, and names it as a coverage gap.

A platform kind is any kind ending `_platform`; the target search accepts both.

### The clock, from the fuses

Fuses are stated on `Firmware(path, target=, fuses=)` or
`Emulates(..., fuses=)`, the question's winning, as `"factory"` or a mapping
of `"low"`, `"high"`, `"extended"` to integers; a byte left out of a mapping is
the factory value. The plan refuses, with the new `SIM-0021`, a platform whose
descriptor declares `clock` and a question and binding that state no fuses; a
clock select with no oscillator in the table; a bit outside `modelled` that
differs from the factory value; and a fuse name the part does not have. It
records `clock = {oscillator_hz, prescaler, fuses: {low, high, extended},
source: "factory" | "binding" | "question", prescaler_register}` and the
assumptions: the core starts at `oscillator_hz / prescaler`, where the fuses
came from, that the oscillator runs at its nominal frequency (calibration is
not modelled), and that time zero is the first instruction, the start-up time
the fuses select not modelled. `core_clock_hz` is the starting frequency.

### The plan's schema moves only where the plan does

`EmulationPlan` gains `clock: Mapping | None = None`. `identity()` writes
`"clock"` only when it is set, as `PlanPin` writes `selector` only when set,
and a plan with a clock is written as `fang.emulation/v3`, one without as
`fang.emulation/v2`. `plan_from_dict` reads v1, v2 and v3 and keeps the schema
it read. A Renode plan therefore stays byte-identical and keeps its hash, and
a v2 consumer refuses an AVR plan by its label instead of misreading it. For
a simavr plan, `platform_file` and `recorder_port` are empty: there is no
platform file, and the runner records everything itself.

*Alternative considered:* every plan as v3. Simpler, and every recorded
Renode measurement would go stale for a change that does not touch it.

### The runner is simavr's native input

`fang/simavr/runner/fang_runner.c`, about 400 lines of C99 against
`sim_avr.h`, `sim_irq.h` and `avr_ioport.h`. It reads `run.cfg`, line by
line, each a keyword of a fixed set and its arguments:

```text
fang-simavr-run 1
mcu attiny84
oscillator_hz 8000000
prescaler 8
prescaler_register 0x46
seed 0
run_until_ns 2000000000
flash flash.bin
events events.jsonl
target COMP-1a2b3c4d5e6f
pin PORT-0123456789ab B 2
watch OSCCAL 0x51 0xFF
watch PRR 0x20 0x07
```

and refuses anything else. The lowering writes only these lines: keywords
from a fixed set, entity identifiers matched against
`[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}` (no quote, backslash, space or control
character can be in one), register names against `[A-Z][A-Z0-9]*`, integers,
and the bundle's own file names, so no program text reaches it; the runner
checks each again, since it is the side that writes them into JSON
unescaped. A model warning's text, which comes from simavr, is escaped.

The runner seeds `random()` from the configuration's seed before anything
else, makes the core by name, overwrites its serial number from the seed
(splitmix64, logged so a run's kept log shows it),
copies `flash.bin` into flash, sets the frequency, and runs `avr_run` until the virtual time reaches `run_until_ns`.
Virtual time is kept in segments: `t = t0 + (cycle − c0) × prescaler × 10⁹ /
oscillator_hz`, in 128-bit integers, floored; a prescaler change closes a
segment. Events, in `fang.events/v1` exactly as Renode's recorder writes them:

- `run.start` at 0, source `""`.
- `gpio.edge` `{level}` on an observed pin's IRQ while its DDR bit is set,
  only on a change; when the DDR bit is set, the pin's current level; and
  `gpio.release` `{}` when it is cleared. Source: the port entity the
  observation names.
- `clock.change` `{prescaler}` when a `CLKPR` write takes effect: a write of
  `0x80` opens a four-cycle window, and a write with CLKPCE clear and CLKPS
  0 to 8 within it sets the division; anything else is stored and changes
  nothing, as on the part. The register reads back what the part would. Source:
  the target.
- `model.warning` `{text}` for a watched register written with a watched bit
  set (`"PRR written 0x01: bits 0x07 are not modelled"`), and for every
  `LOG_ERROR` and `LOG_WARNING` line simavr logs. Source: the target.
- `run.end` `{reason: "completed"}` at `run_until_ns`, source `""`; a core that
  halts first (`cpu_Done`) ends the run with `run.end` `{reason: "halted"}` at
  that time, and a crash with none. The backend reads `halted` and `crashed` as
  runs that did not complete.

Writes to watched registers and `CLKPR` are caught by wrapping the handler the
core installed for that address (or installing one where none is), since
simavr shares at most four I/O registers between write hooks and its cores use
them.

### The flash image is cut from the ELF in Python

`fang/simavr/lowering.py` reads the ELF's program headers: it must be ELF32,
little-endian, `e_machine` 83 (AVR), and every `PT_LOAD` segment with a
physical address below 0x800000 is flash; one past the descriptor's
`flash_bytes` is refused. The image runs from 0 to the last loaded byte, gaps
erased to 0xFF. Segments in the fuse, lock and signature spaces (0x820000 on) are not
programmed. An EEPROM image (0x810000) is refused: nothing states that the
part's EEPROM is programmed with it and the runner does not program it, and
the plan, compiled before the firmware is read, has nowhere honest to record
that as an assumption. A segment that loads into RAM rather than into the
flash RAM is initialized from is refused too. Cutting it in Python
keeps the runner free of libelf and makes the image a pure function of the
firmware, tested without simavr. The bundle carries both `firmware.elf`, whose
digest is the evidence's, and `flash.bin`.

### The backend builds the runner and runs it

`SimavrBackend` finds `simavr` on the path, resolves the symlink, and takes
its prefix: `include/simavr/sim_avr.h` and a `libsimavr.so` or `libsimavr.a`
under `lib`, `lib64` or `lib/<multiarch>`. `available()` is the executable.
`identify()` reads the version from `sim_core_config.h` (stripping a leading
`v`) and the build as the first twelve hex digits of the library file's
SHA-256, so two builds of one tag are told apart. `check()` refuses a version
outside `SUPPORTED_VERSIONS = {"1.8"}`; 1.6 with the reason it is refused.
`run()` copies the bundle into a temporary directory, builds `fang-runner`
there with `$CC` or `cc` (`-std=gnu99 -O2`, the prefix's include directory,
the shared library with an rpath and `-lm`, or a static one with libelf, which
simavr's ELF loader inside it needs), refusing as `SimavrUnavailable` a missing
compiler, missing headers or library, or a build that fails, with the
compiler's message; then runs `./fang-runner run.cfg` in its own process
group under the wall-clock limit, exactly as `RenodeBackend` does, and keeps
`events.jsonl`, the runner's output as `simavr.log`, and an `outcome.json`
naming the version, build, compiler and arguments.

### `Duty` is engine-neutral

`Duty(surface, *, level=0|1, within=(a, b))` produces a dimensionless
fraction, declared and refused like `Count`'s window, and plans as
`{kind: "duty", entity: port, level, within_ns}` with the surface observed as
a GPIO pin. `measure()` walks the pin's `gpio.edge` and `gpio.release` events:
time at the level is observed; time before the first event, or after the
run's end, is unobserved, and the value is the scalar when nothing is, the
range `[observed / length, (observed + unobserved) / length]` otherwise.
Released time counts at neither level. Renode's GPIO probe records edges only,
so on Renode the time before a pin's first edge is unobserved too, which is
conservative and true. A `model.warning` whose source is the plan's target
withdraws every measure, which no Renode run records today.

### One tool base, two engines

`EmulationTool` holds what `RenodeTool` does now, parameterized by the
engine's name, its lowering's `bundle`, its backend and its file names;
`RenodeTool` and `SimavrTool` are it with Renode's and simavr's. `RENODE`
keeps its name, behaviour and job byte for byte; `SIMAVR` is registered after
it. `tool_for(question)` returns the registered emulation tool that covers a
question, for `fang emulate` and `regenerate.py`, so neither names an engine.
`regenerate._emulation_bundles` writes `out/<engine>/<question>/` with the
plan and the engine's own input: `platform.repl` and `run.resc` for Renode,
`run.cfg` for simavr.

### Diagnostics

`SIM-0021`, leaving SIM-0017 to SIM-0020 to the field questions in flight beside this change: the clock cannot be resolved from the
binding's fuses — none stated, a clock source the model does not cover, or an
unmodelled bit that differs from the part's shipped value.

### The example

`examples/quiet_orbit/` is QO-R1 as a Fang program: the ATtiny84A as a part
class with its SOIC-14 pin table, its four timer outputs as signals, its pin
map cited from the datasheet, and the board's USB-C receptacle (power only, CC
terminations), PTC fuse, reverse-blocking diode, bulk and bypass capacitors,
reset pull-up, four amber LEDs with 680 Ω resistors, the ISP header and the
test points, from QO-R1's schematic intent and BOM. The firmware is vendored
under `firmware/` as published, with its GPL-3.0-only licence text and a
README saying it is an aggregate fang's licence does not cover, and its ELF
under `firmware/elf/`, with the toolchain that built it.

The binding states the low fuse 0xE2, as QO-R1's README directs. Two
requirements and two questions:

- `fades`: the four LEDs fade on four phases a quarter cycle apart, peaking
  in turn SE, NE, NW, SW, on hardware PWM at the firmware's 488 Hz. The
  question `orbit` runs 2 s and measures the rises of NW in [1 s, 2 s) (within
  5 % of 488) and each LED's duty at level 0 in a 16 ms window at its peak — SE
  at [0, 16 ms), NE at [257, 273 ms), NW at [514, 530 ms), SW at [771, 787 ms),
  each at least 0.9. It passes.
- `fades_as_shipped`: the same, on a part programmed over ISP with its fuses
  as it ships, since nothing in QO-R1's build programs them. The question
  `as_shipped` names `fuses="factory"` and the same measures. It fails: 61
  rises, and three of the four peaks late.

The series resistors and the ISP header share nets with the observed pins and
are abstracted. Neither question asserts an LED dark: simavr's OCR = TOP
departure would light it for a period. `out/simavr/` ships each question's
`plan.json` and `run.cfg`, which need no emulator; `verification.txt` is
compared where simavr is installed.

### Test firmware is fang's own

The departures and rules the suite checks without the example — the
prescaler's timed sequence and a late write, a watched register, a released
pin, a halted core — run small programs written for the suite under
`tests/fixtures/simavr/firmware/` (Apache-2.0, with a Makefile and committed
ELFs), so no test depends on GPL code. Their recorded event files, kept short,
test the measures without simavr.

## Risks / Trade-offs

- [The fade's peak windows are set from the firmware's own timing, 4.013 ms a
  step] → They are stated in the program beside the requirement and widen or
  move by a transaction with a diff; the README says where they come from.
- [The runner is code fang ships in C, outside the Python suite's reach] → It
  is built and run by every live test; its configuration parser refuses
  anything outside its fixed set; and its output is the same event schema the
  Python measures already parse and check for order.
- [A host without a C compiler or simavr's headers cannot run AVR questions]
  → Reported unsupported by name, like a missing emulator; lowering and the
  committed outputs need neither.
- [simavr's two PWM departures make a short-window measure off by up to a
  period] → Both are coverage gaps on every run, and the example's windows
  span eight periods and assert only brightness.
- [Recording the engine moves every emulation question's verification entity,
  and so `sensor_node`'s snapshot hash] → Snapshot hashes are normalized in
  example outputs; plans and jobs do not move, so no measurement goes stale.
- [GPL firmware in an Apache repository and its sdist] → Vendored as an
  aggregate under its own licence file and README; called out to the
  maintainer before merge.
- [RFC 12 1.5 is numbered after 1.4, which is still a draft] → If 1.4 merges
  later, or not at all, the revision is renumbered and this change's citations
  with it; no requirement depends on 1.4.

## Migration Plan

None for a project with no AVR target: Renode questions, plans, jobs and
recorded measurements are unchanged, and a question recorded before engines
were routes to Renode. Rollback is reverting the change.

## Open Questions

- Whether simavr upstream will take fixes for the two PWM departures; until a
  release carries them, they stay coverage gaps and `SUPPORTED_VERSIONS` stays
  `{"1.8"}`.
