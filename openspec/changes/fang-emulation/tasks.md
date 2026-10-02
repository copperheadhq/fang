# Tasks: Firmware Emulation

Implements copperhead RFC 12 version 1.3, Sections 12.11 to 12.14
([copperheadhq/copperhead-rfcs#6](https://github.com/copperheadhq/copperhead-rfcs/pull/6)).
Group 1 needs no kernel code and can start at once. Groups 2 onward need the
spine of `fang-verification` (its groups 1 to 7) and `fang-mcu-parts`.

## 1. The engine spike

Run in a scratch directory outside the package. Only what graduates is
committed — the firmware, the platform description, the probes, and the golden
and recorded files the later tests read — each reviewed again as it lands.

- [x] 1.1 Install Renode 1.17.0 from the portable Linux tarball, recording its
      digest, and `arm-none-eabi-gcc`; verify `renode --version` prints
      `Renode v1.17.0` and the compiler runs.
- [x] 1.2 Run upstream's `tests/peripherals/HS3001.robot` unchanged; verify it
      passes, confirming the install.
- [x] 1.3 Write the demo firmware as design.md describes it — register-level
      C, a Makefile, the three defect flags — and build all four ELFs; verify
      each builds and record the toolchain version.
- [x] 1.4 Write `stm32f401re.repl` by hand from upstream's `stm32f4.repl` and
      the HS3001 hookup, with Renode's notice; verify the startup ELF boots and
      prints `temp=` lines.
- [x] 1.5 Write the I2C, GPIO and UART probes and the recorder, and produce
      `events.jsonl` with integer virtual nanoseconds; verify the record holds
      the boot line, the sensor's transactions and the LED's edges.
- [x] 1.6 Run the same script ten times; verify the ten event records are
      byte-identical.
- [x] 1.7 Confirm that Renode's configuration (virtual log timestamps,
      synchronous logging) can be supplied per run, that the address NACK's
      warning carries an exact virtual timestamp under it, that the GPIO mode,
      output-type and alternate-function registers read without side effects,
      and that `"100ms"` is read as 100 s; record each result.
- [x] 1.8 Run each defective build and the absent-sensor case; verify which
      events differ from the startup run, as design.md's demo expects.
- [x] 1.9 Write the capability matrix — confirmed, refuted, not modelled — into
      design.md, revising any fact the spike refuted (and RFC 12 where it
      reaches the normative text); commit the hand-written `platform.repl` and
      `run.resc` under `tests/fixtures/renode/` as golden files and the recorded
      event files as measure fixtures.

## 2. Bindings and descriptors

- [x] 2.1 Add the `EmulationModel` (source) and `Firmware` (path, target) traits
      in `fang/emulation.py`; verify they register and enumerate like
      `Simulatable`, that `Firmware` carries no digest, and that
      rebuilding the bound file leaves the snapshot byte-identical.
- [x] 2.2 Add the descriptor schema and registry in `fang/emulation.py`, loading
      `fang/renode/models/*.json` as package data; verify a `source` with no
      descriptor is refused naming the part and the descriptor.
- [x] 2.3 Write the `fang:stm32f401re` platform descriptor — the platform file,
      the core clock assumed, the port and pin mapping, the GPIO register
      addresses, what it does not model — and the `renode:Sensors.HS3001`
      peripheral descriptor — its inputs with units, the absent-device fault,
      its events, its provenance — both at *tested in emulation* once group 1
      passes; verify each loads and every unmodelled item becomes a coverage
      gap.
- [x] 2.4 Allocate the `SIM` codes named in design.md after `fang-verification`'s;
      verify the registry tests pass and no code was reused.

## 3. The question

- [x] 3.1 Add the matches (`I2CRead`, `I2CWrite`, `Rises`, `Falls`,
      `UartLine`), the measures (`FirstAt`, `Count`, `Latency`, `UartValue`,
      `PinConfig`), `At`, `Absent` and the `Emulates` declaration, refusing a
      `result`; verify a declaration with a result fails with its `SIM` code.
- [x] 3.2 Elaborate an emulation question into a `Verification` with method
      `emulation`, result `UNKNOWN` and `extensions["question"]`, every surface
      resolved at elaboration time; verify two elaborations are byte-identical.
- [x] 3.3 Route method `emulation` to the behavioural level and the `renode`
      tool in the spine's registry; verify an undecided question routes there
      and an already-decided one answers at the equation level.

## 4. The plan

- [x] 4.1 Compile the target and scope: the platform model, the firmware (the
      question's own, else the binding), and every component sharing a net with
      a touched pin, each modelled or abstracted; verify a component with
      neither is refused by name and each abstraction is a coverage gap.
- [x] 4.2 Resolve each bus in scope from the port's `peripheral`, the lowered
      connections' selectors, the interface's open-drain signals and
      `resolve_address`; verify the demo's plan names I2C1, the chosen pins with
      AF4, open drain on both, and 0x44.
- [x] 4.3 Resolve observation points through the pin assignment and the
      platform descriptor, refusing a pin the descriptor does not map; verify
      `Rises("mcu.status")` resolves to port A pin 5 and an unmapped pin is
      refused.
- [x] 4.4 Check stimuli and faults against the descriptor, and require
      `run_until`; verify a wrong-dimension stimulus, an unsupported fault and a
      missing duration are each refused by name.
- [x] 4.5 Write the plan as canonical `fang.emulation/v1` JSON identified by its
      own hash; verify two compilations are byte-identical and that the plan
      hash does not depend on the checkout's path.

## 5. The lowering

- [x] 5.1 Ship `platforms/stm32f401re.repl` and `probes/*.cs` as package data
      from group 1, with Renode's notice; verify they install with the package
      and that `MANIFEST.in` and `pyproject.toml` carry them.
- [x] 5.2 Lower a plan to `platform.repl` and `run.resc` — seed first, the
      stimulus segments in decimal seconds, the probes, the register snapshot,
      `quit` — and `manifest.json` with every digest; verify against the golden
      files of 1.9 byte for byte, and that lowering twice is byte-identical.
- [x] 5.3 Verify a stimulus at 100 ms is written as `0.1`, and that a surface or
      string carrying monitor syntax is refused at the plan or never reaches the
      script.

## 6. Events and measures

- [x] 6.1 Read `events.jsonl` into typed events, converting integer
      nanoseconds to `Decimal` seconds; verify against the recorded fixtures.
- [x] 6.2 Implement the five measures over events; verify each against the
      startup fixture.
- [x] 6.3 Measure an absent event in a completed run as
      `Quantity.range(run_end, Infinity)`; verify it serializes canonically,
      that `first_read <= 200 ms` fails after a two-second run and stays
      undecided after a 100 ms one, and that a missing `UartValue` line gives no
      value.
- [x] 6.4 Produce no measurement from a run that ended `timeout` or `crashed`,
      and withdraw every measure over a model that warned, naming the warning on
      the evidence; verify both against crafted event records.
- [x] 6.5 Compare `register.snapshot` events with the board's required mode,
      selector and output type in `PinConfig`; verify the startup fixture
      measures zero and the push-pull fixture measures two.

## 7. The backend and the tool

- [x] 7.1 Add `RenodeBackend`: `available`, `version` checked against the
      supported set, and `run` on a temporary copy, without a shell, in its own
      process group, killing the group at the wall-clock limit and keeping the
      partial events; verify unsupported is reported by name when Renode is
      absent or its version is unchecked, and, where Renode is installed, that a
      hung run leaves no process behind.
- [x] 7.2 Add the `renode` tool implementing the spine's protocol — `covers`,
      `available`, `version`, `prepare` (plan and bundle), `run`, `read` — and
      register it at the behavioural level; verify `prepare` is byte-identical
      twice and `read` produces nothing the events did not contain.
- [x] 7.3 Record on each run's evidence the Renode version and build, the
      firmware digest, the plan hash, the seed, every bundle digest, the
      assumptions and the coverage gaps, and that the run was local; verify the
      record.
- [x] 7.4 Report a verification stale in `fang verify` when its evidence names a
      firmware digest other than the bound file's current one; verify by
      rebuilding a fixture file.

## 8. The command

- [x] 8.1 Add `fang emulate` and `--bundle-only`; verify the bundle is written
      without Renode, measures are printed with it, and no workspace changes.

## 9. The demo

- [x] 9.1 Commit the firmware source, Makefile, ELFs and toolchain record from
      group 1 under `examples/sensor_node/firmware/`, and add the traits and the
      two questions to the program with their parameters and constraints;
      update its README.
- [x] 9.2 Teach `examples/regenerate.py` an `EMULATED` set writing
      `out/renode/` (plan, platform description, script) everywhere, with
      `verification.txt` written where Renode is installed by the spine's own
      listing, which prints no tool version and is compared only where its tool
      is installed; the event records live with the tests as fixtures rather
      than in `out/`; verify the examples suite passes with and without Renode
      on the path.
- [x] 9.3 Add `tests/test_emulation.py` covering every scenario of the delta
      spec, the three defective builds and the PA6 board variant each failing
      on the measure design.md names, and a ten-run determinism test; verify it
      passes where Renode is installed and skips by name where it is not.
- [x] 9.4 Add `test_at_f1_*` and `test_at_f2_*` to `tests/test_acceptance.py`;
      verify both pass with Renode installed and skip by name without it.

## 10. Documents

- [x] 10.1 Add the emulation reference and concepts pages and update the CLI
      page; verify internal links resolve.
- [x] 10.2 Update `README.md`, `CLAUDE.md`, `CHANGELOG.md`, `examples/README.md`
      and `openspec/ROADMAP.md`; verify the quoted counts match the tree.
- [x] 10.3 Quote the requirement names in each new module's docstring; verify
      `openspec validate fang-emulation --strict` and the whole suite pass.

## 11. What review found

- [x] 11.1 Refuse `PinConfig` over a port that is no bus in scope, or a bus
      with no pins of the target, under SIM-0016; verify the status signal,
      USART2 and an unconnected I2C1 are each refused.
- [x] 11.2 Refuse a match detail no measure filters on, the `I2CRead`
      register among them; verify against the plan, and that `contains` and
      `data` still compile.
- [x] 11.3 Refuse a `Count` window that is empty or not bounded by times,
      where it is declared and again when the plan compiles.
- [x] 11.4 Resolve a firmware path for staleness exactly as the run does,
      recording the part the firmware ran on; verify with a question
      redeclared in another directory, before and after a rebuild.
- [x] 11.5 Observe a signal with several loads on its one pin.
- [x] 11.6 Refuse a bus match over a device a fault removes, and a stimulus
      on one; drop `missing_reads` from `sensor_node` and regenerate its
      outputs.
- [x] 11.7 Report a temporary directory whose path has a space as
      unsupported before Renode starts; verify with `TMPDIR` set to one.
- [x] 11.8 Refuse a ranged stimulus and one outside the run under SIM-0012;
      refuse a model naming no shipped descriptor naming the part; name each
      probe by the whole path and refuse two of one name in the lowering.
- [x] 11.9 Report an installed Renode of an unchecked version by its version,
      not as missing, through `fang verify` and `fang emulate`.
- [x] 11.10 Refuse a run duration that is not positive under SIM-0014 where
      `Emulates` is written, when the plan compiles, and in the lowering;
      verify zero and a negative duration at each.
- [x] 11.11 Match a model warning only against the expected warnings of its
      own model's descriptor, each expected warning in the plan naming its
      descriptor; verify a sensor warning the platform expects withdraws the
      sensor's measures, and a bus warning the sensor expects withdraws the
      bus's; regenerate `sensor_node`'s plans.
- [x] 11.12 Refuse a device address that is no whole number under SIM-0016,
      naming the device and the address, rather than truncating it; verify
      with the sensor at `72.5 * addr`.
- [x] 11.13 Refuse a pin selector the platform does not read under SIM-0013,
      naming the pin and the selector, and give a pin configuration over one
      no value; verify `Selector("AF_4")` on the board and `AF_4` and `AF16`
      in a plan.
- [x] 11.14 Exit `fang emulate` non-zero when a run timed out or crashed, as
      `fang verify` does for a failed verification; verify both outcomes with
      a stand-in Renode.
