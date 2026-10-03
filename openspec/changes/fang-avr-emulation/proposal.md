# A Second Emulator, for AVR Cores

This change implements copperhead RFC 12, *The Copperhead Hardware Kernel and
Fang Language Standard*, version 1.5: Sections 4.1, 4.2 and 4.4 as they name
simavr, Sections 12.11 to 12.14 as revised, Section 17, conformance item 18 of
Section 16.1, and acceptance test 20 of Section 16.2. The revision is on the
branch `rfc12-avr-emulation` of copperheadhq/copperhead-rfcs, numbered after
the field questions of 1.4 (copperheadhq/copperhead-rfcs#11); the change may
proceed while its pull request is open, and claims conformance only to the
version that merges. It builds on `fang-emulation`, archived on 2026-10-02:
the binding, the descriptors, `Emulates`, the plan, the measures and the
`renode` tool are that change's, and this one adds an engine beside Renode
rather than a second way in. [design.md](design.md) holds the facts about
simavr and the ATtiny84A the design was checked against, and the spike that
found them.

## Why

Renode models no AVR core, so a Fang board on an ATtiny cannot ask anything of
its firmware. The first such board is copperhead's Quiet Orbit QO-R1, a four-LED
USB lamp on an ATtiny84A whose firmware had never been compiled or run. Built
and run in simavr outside fang, it compiles cleanly and every compare value it
writes is the one its source means, but the part ships with its clock divided
by eight and nothing in the design programs the fuse: on a part as delivered,
the lamp's PWM runs at 61 Hz instead of 488 Hz and its fade takes 8 s instead
of 1 s. That is exactly the defect firmware emulation exists to find before a
board is built, and fang should be able to find it through the gate, which
takes an engine that runs AVR cores and a plan that knows a fuse sets the
clock.

## What Changes

- **A platform descriptor names its engine**, and an `Emulates` question
  records, when it is elaborated, the engine its target's platform model
  names. Each emulation tool covers only its own engine's questions, so a
  question is never run on an emulator its platform model does not describe.
  Questions elaborated before engines were recorded name none, and every such
  question was Renode's.
- **A `simavr` tool**, registered at the behavioural level after `renode`.
  simavr's native input is a program linked against its library, so fang
  ships the source of one runner, `fang_runner.c`, which the backend builds on
  the host against the installed simavr and runs as a process of its own, on
  temporary copies, in its own process group, under a wall-clock limit. fang
  neither links simavr nor distributes a binary linked against it. simavr is
  found by its `simavr` executable, its headers and library read from the same
  installation, and checked against version 1.8; the 1.6 release that
  distributions package wires the ATtiny24/44/84 compare outputs to the wrong
  pins and is refused by name.
- **The ATtiny84A platform descriptor** (`fang:attiny84a`): its pins mapped to
  simavr's ports, its clock sources and factory fuses, the registers simavr
  does not model and the coverage gaps the spike found — compare registers
  applied at once rather than buffered to the end of the period, a fast-PWM
  output held at its compare level when the compare value is TOP, and the
  start-up delay before the first instruction.
- **Fuses are part of the firmware binding.** `Firmware(..., fuses=)` and
  `Emulates(..., fuses=)` state them by value or as `"factory"`, the values
  the part ships with; a platform whose descriptor declares fuses refuses a
  plan that states none, and a fuse value the descriptor does not cover. The
  plan resolves the oscillator and the clock prescaler the run starts at, and
  the runner models the system clock prescaler (`CLKPR`) the firmware may
  change at run time.
- **Watched registers.** simavr does not warn when firmware writes a register
  it does not model, so the runner watches those the descriptor names
  (`OSCCAL`, `PRR`'s unmodelled bits) and a write is a model warning, which
  withdraws every measure of the run. A warning from any platform model now
  withdraws every measure of its run.
- **`Duty(surface, level=, within=)`**, a new measure: the fraction of a
  window a pin spent at a level, decided only over the part of the window the
  run observed, so a window that starts before the pin's first recorded level
  or ends after the run is an interval rather than a guess. A pin the firmware
  stops driving is recorded as released, at neither level.
- **A run the emulator ends early has not completed**, and a runner that fails
  to build reports simavr unsupported, naming why, rather than a crashed run.
- `fang emulate` and the example regeneration dispatch by the question's
  engine instead of assuming Renode.
- **The example `quiet_orbit`**: QO-R1 as a Fang program, its firmware as
  published with its GPL-3.0-only licence and a committed ELF, and two
  questions — the lamp fading as designed with the fuse programmed as its
  README directs, and the same firmware on a part as it ships, which fails.
- **AT-F3**, the acceptance test for RFC 12 1.5's test 20.

## Capabilities

### New Capabilities

None. The project holds one capability and this change extends it.

### Modified Capabilities

- `fang-kernel` — modifies the firmware binding (fuses), emulation models (a
  descriptor names its engine, its clock and its watched registers), emulation
  questions (the engine recorded and routed by), the plan (the clock), the
  emulator's input (a host-built runner; a seed an engine has no use for),
  observation (released pins), absence and incomplete runs (the fraction of a
  window, platform warnings, an early end), an emulator reported rather than
  substituted (simavr's versions and its build), the emulate command, and the
  emulation acceptance tests (AT-F3). It adds a requirement for the AVR clock
  and its fuses.

## Impact

- `fang/emulation.py`: descriptors from every engine package, the engine on
  descriptors and questions, `covers` by engine, fuses on `Firmware` and
  `Emulates`, the plan's clock, `Duty`, platform warnings, the `simavr` tool
  beside `renode` with what they share drawn into one base. The Renode plan,
  bundle and job are byte-identical to today's: a plan without a clock keeps
  schema `fang.emulation/v2`, and only a plan that carries one is written as
  `fang.emulation/v3`.
- New package `fang/simavr/`: the lowering (plan to runner configuration and
  flash image), the backend (find, build, run), and as package data the
  runner's C source and the ATtiny84A descriptor. `pyproject.toml` and
  `MANIFEST.in` ship them.
- `fang/diagnostics.py` gains `SIM-0021` for a clock that cannot be resolved
  from the binding's fuses.
- `fang/cli.py` (`emulate`), `examples/regenerate.py` and
  `tests/test_examples.py` dispatch by engine; the new example ships its plans
  and runner configurations under `out/simavr/`, which need no emulator.
- No new Python dependency. simavr 1.8 with its headers and a C compiler run
  the questions; `avr-gcc` and `avr-libc` rebuild the firmware. The suite
  skips by name where they are absent.
- Licensing: simavr is GPL-3.0-or-later and stays outside fang, reached across
  a process boundary through a runner built on the host. The example's
  firmware is QO-R1's own, GPL-3.0-only, vendored as an aggregate with its
  licence text; fang's Apache-2.0 licence does not cover it.
- Docs: `README.md`, `CLAUDE.md`, `CHANGELOG.md`, `openspec/ROADMAP.md`, and
  the example's README.
