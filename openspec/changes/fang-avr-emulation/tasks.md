# Tasks: A Second Emulator, for AVR Cores

Implements copperhead RFC 12 version 1.5 (branch `rfc12-avr-emulation` of
copperheadhq/copperhead-rfcs). Group 1 was done before this change was
written and needed no kernel code; groups 2 to 4 need no simavr; group 6 on
needs simavr 1.8 and a C compiler for its live tests.

## 1. The engine spike

- [x] 1.1 Build simavr v1.8 (`f44723e`) and master (`d6aed53`) from source,
      and fetch `gcc-avr` 14.3.0 and `avr-libc` 2.2.1 without root; verify
      `simavr --list-cores` lists `attiny84`.
- [x] 1.2 Compile QO-R1's firmware at `056933b` with its own Makefile flags;
      verify it builds under `-Wall -Wextra -Werror` (246 bytes).
- [x] 1.3 Run it under a hand-written libsimavr runner logging pin edges and
      compare-register writes by cycle, for 5 s at 8 MHz and 20 s at 1 MHz;
      verify every write matches `255 − triangle(k + offset)` and every clean
      PWM period matches the datasheet, naming each period that does not.
- [x] 1.4 Run the same under Ubuntu's simavr 1.6; verify and record that it
      maps the ATtiny x4 compare outputs to the wrong pins.
- [x] 1.5 Write the capability matrix into design.md and revise RFC 12 where
      it reaches the normative text (version 1.5; `simavr` draws its serial
      number at random, corrected before commit).
- [x] 1.6 Install simavr 1.8 under `~/.local/opt/simavr-1.8` with `simavr` on
      the path; verify its `sim_core_config.h` reports `v1.8`.

## 2. Engines

- [x] 2.1 Load descriptors from every engine package (`fang.renode`,
      `fang.simavr`) and refuse an id shipped twice; add `engine` to the
      `Descriptor` and `"engine": "renode"` to the F401 descriptor; verify
      `test_the_shipped_descriptors_load` and a new test that a duplicate id is
      refused.
- [x] 2.2 Accept any `*_platform` kind as a platform in `compile_plan`, and
      refuse a plan whose question records an engine other than its target's;
      verify with a test that rewrites a question's recorded engine.
- [x] 2.3 Record `engine` in `Emulates.question_fields` from the module's
      firmware-bound platform part; verify the `sensor_node` questions record
      `renode` and a question with no shipped platform model records none.
- [x] 2.4 Draw `RenodeTool` into an `EmulationTool` base parameterized by
      engine, with `covers` matching `question.data.get("engine", "renode")`;
      verify every existing test in `tests/test_emulation.py` passes unchanged
      and the `sensor_node` jobs' hashes are those before the change.

## 3. Fuses and the clock

- [x] 3.1 Write `fang/simavr/models/attiny84a.json` (engine, target, mcu,
      flash size, SOIC pin table, empty peripherals, clock, watched registers,
      not modelled, provenance, qualification) and add `fang.simavr` package
      data; verify it loads and maps OC0A to PB2, OC0B to PA7, OC1A to PA6 and
      OC1B to PA5.
- [x] 3.2 Add `fuses=` to `Firmware` and `Emulates` (`"factory"` or a mapping
      of `low`, `high`, `extended`), carried into the question's scenario;
      verify a fuse name the part lacks is refused where it is declared.
- [x] 3.3 Allocate `SIM-0021` and resolve the clock in `compile_plan`: the
      question's fuses over the binding's; refuse none stated, an unmodelled
      clock source, and an unmodelled bit off its factory value; record the
      clock and the assumptions; verify each refusal names the fuse and bits,
      `factory` gives 8 MHz / 8, and `{"low": 0xE2}` gives 8 MHz / 1.
- [x] 3.4 Add `clock` to `EmulationPlan`, written only when set, with schema
      `fang.emulation/v3` for a plan that carries one; read v1, v2 and v3 back
      keeping each schema; verify the `sensor_node` plans are byte-identical
      to before and an ATtiny84A plan round-trips through `plan_from_dict`
      with its hash.

## 4. Measures

- [x] 4.1 Add `Duty(surface, level=, within=)` with `DutyMeasure`, its plan
      record, and the surface observed as a GPIO pin; refuse a level other than
      0 or 1 and an empty or untimed window; verify the declaration refusals.
- [x] 4.2 Measure a duty over `gpio.edge` and `gpio.release` events, a scalar
      when the window is wholly observed and an interval otherwise, released
      time at neither level; verify against synthetic records for each of the
      spec's three duty scenarios and the partly-observed one.
- [x] 4.3 Withdraw every measure of a run when a `model.warning`'s source is
      the plan's target and its descriptor does not expect it; verify with a
      synthetic record, and that the Renode fixtures measure as before.

## 5. The simavr lowering

- [x] 5.1 Cut the flash image from an AVR ELF in `fang/simavr/lowering.py`:
      ELF32, little-endian, machine 83, flash segments by physical address,
      gaps as 0xFF, refusing a segment past the part's flash and recording an
      EEPROM image as an assumption; verify on the QO-R1 ELF against
      `avr-objcopy -O binary`'s output, and refusals on an ARM ELF and an
      oversized segment.
- [x] 5.2 Write `run.cfg` from the plan with only the fixed keywords, entity
      identifiers matched against `[A-Z]+-[0-9a-f]+`, and the bundle's own file
      names; verify an identifier outside that form is refused, and a golden
      `run.cfg`.
- [x] 5.3 Assemble the bundle — `plan.json`, `run.cfg`, `fang_runner.c`,
      `firmware.elf`, `flash.bin`, `manifest.json` naming every digest, the
      seed and the engine's versions; verify the bundle is byte-identical when
      lowered twice.

## 6. The runner

- [x] 6.1 Write `fang/simavr/runner/fang_runner.c`: the configuration parser
      refusing anything outside its fixed set, the seed applied to `random()`
      and the serial number first, flash loaded from `flash.bin`, and the run
      bounded by virtual time in 128-bit segment arithmetic; verify it builds
      against simavr 1.8 with `-Wall -Wextra -Werror` and refuses a
      configuration with an unknown keyword.
- [x] 6.2 Record `run.start`, `gpio.edge` only while a pin's DDR bit is set
      (its level when the bit is set), `gpio.release` when it is cleared, and
      `run.end`; verify on a fixture firmware that drives a timer output with
      the pin still an input, then makes it an output, then an input.
- [x] 6.3 Model `CLKPR`'s timed sequence, its read-back, `clock.change` and
      the time base after it, and set simavr's frequency to match; verify on a
      fixture firmware that a change within four cycles multiplies its edge
      rate by eight and one written late changes nothing.
- [x] 6.4 Watch the descriptor's registers by wrapping the core's write
      handler, and record simavr's error and warning log lines, as
      `model.warning` from the target; verify a fixture firmware writing
      `OSCCAL` withdraws every measure and one setting only `PRTIM1` warns of
      nothing.
- [x] 6.5 End a run whose core halts first with `run.end` `halted`, and a crash
      with no `run.end`; verify on a fixture firmware that sleeps with
      interrupts off that the run has not completed and measures nothing.
- [x] 6.6 Commit the fixture firmware's C source (Apache-2.0), Makefile and
      ELFs under `tests/fixtures/simavr/firmware/` with the toolchain version,
      and short recorded event files under `tests/fixtures/simavr/events/`;
      verify `make` reproduces each ELF byte for byte.

## 7. The backend and the tool

- [x] 7.1 Write `SimavrBackend`: find `simavr` on the path and its prefix, the
      headers and the library; read the version from `sim_core_config.h` and
      the build from the library's digest; refuse 1.6 naming the pin fault and
      any version outside `{"1.8"}`; verify against fake prefixes for 1.6, an
      unknown version, missing headers and a missing library.
- [x] 7.2 Build the runner in the run's temporary directory with `$CC` or
      `cc`, refusing a missing compiler or a failed build as unsupported with
      the compiler's message; run it in its own process group under the
      wall-clock limit; keep `events.jsonl`, `simavr.log` and `outcome.json`;
      verify a run past its limit leaves no process and keeps its partial
      events.
- [x] 7.3 Register `SIMAVR` after `RENODE`; verify an ATtiny84A question
      routes to `simavr` and is reported unsupported naming simavr, never run
      on Renode, when simavr is absent.
- [x] 7.4 Run one ATtiny84A plan ten times; verify the ten event records are
      byte-identical, and that the serial number the core is given is the
      seed's.

## 8. The command and the outputs

- [x] 8.1 Add `tool_for(question)` and use it in `fang emulate`; verify
      `fang emulate --bundle-only` on QO-R1 writes the simavr bundle and runs
      nothing, and `fang emulate` prints simavr and its version.
- [x] 8.2 Dispatch `examples/regenerate.py`'s bundles by engine, into
      `out/<engine>/<question>/` with `plan.json` and the engine's own input;
      verify `sensor_node`'s `out/renode/` is unchanged.

## 9. The example

- [x] 9.1 Vendor QO-R1's firmware at `056933b` under
      `examples/quiet_orbit/firmware/` with its GPL-3.0-only licence text and a
      README stating it is an aggregate fang's licence does not cover, and the
      ELF built by avr-gcc 14.3.0 under `firmware/elf/`; verify `make`
      reproduces the ELF byte for byte.
- [x] 9.2 Write `quiet_orbit.py`: the ATtiny84A part with its SOIC-14 pin
      table, timer outputs and datasheet citations, and the board from QO-R1's
      schematic intent and BOM; verify `fang build` elaborates it and its
      netlist matches QO-R1's nets.
- [x] 9.3 Declare `fades` and `fades_as_shipped` with the `orbit` and
      `as_shipped` questions, the binding's low fuse 0xE2 and
      `fuses="factory"` on `as_shipped`; verify `fang verify` passes `orbit`
      and fails `as_shipped` with about 61 rises.
- [x] 9.4 Add the example to `regenerate.EMULATED`, write its README, and
      regenerate its `out/`; verify `tests/test_examples.py` passes with
      simavr present and skips only `verification.txt`, by name, without it.

## 10. Acceptance and the suite

- [x] 10.1 Write `test_at_f3_a_part_whose_fuses_set_its_clock_on_a_second_emulator`
      as the spec's AT-F3 scenario; verify it passes with simavr and is skipped
      by name without it.
- [x] 10.2 Cover every new and modified scenario in the delta spec in
      `tests/test_simavr.py` or beside the test it modifies; verify by listing
      each scenario against its test.
- [x] 10.3 Run the whole suite with simavr and Renode installed, and again
      with simavr hidden from the path; verify it passes, and that the only new
      skips name simavr.

## 11. Packaging and docs

- [x] 11.1 Ship `fang/simavr` package data in `pyproject.toml` and
      `MANIFEST.in`; verify `python -m build` puts `fang_runner.c` and
      `attiny84a.json` in the wheel and `twine check --strict` passes.
- [x] 11.2 Update `README.md`, `CLAUDE.md` (the emulation paragraph, the
      acceptance count, the skips), `CHANGELOG.md` and `openspec/ROADMAP.md`;
      verify every count and name they state against the suite.

## 12. Upstream

- [ ] 12.1 Push `rfc12-avr-emulation` and open its pull request against
      copperhead-rfcs `main`, once the maintainer approves; cite its number in
      proposal.md and design.md.
- [ ] 12.2 Archive this change into `openspec/specs/fang-kernel/spec.md` once
      the revision merges; verify `openspec validate --all --strict`.
