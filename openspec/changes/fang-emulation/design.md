# Design: Firmware Emulation

## Context

See [proposal.md](proposal.md) for motivation. The normative text is copperhead
RFC 12 version 1.3, Sections 12.11 to 12.14, with RFC 3 version 1.5, Sections
5, 8.2 and 14 ([copperheadhq/copperhead-rfcs#6](https://github.com/copperheadhq/copperhead-rfcs/pull/6));
this document is informative. It depends on two changes that are not yet built:
the spine of `fang-verification` (the `Tool` protocol, `route`, the measurement
transaction and `fang verify`) and `fang-mcu-parts` (ports as peripheral
instances, selectors on lowered connections, `resolve_address`, and the
`sensor_node` board). Nothing here duplicates either: an emulation question is
a verification question, the `renode` tool is one more tool, and its
measurements re-enter through the spine's runner.

Renode (Antmicro, MIT) runs unmodified firmware binaries against platform
descriptions in its own `.repl` format, drives them from `.resc` scripts, and
advances in virtual time. It is reached headless as an executable (`renode
--console --disable-gui`), which is what "Backends Are Reached Across A Process
Boundary" asks for, and it needs no Robot Framework: `renode-test` is only the
Robot wrapper.

Renode is not installed on the machine this was planned on, and neither is
`arm-none-eabi-gcc`. Every claim below was verified against Renode's source at
`renode` 8aa2c8d and `renode-infrastructure` e0b8c33 (both 2026-10-02, after
the v1.17.0 release of 2026-09-07), not against a running install. Group 1 of
the tasks re-checks each against v1.17.0 before any kernel code is written; a
claim that does not survive revises this document, and RFC 12 if it reaches
the normative text, first.

### What Renode does and does not do

| Fact | Consequence for this design | Source |
| --- | --- | --- |
| There is no STM32F401 platform. Upstream runs a `nucleo_f401re` Zephyr ELF on `platforms/cpus/stm32f4.repl`, a superset built on the F40x: more flash and RAM, Ethernet, CAN, USART3, UART4/5, extra timers. | Firmware that touches a peripheral the F401 lacks runs in emulation and faults on silicon. Fang ships its own F401 platform description, derived from upstream, with the F401's memory map and peripheral set. | `platforms/cpus/stm32f4.repl`; `tests/peripherals/HS3001.robot` |
| The clock controller is a stub: its registers read back what was written and "do not affect other peripherals or their clocks". SysTick is fixed at 72 MHz in the platform file and general timers at 10 MHz; an F401 runs at up to 84 MHz. | A firmware clock misconfiguration is invisible. Virtual-time measurements hold only under the core clock the descriptor assumes, recorded as an assumption on every run; clock configuration is a standing coverage gap. | `STM32F4_RCC.cs:22-34`; `stm32f4.repl:40` |
| I2C and UART controllers ignore GPIO configuration: a sensor registers on the controller by address (`@ i2c1 0x44`). GPIO *outputs* honour the mode register: a write reaches a connected receiver only in output mode. | Firmware with the wrong alternate function still talks to the sensor, so pin configuration is measured directly. A GPIO observation on the pin the board assigns does test the firmware's pin choice. | `STM32F1_I2C.cs` (a `SimpleContainer<II2CPeripheral>`); `STM32_GPIOPort.cs:111-175` |
| The I2C controller does not model acknowledgement bits; it sets the address-NACK flag only when no target is registered at the address. A data-phase NACK cannot be injected. | The one I2C fault is an absent device. Every other I2C fault is refused at plan time. | `STM32F1_I2C.cs:107,418-426` |
| I2C DMA is not implemented: `DMAEN` is a tagged flag and the DMA request lines are never driven. | Firmware that reads the sensor by DMA does not work. A write to `DMAEN` is reported as a model warning, which withdraws the sensor's measures. | `STM32F1_I2C.cs:77,79,238` |
| There is no I2C transaction log; register-level access logging exists, and logging is asynchronous unless configured synchronous. | Events come from probes, not from scraping logs. | `renode-infrastructure` grep; `Logger.cs:829` |
| An I2C target implements `Write(byte[])`, `Read(int)` and `FinishTransmission()`, and C# is compiled at load time with `include @file.cs`. | A probe is a C# class implementing the target interface, wrapping the real sensor model and recording each call; no Renode build is needed. | `II2CPeripheral.cs`; `IncludeFileCommand.cs:85` |
| Shipped sensor models include `HS3001`, `SI70xx`, `TMP103`, `TMP108`, `BMP180`, `LPS25HB`, `LSM6DSO_IMU`, `ICM20948` and `ADXL345`. `HS3001` exposes `Temperature` and `Humidity` as `decimal` properties and is tested upstream on `nucleo_f401re`; the test shows its quantization (25.00 °C reads back as 25.01 °C). | HS3001 is the first sensor: the firmware-and-model pair is already exercised upstream, a stimulus is a property assignment, and a tolerance has to allow the sensor's resolution. | `Sensors/HS3001.cs:191-227`; `HS3001.robot` |
| The default pseudo-random seed is drawn per process; `emulation SetSeed` fixes it. | The script sets the seed first. A fixed seed is necessary and not by itself proof of determinism; the suite runs one plan ten times and compares. | `PseudorandomNumberGenerator.cs:86` |
| Host inputs — monitor commands over a socket, the external control API — land at synchronization points chosen by host timing. | The whole scenario is compiled into the script; nothing drives Renode live during a run whose events become evidence. | inferred; confirmed by the spike |
| `TimeInterval` parses with an unanchored pattern and no units: `"100ms"` is read as 100 seconds. | Every duration is written as decimal seconds (`"0.1"`) from the `Decimal` quantity, and a golden-file test pins the form. | `TimeInterval.cs:44` |
| `renode --version` prints `Renode v1.17.0` and a build line carrying the build date and commit. | The first line is the version; the build line is recorded on the evidence and normalized in committed outputs. | `src/Renode/Program.cs:134-148` |

### What the spike found (Renode 1.17.0, 2026-10-02)

Run against the installed release (`renode` build `f1dd1b4af`, the portable
Linux tarball, sha256 `4ba7c68b…605a5f`) with firmware built by Arm GNU
Toolchain 15.2.Rel1. Upstream's `HS3001.robot` passes unchanged.

| Fact | Status | Consequence |
| --- | --- | --- |
| No F401 platform; the F40x superset runs F401 firmware | confirmed | `stm32f401re.repl` derived and shipped |
| Clock controller is a stub | confirmed | the firmware runs from the 16 MHz HSI it resets to and configures no PLL; SysTick and the timers are set to 16 MHz in the platform; clock configuration is a coverage gap |
| I2C and UART ignore pin configuration; GPIO outputs honour the mode | confirmed | the PA6 board variant sees no edge while the firmware drives PA5 |
| **The GPIO output-type register is not stored** | **added** | OTYPER is a tagged register: a write is accepted with a warning and reads back 0. Output type is measured from the firmware's *writes*, captured by a bus watchpoint (`register.write`), not from a read-back; mode and alternate function are read back too, and agree |
| Only an absent device NACKs | confirmed | the controller's warning becomes `i2c.nack` |
| The NACK's timestamp | confirmed, with a change | a log entry's own virtual time is the last sync point (it stamped the NACK at the boot line's 2020 ns); the recorder stamps it itself after synchronizing the CPU, giving 2340 ns. Renode's logger collapses a run of identical warnings, so a repeated NACK is recorded once |
| **The I2C controller warns on every write to CCR, TRISE and ACK** | **added** | these fields are tagged — timing and acknowledgement are not modelled. The descriptor lists them as expected warnings and coverage gaps, so they do not withdraw measures; any other warning from a watched model does |
| The HS3001 measurement request is a zero-length write | confirmed | the controller calls only `FinishTransmission()`, so the model logs nothing; the read hands back all four bytes at the address phase |
| No I2C transaction log | confirmed | probes record transactions |
| Seed per process; host input lands at sync points | confirmed | ten startup runs and three absent-sensor runs gave byte-identical event records |
| `"100ms"` is read as 100 s | confirmed | `RunFor "1ms"` ran one second |
| **Renode's launcher runs from its install directory** | **added** | relative paths in a script resolve there, including `@` paths to files that do not exist yet; the script names every file as `$ORIGIN/…` |
| **Upstream's platform downloads an SVD at load** | **added** | `ApplySVD` fetches `STM32F40x.svd.gz` over the network on every load; the F401 platform drops it, so a run needs no network |
| `--hide-log` hides errors as well as noise | added | the backend keeps Renode's log in the raw run instead of hiding it |
| The firmware build is reproducible | confirmed | `make clean && make` reproduces the ELF byte for byte |

### Considered and set aside

| Option | Why not |
| --- | --- |
| **Robot Framework** (`renode-test`) | Not needed to drive Renode, and its reports are not the result contract. |
| **pyrenode3**, **renode-run** | Wrappers, and neither is on PyPI; binding to a wrapper in place of the native input is what "Simulation Is A Compiler Target" forbids. |
| **The external control API**, **the monitor socket** | Live control is host-timed. Useful to a person debugging; never for evidence. |
| **Renode's Docker image** | No 1.17.0 tag as of this writing. The portable Linux tarball, pinned by digest, is the reference install. |
| **QEMU** | Its device models are compiled into the emulator, so every sensor is a patch to QEMU; Renode loads a C# model at run time. |
| **Wokwi**, **Simantic** | Hosted products whose engines are not published; neither runs as a local backend under a licence fang can name. |

## Goals / Non-Goals

**Goals:**

- One board end to end: a Fang program, a committed ELF, Renode, and a
  requirement over the firmware's behaviour decided through the gate.
- Everything but the run testable without Renode: the plan, the lowering and
  the measures are pure, and their tests read golden files and recorded event
  files produced by the spike.
- The bundle as the contract copperhead takes over later, so that adopting a
  hosted runner changes `run` and nothing else.

**Non-Goals:**

- No copperhead integration: no hosted runner, model catalogue, orchestration
  or REFUSE/HOLD mapping.
- No physical correlation and no `qualify`; every model here is at most
  *tested in emulation*, and its measurements' confidence says so.
- No timing claims beyond virtual time; the clock tree is not modelled.
- No I2C fault but an absent device; no SPI, interrupts as stimuli or second
  MCU; no agent tool, for the reason RFC 12 and `fang-verification` give.

## Decisions

### The loop

```text
Fang program
   |  Emulates(...)                                 -- a question, declared
   v
Verification entity, result UNKNOWN          Constraint over the measured parameter,
(firmware, stimuli, faults, measures)        evaluating to undecided
   |
   v
route(question) --> behavioural, renode       equation: already decided, no tool runs
   |
   v
tool.prepare(snapshot, question) --> Job      compile_plan: resolve and validate everything;
   |                                          lower: plan -> .repl + .resc + probes + manifest
   v
tool.run(job, workspace) --> RawRun           renode across a process boundary, on temporary
   |                                          copies; version recorded; unsupported if absent
   v
tool.read(job, raw) --> Measurements          events.jsonl -> Decimal, nothing else
   |
   v
the spine's measurement transaction through propose, unchanged: accepted
commits; a failed hard constraint records FAIL with the evidence
```

### Fang drives Renode, and the bundle is the seam

The kernel writes Renode's native input itself and runs Renode as it runs
ngspice, which "Simulation Is A Compiler Target" asks for as written. `prepare`
produces a bundle; `run` is the only method that leaves the process; `read`
turns the event file into measurements. When copperhead integrates, it executes
a bundle — in a sandbox locally, on a hosted worker remotely — where
`RenodeBackend.run` executes it today; `prepare` and `read` stay in fang, so the
verdict is the same code reading the same events whichever runner produced
them. A logic-analyzer capture decoded into the same event schema is read by
the same measures, which is how physical qualification will fit.

### Modules and package data

`fang/emulation.py` holds the `Firmware` binding's semantics, the descriptor
registry, `Emulates`, the matches and measures, plan compilation and the
`renode` tool. `fang/renode/` is a package: `lowering.py` (plan to bundle),
`backend.py` (`RenodeBackend`), and as package data `platforms/stm32f401re.repl`,
`probes/*.cs` and `models/*.json` — one descriptor per supported model.
Descriptors are data in the fang package until a catalogue exists; then each
becomes a reference into it, pinned by digest, and the fang copy is retired
rather than kept beside it.

### Bindings: a trait for the model, a trait for the firmware

An emulation model is an `EmulationModel` trait whose `source` names a
descriptor (`"fang:stm32f401re"`, `"renode:Sensors.HS3001"`); the descriptor
says whether it is a platform or a peripheral model. `Firmware(path, target=)`
is a trait on the component that runs it, and carries no digest. Both live in
`fang/emulation.py`.

*Alternative considered, and first planned:* `Simulatable` traits with
`model_kind="renode_platform"`. The trait registry holds one trait per protocol
for an entity, so a part could not carry a SPICE model and an emulation model
at once, and the SPICE plan, which walks every `simulatable` entity, would read
an emulation model as one it cannot use and reject its plan.

Fang holds traits in the elaboration result, beside the snapshot, not in it:
`compile_plan` takes `traits=` for exactly this reason, and RFC 12's
conformance item 14 — traits persisted with the snapshot and reloaded without
running a program — is a gap across the whole project, not one this change can
close. The emulation plan is therefore compiled from the snapshot and the
traits, as the SPICE plan is; when traits are persisted, the binding moves into
the snapshot with every other trait and nothing here changes shape.

```python
self.mcu.add_trait(EmulationModel(source="fang:stm32f401re"))
self.env.add_trait(EmulationModel(source="renode:Sensors.HS3001"))
self.mcu.add_trait(Firmware("firmware/elf/sensor_node.elf", target="stm32f401re"))
```

### The question

`Emulates` is a rationale declaration beside `Requires`, `Verifies` and
`Simulates`, elaborating like `Simulates` does: a `Verification` with
`extensions["question"]` holding the canonical question, with every surface
resolved at elaboration time.

```python
startup = Emulates(
    "sensor_ready",
    run_until=2 * s,
    stimuli=[At(0 * ms, "env.temperature", 25 * degC)],
    measures={
        "first_read": FirstAt(I2CRead("env")),
        "reported": UartValue("mcu.usart2", prefix="temp=", unit=degC),
        "slow_blinks": Count(Rises("mcu.status"), within=(1 * s, 2 * s)),
        "mux_mismatches": PinConfig("mcu.i2c1"),
    },
    abstracted=("scl_pullup", "sda_pullup", "series", "indicator", "bypass"),
)
```

Because the question is in the graph, widening `within` is a transaction with a
diff, provenance and the gate's policy — an assertion window turns a failure
into a pass as surely as a verdict does.

### The plan and the bundle

`compile_plan` for an emulation question resolves the target, the scope, each
bus (controller from the port's `peripheral`, chosen pins and selectors from
the lowered connections, open drain from the interface's `SignalSpec`, address
from `resolve_address`), each observation point, each stimulus and fault, and
the duration. It is written as canonical JSON, `fang.emulation/v1`, through
`fang.serialization`: mappings sorted, quantities as `Decimal` strings, times as
integer nanoseconds. Its identity is its own content hash; the snapshot hash is
recorded beside it but is not its identity, because the snapshot hash covers
provenance and so the checkout's absolute path.

A bundle is the plan lowered: `plan.json`, `platform.repl` (using the platform
file, then each peripheral model wrapped in its probe at its address, and the
GPIO probes), `run.resc`, the probes, the firmware copy, and `manifest.json`
naming the digest of every file, the seed and the Renode version it was
prepared for.

### The lowering's rules

- `emulation SetSeed` is the first command.
- Stimuli are ordered by time and the run is emitted as segments: run to a
  stimulus, set the input, run to the next, to `run_until`. Every duration is
  decimal seconds from the `Decimal` quantity. The stimulus is also written
  into the event record when applied.
- Renode's configuration makes log timestamps virtual and logging synchronous.
- Before the firmware loads, the recorder installs a write watchpoint on the
  mode, output-type and alternate-function registers of each GPIO port the
  plan's buses use, recording every write the firmware makes; at the end of
  the run it also reads back the mode and alternate-function registers. The
  output-type register is not stored by Renode's model, so its writes are the
  only evidence of it. Register addresses come from the platform descriptor.
  The I2C status register, whose NACK flag clears on read, is never read.
- Every file the script names is `$ORIGIN/…`, because Renode's launcher runs
  from its install directory.
- The script ends with `quit`. Only commands from this fixed set appear;
  surfaces are validated identifiers and values are `Decimal` strings, so no
  text from a program reaches the monitor or Renode's Python.

### Probes and events

All probes live in one C# file, `fang_probes.cs`, compiled by Renode at load.
The recorder registers on a GPIO port as a container child, like an LED, and is
never connected, so the script can call it and the firmware cannot see it; it
switches Renode's logger to synchronous and adds a log backend for the
warnings of the peripherals it is told to watch. The I2C probe registers at
the device's address, constructs the real model by its type name, forwards
every call to it, and records `Write`, `Read` and `FinishTransmission` with
their bytes; a stimulus is its `SetInput` method, given a decimal string. The
GPIO probe is a receiver connected to a port pin's output. The UART probe
listens to the UART's transmitter and records each line. The recorder writes
`events.jsonl`, each line `{seq, t_ns, source, type, payload}`, with `source`
an entity identifier the lowering writes into the probe, and each event stamped
after synchronizing the CPU that caused it. The types are `run.start`,
`stimulus`, `uart.line`, `gpio.edge`, `i2c.write`, `i2c.read`, `i2c.stop`,
`i2c.nack`, `register.write`, `register.snapshot`, `model.warning` and
`run.end`, whose payload gives `completed`; a run without `run.end` ended on a
timeout or a crash, which the backend tells apart.

The address NACK of an absent device reaches no probe, because no target is
registered at that address; it is taken from the controller's warning, which
the recorder's log backend receives on the CPU thread that caused it.

### Measures

| Measure | Measures | Dimension |
| --- | --- | --- |
| `FirstAt(match)` | virtual time of the first matching event | time |
| `Count(match, within=(a, b))` | matching events in `[a, b)` | dimensionless |
| `Latency(from_, to)` | time from the first `from_` to the first `to` after it | time |
| `UartValue(uart, prefix=, unit=)` | the number after `prefix` on the first matching line | the stated unit |
| `PinConfig(port)` | pins configured otherwise than the board requires | dimensionless |

The matches are `I2CRead(device, register=None)`, `I2CWrite(device,
data=None)`, `Rises(surface)`, `Falls(surface)` and `UartLine(uart,
contains=)`. An ordering requirement is a latency.

**An absent event is the half-open range after the run's end.** RFC 12 leaves
the representation to the implementation, provided interval comparison decides
it. A `FirstAt` or `Latency` whose event did not occur in a completed run
measures `Quantity.range(run_end, Infinity)`, an inferred value. Interval
semantics then decide exactly what was observed: `first_read <= 200 ms` fails
after a two-second run, and stays undecided after a 100 ms one, because the run
never looked past 100 ms. A range with an infinite maximum already constructs
and yields its interval; its canonical serialization and its comparisons are
verified in the tasks. A `UartValue` whose line never appeared has no value —
there is no range of temperatures to fail — so presence is a `Count` of the
line, measured beside it.

A run that ended `timeout` or `crashed` produces no measurement. A
`model.warning` from a model withdraws every measure over that model's events,
and the evidence names the warning.

### `RenodeBackend`

It follows `NgspiceBackend`. `available()` finds `renode` on the path;
`version()` reads the first line and checks it against the versions the
lowering was checked against, reporting unsupported otherwise. `run` copies the
bundle to a temporary workspace and runs `renode --console --disable-gui -p
--hide-log run.resc` with no shell, in its own process group; on the wall-clock
limit it kills the group and returns what was recorded, with `run.end`
reporting `timeout`. The local backend isolates only this far — temporary
copies, no source tree reachable through the bundle, a time limit and a
recorded invocation — and the evidence says the run was local; network
isolation and resource limits are a hosted runner's.

### The F401 platform description

`fang/renode/platforms/stm32f401re.repl` is derived from upstream `stm32f4.repl`:
512 KB of flash and 96 KB of SRAM, the peripherals the F401 lacks removed, and
SysTick and the timers set from the core clock the descriptor assumes. Every
remaining difference from silicon — the stubbed clock controller, I2C without
DMA or acknowledgement bits — is listed in the descriptor and becomes a coverage
gap on every run. The file carries Renode's copyright and MIT notice.

### Diagnostics go in the `SIM` area

New codes after those `fang-verification` allocates: a model naming no
descriptor, a component in scope with neither model nor abstraction, an
unsupported fault, a stimulus of the wrong dimension, a pin the platform
descriptor does not map, a missing duration, a question stating a result, and a
firmware target the platform does not describe.

### The demo

`examples/sensor_node/` — the board `fang-mcu-parts` adds — gains
`firmware/`: bare-metal C at the register level with a Makefile and no vendor
HAL, so the defective variants are build flags. USART2 at 115200 baud; I2C1 on
PB8/PB9 at AF4, open drain; the HS3001 at 0x44, read every 100 ms and printed as
`temp=<value>`; the LED on PA5 toggling every 500 ms while readings succeed and
every 100 ms while the sensor does not acknowledge. `-DSENSOR_ADDRESS=0x45`,
`-DI2C_PUSH_PULL` and `-DNO_TIMEOUT` build the defects. The source, the
Makefile, the ELFs and the toolchain version that built them are committed;
the suite never rebuilds them.

Two questions: **startup** — at 25 °C the first read is within 200 ms, the
reported temperature is within 0.05 °C, between 1 s and 2 s the LED rises
exactly once, and no I2C pin is misconfigured; and **sensor missing** — with
the sensor absent, between 1 s and 2 s the LED rises at least four times, and
nothing is read.

The negative cases live in the suite, each failing on the measure it should:
the wrong-address build fails `first_read`; the push-pull build fails
`mux_mismatches`; a board variant assigning the status signal to PA6 fails
`slow_blinks`, because the firmware still drives PA5 and Renode delivers a GPIO
write only to the pin the firmware configured; the no-timeout build fails the
sensor-missing question.

The example's `out/renode/` carries each question's plan, platform
description and script, regenerated and compared everywhere, because lowering
needs no emulator. Its `verification.txt` is the spine's listing of what
`fang verify` found, written where Renode is installed and compared only
there; it prints no tool version, so nothing machine-specific reaches it. The
event records are not shipped in `out/`: a reader learns what was measured from
`verification.txt`, and the recorded events live with the tests as fixtures,
where the measures are tested against them without Renode.

### Where copperhead takes over

Three artifacts are the contract, and nothing else on the fang side changes
when copperhead integrates: the plan schema `fang.emulation/v1`, the event
schema `fang.events/v1`, and the bundle layout.

The verdict and the run's outcome stay two things: the verification reads
`PASS`, `FAIL` or `UNKNOWN`, decided by the gate, and the run ends in a terminal
status of "Tool Terminal Statuses". Copperhead's firmware-simulation
specification names five statuses; they map onto these without a new value:

| Copperhead status | Fang |
| --- | --- |
| PASS | verification `PASS` |
| FAIL | verification `FAIL`, with the evidence and the rejection that failed it |
| INCONCLUSIVE | verification `UNKNOWN`; the evidence names the coverage gap, abstraction or model warning that withheld the measure |
| ERROR | tool status `failed`; the verification stays `UNKNOWN`, and the evidence records the error and the partial events |
| SKIPPED | tool status `skipped` |

Whether an `UNKNOWN` blocks is the gate's policy over a must-be-decided
requirement, so a project with no emulation questions acquires no emulation
blocker, and copperhead's REFUSE and HOLD read fang's verifications rather than
computing their own.

## Risks / Trade-offs

- [A fact verified against source does not hold on v1.17.0] → group 1 of the
  tasks is the spike, run before any kernel code, and a fact that fails revises
  this document and, where it reaches the normative text, RFC 12.
- [Firmware boots and talks while the models hide the defect that matters] →
  pin configuration is measured, model warnings withdraw measures, absence
  decides only in a completed run, and every unmodelled behaviour is a coverage
  gap the evidence lists.
- [A Renode release changes what a script means] → versions outside the checked
  set report unsupported; the version and build are on every evidence entity.
- [The address NACK comes from a log line rather than a probe] → it is used
  only once the spike shows its virtual timestamp exact under synchronous
  logging; no demo measure depends on it — the sensor-missing question measures
  the firmware's behaviour.
- [Committed ELFs drift from their source] → the toolchain version is recorded
  beside them and the README says how to rebuild; whether a later change
  rebuilds reproducibly in CI is RFC 12's open decision 15.

## Migration Plan

Additive. `sensor_node` gains firmware, traits and questions; no other example
changes. `SCHEMA_VERSION` does not move here: traits are not yet part of the
snapshot, and question data lives in `extensions`, which already serializes.

## Open Questions

- The confidence scale for emulated measurements. A descriptor states a
  qualification state; what number that bounds a confidence to is RFC 12's open
  decision 13, and nothing here consumes it beyond recording.
