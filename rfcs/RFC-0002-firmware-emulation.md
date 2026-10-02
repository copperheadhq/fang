# RFC-0002: Firmware emulation

| | |
| --- | --- |
| Status | Draft; to be delivered by the OpenSpec changes `fang-mcu-parts` and `fang-emulation` |
| Author | Animesh Chouhan |
| Date | 2026-10-02 |
| Depends on | RFC-0001: its questions, tool protocol, routing and re-entry through the gate |
| Supersedes | nothing; extends "Simulation Is A Compiler Target", "The Pin Model" and RFC-0001 |

RFC 2119 keywords are normative. Section 7 is the normative part; everything
before it is the argument for it, and everything after it is what is
deliberately left out.

## 1. Summary

A Fang board can say which pin of an MCU carries SCL, record that choice as a
decision, and check that the bus has its pull-ups. It cannot say anything about
the firmware that will run on that MCU, and so it cannot notice that the
firmware drives a pin the board never connected, talks to an address no device
answers on, or hangs when a sensor is missing. Those defects are found at
bring-up, on a fabricated board, which is the most expensive place to find
them.

This RFC lets a Fang program ask questions about compiled firmware running on
the board it describes. A program binds a firmware ELF to its MCU, and declares
an **emulation question** beside the requirement it serves: the stimuli applied,
the faults injected, and the **measures** taken over what the emulator
observes. The kernel compiles the board and the question into a **plan** in
which every connection is already resolved from the graph — which I2C
controller a device sits on, at which address, through which pins, configured
how. It lowers the plan into Renode's native input, runs Renode across a
process boundary, and reads back a stream of timestamped **events** recorded by
**probes** this RFC adds to Renode. Measures turn events into `Decimal`
quantities, and from there the loop is RFC-0001's unchanged: the measurements
re-enter through the commit gate, and the constraint evaluator that already
exists decides the requirement.

The first target is one board: an STM32F401RE with an HS3001 temperature and
humidity sensor on I2C1, a status LED and a UART. The whole design is sized to
make that board work end to end — a Fang program, a committed ELF, Renode, and
a requirement decided through the gate — before any second part is supported.

Emulation is a finding, not a proof. A pass says that the declared behaviour
was observed on models whose boundaries the evidence names; it does not say
the fabricated board will work.

## 2. Motivation

**The pin choice is recorded and never checked.** `lowering._choose` picks a
pin for each signal in declared order, and "A Pin Choice Is A Recorded
Decision" turns the choice into a decision entity. The firmware is written
separately, by hand, against a pinout someone copied. Nothing compares the two.

**An I2C address lives in one place, and it is not the board.** `I2C` in
`fang/interfaces.py` has no address. The address exists only as a `#define` in
the firmware, so two devices at one address on one bus, or a strap pin tied the
wrong way, cannot be seen by any check the kernel runs.

**Pins can come from two controllers.** `_choose` treats each signal on its
own. An MCU whose SCL candidates belong to I2C1 and I2C2 can be lowered to SCL
on one controller and SDA on the other, and the lowering is still accepted,
because nothing tells it the candidates belong to different peripherals.

**The verification loop stops at the MCU's pins.** RFC-0001 reaches circuits,
rules and RF. No question can be asked about the program that will run on the
board, so the class of defect that only appears when firmware meets hardware —
wrong address, wrong pin, omitted initialization, no timeout — has no level in
the ladder.

The origin of this RFC is Copperhead's firmware-simulation specification
(v0.1, 2026-10-02), which proposes the whole product: a hosted runner, a model
catalogue, orchestration and physical qualification. This RFC is the part of it
that belongs to fang — the board semantics, the plan, the lowering, the
observation and the verdict — sized so that it works on its own before
copperhead integrates it.

## 3. Renode, and what it does and does not do

Renode (Antmicro, MIT licence) runs unmodified firmware binaries against
platform descriptions written in its own `.repl` format, drives them from
`.resc` scripts, and advances in virtual time. It is reached as an executable,
headless (`renode --console --disable-gui`), which is what "Backends Are
Reached Across A Process Boundary" asks for, and it needs no Robot Framework:
`renode-test` is only the Robot wrapper.

Renode is not installed on the machine this was written on. Every claim below
was verified against Renode's source at `renode` 8aa2c8d and
`renode-infrastructure` e0b8c33 (both 2026-10-02, after the v1.17.0 release of
2026-09-07), not against a running install. The spike in section 5.1 checks
each one against v1.17.0 before the delta spec is written, and a claim that
does not survive the spike is corrected here first.

### 3.1 Facts that shape the design

| Fact | Consequence for this design | Source |
| --- | --- | --- |
| There is no STM32F401 platform. Upstream runs a `nucleo_f401re` Zephyr ELF on `platforms/cpus/stm32f4.repl`, a superset built on the F40x: more flash and RAM, Ethernet, CAN, USART3, UART4/5, extra timers. | Firmware that touches a peripheral the F401 does not have runs in emulation and faults on silicon. Fang ships its own F401 platform file, derived from upstream, with the F401's memory map and peripheral set. | `platforms/cpus/stm32f4.repl`; `tests/peripherals/HS3001.robot` |
| The clock controller is a stub: its registers read back what was written and "do not affect other peripherals or their clocks". SysTick is fixed at 72 MHz in the platform file; general timers at 10 MHz. An F401 runs at up to 84 MHz. | A firmware clock misconfiguration is invisible. Virtual-time measurements hold only under the core clock the platform assumes, which is recorded as an assumption on every run. Clock configuration is a standing coverage gap. | `STM32F4_RCC.cs:22-34`; `stm32f4.repl:40` |
| I2C and UART controllers ignore GPIO configuration. A sensor registers on the controller by address (`@ i2c1 0x44`); the controller never consults the pins' mode or alternate function. GPIO *outputs* do honour the mode register: a write reaches a connected receiver only in output mode. | Firmware with the wrong alternate function on PB8/PB9 still talks to the sensor. Fang measures pin configuration directly (4.8) rather than trusting the engine to route through it. A GPIO observation on the pin the board assigns does test the firmware's pin choice. | `STM32F1_I2C.cs` (a `SimpleContainer<II2CPeripheral>`); `STM32_GPIOPort.cs:111-175` |
| The I2C controller does not model ACK/NACK bits. It sets the address-NACK flag only when no target is registered at the address. A data-phase NACK cannot be injected. | The one I2C fault available is an absent device. Every other I2C fault is refused at plan time (4.7). | `STM32F1_I2C.cs:107,418-426` |
| I2C DMA is not implemented: `DMAEN` is a tagged flag, and the DMA request lines are declared and never driven. | Firmware that reads the sensor by DMA does not work in emulation. The probe reports a write to `DMAEN` as a model warning, and the affected measures stay undecided (4.10). | `STM32F1_I2C.cs:77,79,238` |
| There is no I2C transaction log. Register-level access logging exists for bus peripherals; logs are asynchronous unless synchronous logging is configured. | Events come from probes fang adds (4.9), not from scraping logs. | grep over `renode-infrastructure`; `Logger.cs:829` |
| An I2C target implements `Write(byte[])`, `Read(int)` and `FinishTransmission()`. C# compiled at load time is supported with `include @file.cs`. | A probe is a C# class that implements the I2C target interface, wraps the real sensor model, and records each call. No Renode build is needed. | `II2CPeripheral.cs`; `IncludeFileCommand.cs:85` |
| Shipped sensor models include `HS3001`, `SI70xx`, `TMP103`, `TMP108`, `BMP180`, `LPS25HB`, `LSM6DSO_IMU`, `ICM20948`, `ADXL345` and others. `HS3001` exposes `Temperature` and `Humidity` as `decimal` properties, and is tested upstream on `nucleo_f401re`. | HS3001 is the first sensor: the firmware-and-model pair is already exercised upstream, and a stimulus is a property assignment. The upstream test shows the sensor's own quantization (25.00 °C reads back as 25.01 °C), which a tolerance has to allow. | `Sensors/HS3001.cs:191-227`; `HS3001.robot` |
| The default pseudo-random seed is drawn per process. `emulation SetSeed` fixes it. | Every script sets the seed before anything else. A fixed seed is necessary and is not by itself proof of determinism; the acceptance test runs the same plan ten times and compares. | `PseudorandomNumberGenerator.cs:86` |
| Inputs from the host — monitor commands over a socket, the external control API — land at synchronization points chosen by host timing. | The whole scenario is compiled into the script before the run starts. Nothing drives Renode live during a run that produces evidence. | inferred from the time framework; checked in the spike |
| `TimeInterval` parses with an unanchored pattern and no units: `"100ms"` is read as 100 seconds. | The lowering writes every time as decimal seconds (`"0.1"`), from the `Decimal` quantity, and a golden-file test pins the form. | `TimeInterval.cs:44` |
| `renode --version` prints `Renode v1.17.0` and a build line carrying the build date and commit. | The first line is the version the tool reports; the full build line is recorded on the evidence. | `src/Renode/Program.cs:134-148` |

### 3.2 Considered and set aside

| Option | Why not |
| --- | --- |
| **Robot Framework** (`renode-test`) | Not needed to drive Renode, and its reports are not the result contract. The script is a plain `.resc`. |
| **pyrenode3**, **renode-run** | Wrappers, and neither is published on PyPI. Binding to a wrapper in place of the native input is what "Simulation Is A Compiler Target" forbids. |
| **The external control API**, **the monitor socket** | Live control is host-timed and so nondeterministic. Useful for a person debugging; never for a run whose events become evidence. |
| **Renode's Docker image** | Has no 1.17.0 tag as of this writing. The portable Linux tarball, pinned by digest, is the reference install. |
| **QEMU** | Its device models are compiled into the emulator, so every sensor is a patch to QEMU. Renode loads a C# model at run time. |
| **Wokwi**, **Simantic** | Hosted products whose engines are not published. Fang cannot run either as a local backend under a licence it can name. |

## 4. Design

### 4.1 Terms

- A **firmware binding** names an ELF, relative to the project root, and the
  target it was built for. It attaches to the MCU as a trait.
- A **platform model** describes the MCU to the emulator: Fang ships it, the
  MCU's `Simulatable` trait names it, and its descriptor maps the part's
  surfaces and pins to the emulator's peripherals.
- A **peripheral model** describes an external device: a sensor's model, named
  by the device's `Simulatable` trait, with a descriptor of its inputs, the
  faults it supports, and what it can be observed doing.
- An **emulation question** is a question in RFC-0001's sense, whose method is
  `emulation` and whose level is **behavioural**. It names the requirement, the
  firmware, the stimuli, the faults, the run's virtual duration, the parts
  deliberately abstracted, and the measures.
- A **stimulus** sets a peripheral model's input at a virtual time. A **fault**
  is a named mechanism a peripheral model declares it supports.
- A **probe** is a small model fang adds to the emulator. It records what a
  device, a pin or a UART observed, with the virtual time.
- An **event** is one line of the probes' record: a sequence number, a virtual
  timestamp in integer nanoseconds, the entity it came from, a type and a
  payload.
- A **measure** over events turns the record into one number: the time of the
  first matching event, a count in a window, a latency, a value the firmware
  reported, a count of pin-configuration mismatches.
- A **plan** is the question compiled against a snapshot, with every reference
  resolved. A **bundle** is the plan lowered for Renode: the platform file, the
  script, the probes, the firmware copy and a manifest of digests.

### 4.2 The loop

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
RFC-0001 section 4.6, unchanged: the measurement transaction through propose;
accepted commits, a failed hard constraint records FAIL with the evidence
```

### 4.3 What a board must say

Three additions to the part model, each useful before any emulator exists.

**A port is one peripheral instance.** An MCU declares one interface port per
peripheral instance — `i2c1`, `usart2` — and names the instance. A pin
candidate in the pin map carries its alternate-function number:

```python
i2c1 = I2CPort(peripheral="I2C1", voltage=3.3 * V, bit_rate=100 * kHz)

pinmap = PinMap({
    "i2c1.scl": {"PB8": AF(4), "PB6": AF(4)},
    "i2c1.sda": {"PB9": AF(4), "PB7": AF(4)},
    ...
})
```

Because the candidates of one port all belong to one controller, a lowering
cannot give SCL to I2C1 and SDA to I2C2: the mixed assignment in section 2 is
ruled out by construction rather than by a check. Today's form — a list of
candidate names — stays valid for parts that are not MCUs. The alternate-function
number is datasheet data and carries a citation like any other.

**An I2C address is derived, not written twice.** A device's I2C port carries
its address: either fixed (`address=0x44`), or a base and a strap pin with the
address each strap connection selects. A strapped address is resolved from the
graph: the net the strap pin sits on is the ground domain, the device's own
supply rail, or one of its own bus signals, and the address follows. A strap pin
on no net is refused rather than assumed, and two devices at one address on one
bus are refused naming both. The HS3001 has a fixed address, so the demo board
uses only the first form; the second is in this change because the collision
check needs every address.

**Package pads and port pins stay separate.** They already are: `Pin("PB8",
number="61")` records the vendor name and the pad. Nothing in this design ever
derives a GPIO port and index from a pad number, or parses one from a vendor
name. The platform model's descriptor is what maps `PB8` to the emulator's
`gpioPortB` pin 8, and a pin the descriptor does not map is refused by name.

### 4.4 Binding firmware and models

Models are carried the way SPICE models are carried today, as `Simulatable`
traits, with `backends=("renode",)`:

```python
self.mcu.add_trait(Simulatable(model_kind="renode_platform",
                               backends=("renode",), source="fang:stm32f401re"))
self.env.add_trait(Simulatable(model_kind="renode_peripheral",
                               backends=("renode",), source="renode:Sensors.HS3001"))
self.mcu.add_trait(Firmware("firmware/build/sensor_node.elf", target="stm32f401re"))
```

`source` names a model **descriptor** fang ships, one per supported model. A
descriptor states the emulator class or platform file, the part numbers it
stands for, its inputs with the unit the model takes (`temperature` in `degC`,
so a stimulus in any temperature unit converts exactly), the faults it supports, the events it can
produce, its provenance (the Renode commit it was read from, the licence), what
it does not model, and its qualification state — *experimental*, *tested in
emulation*, or *hardware-correlated*. A `source` with no descriptor is refused;
there is no generic sensor to fall back to. Long-term the descriptors belong to
a model catalogue copperhead serves; until then they are data in the fang
package.

The firmware binding names a path and a target. The ELF's **digest is not part
of the graph**: rebuilding firmware is not a design change, and putting the
digest in the snapshot would turn every build into a revision. The digest is
recorded on the run's `Evidence`, and `fang verify` reports a verification as
**stale** when the bound file's current digest differs from the one its
evidence names. A question may name a different ELF for itself, which is how
one board carries questions about more than one build.

### 4.5 The question

```python
#: Dimensionless, for counts, as the buck regulator example declares `ratio`.
count = UnitLiteral("1")

class SensorNode(System):
    sensor_ready = Requires("The firmware reads the sensor within 200 ms of reset ...")

    first_read = Parameter("s", description="when the firmware first reads the sensor")
    reported = Parameter("degC", description="the temperature the firmware reports")
    slow_blinks = Parameter("", description="status LED rises between 1 s and 2 s")
    mux_mismatches = Parameter("", description="I2C pins configured otherwise than the board requires")

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

    def constraints(self):
        require(self.first_read <= 200 * ms)
        require(self.reported >= 24.95 * degC)
        require(self.reported <= 25.05 * degC)
        require(self.slow_blinks == 1 * count)
        require(self.mux_mismatches == 0 * count)
```

`Emulates` is a rationale declaration, filed beside `Requires`, `Verifies` and
RFC-0001's `Simulates`, and it elaborates to a `Verification` with result
`UNKNOWN`. Every field is part of the graph. That matters more here than for a
circuit question: an assertion window is what turns a failure into a pass, so
widening `within` is a transaction with a diff, provenance and the gate's
policy, never an edit to a file the gate does not see.

Measures, stimuli and faults name **part surfaces** — `env`, `mcu.status`,
`mcu.usart2` — never emulator names. The plan resolves a surface through the pin
map and the platform descriptor.

### 4.6 The plan: everything resolved before anything runs

`compile_plan` for an emulation question is "Simulation Plan Validation"
applied to a board with firmware. It resolves, or refuses naming what is
missing:

- **The target.** Exactly one component carries a `renode_platform` model and a
  firmware binding (or the question names one), and the firmware's target is
  the one the platform describes.
- **The scope.** The MCU, and every component that shares a net with an MCU pin
  the question touches. Each component in scope carries a peripheral model or
  is listed in `abstracted`. Nothing is abstracted silently, and each
  abstracted part becomes a coverage gap on the run.
- **Each bus.** For each I2C connection in scope: the controller instance (the
  port), the pins the lowering chose and their alternate-function numbers, the
  open-drain requirement (from `SignalSpec(open_drain=True)`), and each
  device's address (4.3).
- **Each observation point.** A `Rises("mcu.status")` resolves to the pin the
  board assigns to that signal, and through the descriptor to a port and index.
- **Each stimulus and fault**, against the peripheral model's descriptor: an
  input it declares, of the right dimension; a fault it supports.
- **The window.** `run_until` is required. There is no default duration.

The plan is canonical JSON (`fang.emulation/v1`) written by
`fang.serialization`: mappings sorted, quantities as `Decimal` strings, times
as integer nanoseconds. It is a function of the snapshot and the question, and
its own content hash identifies it. The snapshot hash is recorded beside it but
is not the plan's identity, because the snapshot hash covers provenance and so
the checkout's absolute path; two machines preparing the same question produce
the same plan hash.

### 4.7 Stimuli and faults

A stimulus is `At(time, "<surface>.<input>", quantity)`. The lowering orders
stimuli by time and emits the run as segments: run to the first stimulus, set
the input, run to the next, and so on to `run_until`. The stimulus is also
written into the event record when it is applied, so a latency can be measured
from it.

A fault names its mechanism. The one this RFC delivers is `Absent("env")`: the
device is not attached, and the controller reports an address NACK because no
target answers at its address. A data-phase NACK, a malformed response, a stuck
data line and clock stretching are refused at plan time as unsupported by the
model, naming the fault. A stuck line is an electrical condition, and a device
that stops responding is not the same fault; neither is approximated by the
other.

### 4.8 Pin configuration is measured

Because the engine routes I2C and UART without consulting GPIO (3.1), a
firmware that configures the wrong pins would pass every bus measure. So pin
configuration is observed directly. At the end of the run, and at any virtual
time a measure names, a probe reads the mode, output-type and
alternate-function registers of each GPIO port the plan's buses use, and
writes them into the event record. `PinConfig("mcu.i2c1")` compares them to
what the board requires — alternate-function mode, the declared AF number,
open-drain for an I2C signal — and measures the number of mismatched pins.
`require(self.mux_mismatches == 0 * count)` then decides it.

Register addresses come from the platform descriptor, not from the kernel. A
probe reads only registers without read side effects; the I2C status register,
whose NACK flag clears on read, is never read by a probe.

### 4.9 Observation: probes and events

Events come from probes fang adds, loaded with `include` from C# sources
shipped in the fang package:

- **The I2C probe** implements the I2C target interface, registers at the
  device's address, forwards every call to the real sensor model, and records
  each `Write`, `Read` and `FinishTransmission` with its bytes.
- **The GPIO probe** is a receiver connected to a port pin's output, recording
  each edge.
- **The UART probe** sits on the UART, recording each line the firmware
  transmits.
- **The recorder** they share writes one file, `events.jsonl`, synchronously,
  each line stamped with the machine's virtual time in integer nanoseconds and a
  sequence number.

An event names the **entity** it came from — the plan maps probe names back to
entity identifiers — so the record is in the board's terms, not Renode's. The
types are `run.start`, `stimulus`, `uart.line`, `gpio.edge`, `i2c.write`,
`i2c.read`, `i2c.stop`, `i2c.nack`, `register.snapshot`, `model.warning` and
`run.end`, whose payload gives the reason the run ended: `completed`,
`timeout` or `crashed`. The address NACK in an absent-device run is not seen
by any probe, because no target is registered at that address; it is taken
from the controller's warning in the engine log, under synchronous logging and
virtual timestamps, and the spike confirms its timestamp is exact before the
event is relied on.

**A firmware's report is not an observation of the bus.** `UartValue` reads a
number the firmware printed. It is recorded on the evidence as the firmware's
report, and a measure that the requirement states at the bus — a register read,
a transaction — cannot be satisfied by a UART line.

### 4.10 Measures over events

| Measure | Measures | Dimension |
| --- | --- | --- |
| `FirstAt(match)` | virtual time of the first matching event | time |
| `Count(match, within=(a, b))` | matching events in `[a, b)` | dimensionless |
| `Latency(from_, to)` | time from the first `from_` to the first `to` after it | time |
| `UartValue(uart, prefix=, unit=)` | the number after `prefix` on the first matching line | the stated unit |
| `PinConfig(port)` | pins whose configuration differs from what the board requires | dimensionless |

The matches are `I2CRead(device, register=None)`, `I2CWrite(device,
data=None)`, `Rises(surface)`, `Falls(surface)` and `UartLine(uart,
contains=)`. An ordering requirement is a latency: "A before B" is
`Latency(A, B)` measured, and absent when B never follows A.

Two rules keep a measure honest about what the run could see:

- **Absence is an observation; an incomplete run is not.** In a run that ended
  `completed`, an event that never occurred has been observed not to occur
  before `run_until`, and `require(self.first_read <= 200 * ms)` is decided
  `FAIL`. In a run that ended `timeout` or `crashed`, nothing was observed
  after the end, the measure produces no value, and the constraint stays
  undecided.
- **A model warning withdraws what rests on it.** A `model.warning` from a
  component's model — an unhandled register read, a write to `DMAEN` — means the
  firmware did something the model does not cover. Every measure over that
  component's events produces no value, and the evidence names the warning as
  the reason.

### 4.11 The Renode lowering

`fang/renode/` turns a plan into a bundle, as a pure function of the plan:

- `platform.repl`: `using` the platform file named by the platform descriptor,
  then each peripheral model wrapped in its probe at its address, and the GPIO
  probes on their pins.
- `run.resc`: `emulation SetSeed` first; the probes' `include`; the platform;
  `sysbus LoadELF` on the firmware copy; the stimulus segments, every time
  written as decimal seconds; the register snapshots; `quit`.
- The Renode configuration that makes log timestamps virtual and logging
  synchronous.
- `manifest.json`: the plan hash, the digest of every file in the bundle, the
  firmware digest, the seed, and the Renode version the bundle was prepared
  for.

The script carries only commands the lowering writes from a fixed set. No text
from the program reaches the monitor or Renode's Python: surfaces are
validated identifiers, values are `Decimal` strings, and a question has no
field that takes a command. Firmware is untrusted code, and runs inside the
emulator; the script is not a second way in.

**The F401 platform file** (`fang/renode/platforms/stm32f401re.repl`) is
derived from upstream `stm32f4.repl`: 512 KB of flash and 96 KB of SRAM, the
peripherals the F401 lacks removed, and SysTick and the timers set from the
core clock the descriptor assumes. Every remaining difference from silicon —
the stubbed clock controller, I2C without DMA or acknowledgement bits — is
listed in the descriptor and becomes a coverage gap on every run. The file
carries Renode's copyright and MIT notice.

### 4.12 Running Renode

`RenodeBackend` follows `NgspiceBackend`. `available()` finds `renode` on the
path; `version()` reads its first line. `run` copies the bundle to a temporary
workspace, runs `renode --console --disable-gui -p --hide-log run.resc` with
no shell, in its own process group, and on the wall-clock limit kills the
group and returns what was recorded with `run.end` reporting `timeout`. A
missing Renode reports unsupported, naming it. A Renode outside the versions
the lowering was checked against reports unsupported, naming the version,
rather than running a script whose meaning may have moved.

The local backend isolates the run only this far: temporary copies of its
inputs, no source tree reachable through the bundle, a time limit, and a
recorded invocation, as "Security And Trust Boundaries" requires. Network
isolation and resource limits beyond that are the hosted runner's, which is
copperhead's, and the evidence of a local run says it was local.

### 4.13 Statuses

The verdict is RFC-0001's: the verification reads `PASS`, `FAIL` or
`UNKNOWN`, decided by the gate. The run ends in one of the statuses "Tool
Terminal Statuses" names. They are two things and stay two things. For the copperhead
integration that follows, the five statuses of the origin specification map
onto them without a new value:

| Origin status | Fang |
| --- | --- |
| PASS | verification `PASS` |
| FAIL | verification `FAIL`, with the evidence and the rejection that failed it |
| INCONCLUSIVE | verification `UNKNOWN`; the evidence names the coverage gap, abstraction or model warning that withheld the measure |
| ERROR | tool status `failed`; the verification stays `UNKNOWN`, and the evidence records the error and the partial events |
| SKIPPED | tool status `skipped` |

Whether an `UNKNOWN` blocks is the gate's policy over a must-be-decided
requirement, as it is for every other question. A project with no emulation
questions acquires no emulation blocker.

### 4.14 Determinism

- A plan is a function of the snapshot and the question, identified by its own
  hash. A bundle is a function of the plan.
- The seed is set before anything else in the script. The run takes no input
  from the host after it starts.
- Event times are integer virtual nanoseconds, and every number that crosses
  back is a `Decimal`.
- The Renode version and build line, the firmware digest and the plan hash are
  recorded on every evidence entity. Two Renode builds are two pieces of
  evidence.
- The suite runs one plan ten times and requires byte-identical event records.
  If Renode cannot meet that for a configuration, the run reports the
  difference rather than picking one record.

### 4.15 The commands

`fang emulate board.py` is the low-level command, as `fang sim` is for SPICE:
compile each emulation question's plan, write the bundle, run Renode, print the
events' summary and each measure's number. `--bundle-only` writes the bundle
without running it, which is what the golden-file tests read and what
copperhead will later execute. `fang verify` routes emulation questions to the
`renode` tool like any other question and reads the answer back through the
gate.

## 5. Phasing

### 5.1 Phase 0: the spike

Before any kernel code, a spike in a scratch directory outside the package
establishes that the engine does what section 3 says. Nothing from it ships
except the files that graduate — the platform file, the probes, the firmware —
each reviewed again as it lands.

1. Install Renode 1.17.0 (the portable Linux tarball, recorded by digest) and
   `arm-none-eabi-gcc`. Neither is installed on the machine this was written
   on.
2. Run upstream's `HS3001.robot` once, unchanged, to confirm the install.
3. Write the demo firmware: bare-metal C at the register level with a
   Makefile, no vendor HAL. USART2 at 115200 baud; I2C1 on PB8/PB9 at
   alternate function 4, open-drain; the HS3001 at 0x44, read every 100 ms and
   printed as `temp=<value>`; the LED on PA5 toggling every 500 ms while
   readings succeed and every 100 ms while the sensor does not acknowledge.
   Build-time flags produce the defective variants: `-DSENSOR_ADDRESS=0x45`,
   `-DI2C_PUSH_PULL`, `-DNO_TIMEOUT`.
4. Write `stm32f401re.repl` by hand from upstream's, and the HS3001 hookup.
5. Write the probes and the recorder; produce `events.jsonl` with virtual
   timestamps.
6. Run the same script ten times and compare the records byte for byte.
7. Confirm that Renode's configuration — virtual log timestamps, synchronous
   logging — can be supplied per run; that the address NACK's warning reaches
   the log with an exact virtual timestamp under it; and that the GPIO
   registers read without side effects.
8. Run each defective variant and record which events differ.

The spike exits with a capability matrix (what is modelled, what is not, what
was confirmed), the hand-written `platform.repl` and `run.resc` that become
the lowering's golden files, and recorded event files that become the measure
tests' fixtures. If the record is not reproducible, or a fact in 3.1 does not
hold, this RFC is revised before anything is proposed.

### 5.2 Tracks

| Track | Delivers | Needs Renode | Depends on |
| --- | --- | --- | --- |
| A. The verification spine | `fang-verification` groups 1, 2, 4, 5 and 8 — codes, question elaboration, the protocol and routing, re-entry, `fang verify` — proven on ngspice (group 3). Rule checks, Touchstone and Xyce leave the critical path. | no | — |
| B. The spike | Section 5.1 | yes | — |
| C. Board data | Ports as peripheral instances with alternate-function candidates; I2C addresses, fixed and strapped; the collision and strap checks; the STM32F401RE and HS3001 parts | no | — |
| D1. The plan | Firmware binding, descriptors, `compile_plan` for emulation, `fang.emulation/v1` | no | C |
| D2. The lowering and backend | `fang/renode/`, the bundle, `RenodeBackend`, golden-file tests against the spike's files | for its live test only | B, D1 |
| D3. Measures | Reading `events.jsonl`; the measures in 4.10; tests over the spike's recorded events | no | B |
| E. The surface and the demo | `Emulates`, `fang emulate`, the example, `regenerate.py` and `test_examples.py` learning the new outputs, AT-F1 and AT-F2 | for live parts only | A, D |

A, B and C start together. B is the critical path and the only real risk;
everything in fang is ordinary work, and most of it is tested without Renode,
the way the SPICE lowering is tested without ngspice.

### 5.3 Changes

| Change | Delivers | Needs |
| --- | --- | --- |
| `fang-verification` (reordered) | The spine and ngspice first; rule checks, Touchstone and Xyce after | nothing new |
| `fang-mcu-parts` | Track C. Useful on its own: it catches address collisions, floating straps and mixed controllers with no emulator | nothing new |
| `fang-emulation` | Tracks D and E: the plan, the lowering, the backend, the measures, `Emulates`, `fang emulate`, the example | the spine; Renode on the path for the live tests |

Neither new change depends on stage 14 or 15. Each is numbered on the roadmap
when it is proposed.

### 5.4 The demo, which is the measure of done

`examples/sensor_node/` is the board: an STM32F401RE; an HS3001 on I2C1 with
its pull-ups; a status LED on PA5 through a series resistor; USART2 on PA2/PA3
to a header. The firmware's source, its Makefile and the built ELF are
committed beside the program, with the toolchain version that built it. Two
questions:

- **startup**: at 25 °C, the first sensor read happens within 200 ms; the
  reported temperature is within 0.05 °C of the stimulus; between 1 s and 2 s
  the LED rises exactly once; no I2C pin is misconfigured.
- **sensor missing**: with the sensor absent, the firmware keeps running —
  between 1 s and 2 s the LED rises at least four times — and makes no read.

The negative cases live in the suite, each failing on the measure it should:
the wrong-address build fails `first_read`; the push-pull build fails
`mux_mismatches`; a variant of the board that assigns the status signal to PA6
fails `slow_blinks`, because the firmware still drives PA5 and Renode delivers
a GPIO write only to the pin the firmware configured; the no-timeout build
fails the sensor-missing question.

The example's `out/` carries the bundle, `events.jsonl` and
`verification.txt`. `test_examples.py` compares them like any other output,
normalizing the Renode build line as it normalizes the compiler version, and
skips them by name where Renode is absent. The program, the parts and the plan
tests run everywhere.

## 6. What copperhead takes over later

Three artifacts are the contract, and nothing else on the fang side changes
when copperhead integrates: the plan schema (`fang.emulation/v1`), the event
schema (`fang.events/v1`), and the bundle layout. Copperhead executes a bundle
— in a sandbox locally, on a hosted worker remotely — where `RenodeBackend.run`
executes it today; `prepare` and `read` stay in fang, so the verdict is the
same code reading the same events whichever runner produced them. Physical
qualification fits the same shape: a logic-analyzer capture decoded into
`fang.events/v1` is read by the same measures, and a hardware-correlated model
is one whose emulated and captured measurements agree within tolerances
declared before the comparison.

## 7. Requirements

These are the normative statements the OpenSpec delta specs carry into the
kernel spec, word for word where they can.

### R1. A Port Is One Peripheral Instance

An MCU part SHALL be able to declare each interface port as one named
peripheral instance, and each pin candidate of such a port SHALL be able to
carry its alternate-function number with a citation. A lowering SHALL assign
all signals of one connection from the candidates of one port. A package pad
number SHALL NOT be used as, or to derive, a port pin index.

### R2. An I2C Address Is Derived From The Board

An I2C device's port SHALL carry its address, fixed or selected by a strap pin.
A strapped address SHALL be resolved from the net the strap pin is on, and a
strap pin on no net SHALL be refused naming the pin. Two devices resolving to
one address on one bus SHALL be refused naming both.

### R3. Firmware Is Bound And Its Digest Is Evidence

A Fang program SHALL be able to bind a firmware file, relative to the project
root, and its target to an MCU. The file's digest SHALL be recorded on the
evidence of every run and SHALL NOT be stored in the snapshot. A verification
whose evidence names a digest different from the bound file's current digest
SHALL be reported stale.

### R4. Emulation Questions Are Declared

A Fang program SHALL be able to declare an emulation question beside the
requirement it serves, naming the stimuli, faults, run duration, abstracted
parts and measures, each by part surface. It SHALL elaborate to a
`Verification` with result `UNKNOWN` and method `emulation`, routed at the
behavioural level. A program SHALL NOT be able to declare its computed result.

### R5. The Plan Resolves Everything Before Anything Runs

Plan compilation SHALL resolve the target, every component in scope, every bus
with its controller, pins, alternate functions and addresses, every observation
point, and every stimulus and fault against its model's descriptor, before
anything runs. A component in scope with no model SHALL be refused unless the
question lists it as abstracted, and each abstraction SHALL be recorded as a
coverage gap. A model with no descriptor, a fault its descriptor does not
support, a stimulus of the wrong dimension, a pin the platform descriptor does
not map, or a missing run duration SHALL refuse the plan naming it. No
substitute model SHALL be used.

### R6. Observation Comes From The Emulator, Not From The Firmware's Report

Bus and pin events SHALL be recorded by probes in the emulator, each with its
virtual time and the entity it came from. A value read from the firmware's UART
output SHALL be recorded as the firmware's report and SHALL NOT satisfy a
measure stated at the bus.

### R7. Pin Configuration Is Measured

Where the emulator does not route a peripheral through its pins'
configuration, the run SHALL record the configuration registers of the pins
that peripheral uses, and a measure SHALL be able to compare them to the
board's required mode, alternate function and output type. A probe SHALL NOT
read a register that has read side effects.

### R8. Absence Is An Observation; An Incomplete Run Is Not

In a run that completed, a measured event that did not occur SHALL decide the
constraints over it as observed not to have occurred before the end of the
run. In a run that timed out or crashed, a measure SHALL produce no value. A
measure over a component whose model reported a warning during the run SHALL
produce no value, and the evidence SHALL name the warning.

### R9. The Run Is Deterministic And Its Inputs Are Identified

A plan SHALL be identified by the hash of its canonical form. The script SHALL
fix the emulator's seed before anything else and SHALL take no input from the
host after the run starts. Event times SHALL be integer virtual nanoseconds.
The emulator's version and build, the firmware digest, the plan hash and the
digest of every bundle file SHALL be recorded on the evidence.

### R10. The Script Carries Only What The Lowering Writes

The emulator script SHALL contain only commands from the lowering's fixed set.
No text from a Fang program SHALL reach the emulator's monitor or its scripting
language.

### R11. The Emulator Is Reported, Never Substituted

A missing emulator, or one outside the versions the lowering supports, SHALL
report unsupported naming what is missing. A run that exceeds its wall-clock
limit SHALL be ended with its whole process group, and its partial events SHALL
be kept with the run reported failed.

### AT-F1. Acceptance: a requirement over firmware behaviour is decided through the gate

GIVEN the demo board, its firmware, and the startup question, WHEN `verify`
runs with Renode installed, THEN the constraints over `first_read`,
`reported`, `slow_blinks` and `mux_mismatches` are decided on the committed
head, each measured parameter is inferred with the run's evidence as its
source, and the evidence names the Renode version, the firmware digest and the
plan hash. AND WHEN the same question runs against the wrong-address build,
THEN the head does not move and the verification reads `FAIL`, with
`first_read` observed absent.

### AT-F2. Acceptance: what cannot be modelled cannot pass

GIVEN the demo board, WHEN the sensor's model is removed and the sensor is not
listed as abstracted, THEN the plan is refused naming the sensor and nothing
runs. AND WHEN a fault the sensor's model does not support is declared, THEN
the plan is refused naming the fault. AND WHEN the startup plan runs ten times,
THEN the ten event records are byte-identical.

## 8. Non-goals and open questions

- **No copperhead integration yet.** No hosted workers, model catalogue,
  orchestrator or REFUSE/HOLD mapping beyond the table in 4.13. Section 6 is
  the contract they integrate against.
- **No physical correlation yet.** No `qualify`, no logic-analyzer capture.
  Every model in this RFC is at most *tested in emulation*, and a measurement's
  confidence is bounded by that.
- **No timing claims beyond virtual time.** The clock tree is not modelled. A
  latency is a statement about the emulated run under the assumed core clock,
  not a cycle-accurate or physical prediction.
- **No I2C faults beyond an absent device.** Data-phase NACK, stuck lines,
  clock stretching and DMA wait for an extension to Renode's I2C controller,
  which is its own change.
- **No second MCU, no SPI, no interrupts as stimuli.** Each is added when a
  board asks for it and its model is qualified.
- **No agent tool.** RFC-0001's reason stands: running a tool from an agent
  session spawns a process, and that needs its own requirement.
- **Open: how an absent event is represented.** `Quantity` ranges are closed,
  with a minimum and a maximum. R8 fixes the semantics — an absent event in a
  completed run decides `first_read <= 200 ms` as `FAIL` — and the
  representation is design.md's to choose: a half-open range after the run's
  end, if `Quantity` can carry one without weakening interval semantics, or a
  measured-absent value the evaluator decides against any upper bound.
- **Open: confidence values.** A descriptor states a qualification state;
  RFC-0001 leaves the confidence scale open, and so does this.
- **Open: rebuilding the firmware.** The example commits the ELF and records
  the toolchain that built it; the suite never rebuilds it. Whether a later
  change adds a reproducible build in CI is left to that change.
- **Open: where descriptors live.** In the fang package now. When copperhead's
  catalogue exists, a descriptor becomes a reference into it, pinned by digest,
  and the fang copies are retired rather than kept in parallel.
