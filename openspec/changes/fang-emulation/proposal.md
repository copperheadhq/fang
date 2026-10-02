# Firmware Emulation

This change implements copperhead RFC 12, *The Copperhead Hardware Kernel and
Fang Language Standard*, version 1.3: Sections 12.11 to 12.14, conformance item
18 of Section 16.1, and acceptance tests 18 and 19 of Section 16.2. The records
it writes follow RFC 3 version 1.5: the firmware binding of Section 5, the
emulation models of Section 8.2, and the verification and measurement records
of Section 14. Both revisions are open as
[copperheadhq/copperhead-rfcs#6](https://github.com/copperheadhq/copperhead-rfcs/pull/6);
the change may proceed while it is open, and claims conformance only to the
version that merges. It depends on the spine of `fang-verification` — questions,
the tool protocol, routing and re-entry — and on `fang-mcu-parts`.
[design.md](design.md) holds the facts about Renode the design was checked
against, the spike that re-checks them, and the demo that is the measure of
done.

## Why

A Fang board can say which pin carries SCL and record the choice as a decision,
but nothing can ask about the firmware that will run on it, so the defects that
appear only when firmware meets hardware — a wrong address, a wrong pin, an
omitted initialization, no timeout on a missing device — are found at bring-up
on a fabricated board. RFC 12 now specifies how compiled firmware runs against
the board a program describes, as one more question whose answer re-enters the
graph through the gate; this change builds it, with Renode as the emulator,
for one demo board before any second part is supported.

## What Changes

- A firmware binding: a trait naming an ELF relative to the program that
  declares the part, as a SPICE model's path is, and the target it was built
  for. Its digest is recorded on each run's evidence,
  never in the snapshot, and a verification whose evidence names a different
  digest from the file's current one is reported stale.
- Emulation models: `EmulationModel` traits naming a
  descriptor fang ships — a platform model for the STM32F401RE derived from
  Renode's F4 platform, and a peripheral model for the HS3001 over Renode's own
  sensor model. A descriptor states the inputs, faults and observable events
  the model supports, what it does not model, and its qualification state. A
  part with no descriptor is refused; nothing falls back to a generic model.
- `Emulates(...)`: a question declared beside its requirement, naming the run's
  virtual duration, stimuli at virtual times, faults by mechanism, abstracted
  parts and measures over events. It elaborates to a `Verification` with method
  `emulation`, routed at the behavioural level to the `renode` tool.
- An emulation plan that resolves the target, the scope, every bus with its
  controller, pins, selectors and addresses, every observation point, and every
  stimulus and fault against its model's declarations, before anything runs —
  written as canonical JSON and identified by its own hash.
- A lowering from the plan to Renode's native input — a platform description,
  a script and the probes — and a backend that runs Renode across a process
  boundary on temporary copies, in its own process group, under a wall-clock
  limit.
- Probes in C#, loaded by the script: an I2C probe wrapping the sensor model, a
  GPIO probe on each observed pin, a UART probe, and a recorder writing one
  event file stamped in integer virtual nanoseconds.
- Measures over events — `FirstAt`, `Count`, `Latency`, `UartValue` and
  `PinConfig` — that produce `Decimal` quantities for RFC 12's re-entry, with
  absence in a completed run decided, an incomplete run decided nothing, and a
  model warning withdrawing the measures over that model.
- `fang emulate`, the low-level command, with `--bundle-only`; `fang verify`
  answers emulation questions like any other.
- The demo: `examples/sensor_node/` gains bare-metal firmware with its source,
  Makefile and committed ELFs, two questions — startup, and a missing sensor —
  and outputs, three of which (the plan, the platform description and the
  script) need no Renode to regenerate. Defective builds and a board variant
  live in the suite, each failing on the measure it should.

## Capabilities

### New Capabilities

None. The project holds one capability and this change extends it.

### Modified Capabilities

- `fang-kernel` — adds the requirements for the firmware binding, emulation
  models, emulation questions, the emulation plan, the emulator's script,
  observation by probes, measured pin configuration, absence and incomplete
  runs, deterministic and identified runs, an emulator that is reported rather
  than substituted, the emulate command, and the emulation acceptance tests,
  AT-F1 and AT-F2. No existing requirement's text changes.

## Impact

- New modules `fang/emulation.py` (the binding, descriptors, `Emulates`, the
  plan, the measures and the `renode` tool) and the `fang/renode/` package (the
  lowering, the backend, and as package data the platform description, the
  probes and the model descriptors).
- `fang/emulation.py` also holds the `EmulationModel` and `Firmware` traits; `fang/cli.py` gains `emulate`;
  `fang/diagnostics.py` gains codes in the `SIM` area; `pyproject.toml` and
  `MANIFEST.in` ship the package data and the example's firmware.
- `examples/regenerate.py` and `tests/test_examples.py` learn the example's
  emulation outputs, regenerating the plan, platform description and script
  everywhere and skipping the event record and listing, by name, where Renode
  is absent.
- No new Python dependency. Renode 1.17.0 and, to rebuild the firmware,
  `arm-none-eabi-gcc` are found on the path; neither is installed on the
  machine this was planned on, and the suite reports their absence by name.
- The derived platform description carries Renode's copyright and MIT notice.
- Docs: an emulation reference page and a concepts page, the CLI page,
  `README.md`, `CLAUDE.md`, `CHANGELOG.md` and `openspec/ROADMAP.md`.
