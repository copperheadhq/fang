---
title: Emulation
description: Running a board's compiled firmware in Renode, and what a run can and cannot show.
sidebar:
  order: 8
  attrs:
    data-icon: rocket
---

An emulation question runs the board's compiled firmware in an emulator and
measures what the emulator observes. It is a
[verification question](/reference/verification/) like a circuit one: declared
beside the requirement it serves, routed to a tool, and answered through the
commit gate. The tool is [Renode](https://renode.io), run
across a process boundary.

```bash
fang verify board.py                 # answer every question, emulation included
fang emulate board.py                # run the firmware and print what it measured
fang emulate board.py -o bundles     # also write each question's bundle
fang emulate board.py --bundle-only -o bundles   # write the bundles, run nothing
```

A pass says the declared behaviour was observed on models whose limits the
evidence lists. It does not say the fabricated board works.

## Binding the firmware and the models

```python
from fang.emulation import EmulationModel, Firmware

class SensorNode(System):
    def __init__(self, **overrides):
        super().__init__(**overrides)
        self.mcu.add_trait(EmulationModel(source="fang:stm32f401re"))
        self.mcu.add_trait(Firmware("firmware/elf/sensor_node.elf", target="stm32f401re"))
        self.env.add_trait(EmulationModel(source="renode:Sensors.HS3001"))
```

`EmulationModel` names a descriptor fang ships. There is no generic model to
fall back to: a model naming no descriptor refuses the plan. Two descriptors
ship today.

| Descriptor | Stands for | Qualification |
| --- | --- | --- |
| `fang:stm32f401re` | The STM32F401RE, on a platform description derived from Renode's F4 one | tested in emulation |
| `renode:Sensors.HS3001` | Renesas's HS3001, on Renode's own model | tested in emulation |

`Firmware` names an ELF relative to the program that declares the part, and
the target it was built for. Its digest is not part of the snapshot, because
rebuilding firmware is not a design change; every run records the digest on
its evidence, and `fang verify` reports a verification whose evidence names a
different digest as stale.

## Declaring a question

```python
from fang.emulation import (
    Absent, At, Count, Emulates, FirstAt, I2CRead, PinConfig, Rises, UartValue,
)

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
    abstracted=("scl_pullup", "sda_pullup", "series", "console"),
)
```

Each measure writes into a parameter the system declares, and constraints over
those parameters are what the run decides. Everything is named by part surface
— `env`, `mcu.status`, `mcu.usart2` — never by an emulator name. The question
is part of the graph, so widening a window is a transaction with a diff, not an
edit nobody sees.

| Field | Means |
| --- | --- |
| `run_until` | The run's virtual duration. There is no default. |
| `stimuli` | `At(time, "<device>.<input>", value)`: a model input set at a virtual time |
| `faults` | `Absent(device)`: the device is not on its bus, so its address goes unanswered |
| `abstracted` | Parts in scope deliberately left without a model, each a coverage gap |
| `firmware` | An ELF for this question only, in place of the part's binding |
| `seed` | The emulator's random seed; `0` unless named |

### Measures

| Measure | Measures | Unit |
| --- | --- | --- |
| `FirstAt(match)` | The virtual time of the first matching event | time |
| `Count(match, within=(a, b))` | Matching events in `[a, b)` | dimensionless |
| `Latency(from_, to)` | Time from the first `from_` to the first `to` after it | time |
| `UartValue(uart, prefix=, unit=)` | The number after `prefix` on the first matching line | the stated unit |
| `PinConfig(port)` | Pins configured otherwise than the board requires | dimensionless |

The matches are `I2CRead(device)`, `I2CWrite(device)`, `Rises(surface)`,
`Falls(surface)` and `UartLine(uart, contains=)`. An ordering requirement is a
latency.

## The plan

Before anything runs, the question compiles into a plan in which everything is
resolved from the graph: the component that runs the firmware and the target
its firmware was built for; the scope, being every component sharing a net with
a pin the question touches; each bus's controller (the port's `peripheral`),
its chosen pins and their selectors, open drain from the interface, and each
device's address from `resolve_address`; each observed pin through the
platform model's own pin table; and each stimulus and fault against the model
it names. A plan that cannot be resolved is refused, naming what is missing.

| Code | Refused because |
| --- | --- |
| `SIM-0009` | A model names a descriptor fang does not ship |
| `SIM-0010` | A component in scope has neither a model nor an abstraction |
| `SIM-0011` | A fault the device's model does not support |
| `SIM-0012` | A stimulus names an input its model lacks, or a value of the wrong dimension |
| `SIM-0013` | A pin the platform model does not map; a port is never derived from a pin's name |
| `SIM-0014` | No run duration |
| `SIM-0015` | No firmware is bound, or it was built for another target |
| `SIM-0016` | A bus device's controller or address cannot be resolved |

The plan is canonical JSON, identified by the hash of its own canonical form,
so two machines preparing the same question produce the same plan.

## The run

The plan lowers into Renode's own input: a platform description, a script, and
probes compiled by Renode at load. A bundle holds all of it with the firmware
and a manifest of digests, and runs on its own:

```bash
fang emulate board.py --bundle-only -o bundles
cd bundles/startup && renode --console --disable-gui run.resc
```

The script fixes the seed first, applies every stimulus at its virtual time
from inside the script, writes every duration as decimal seconds, and takes no
input once the run starts. Renode 1.17.0 is the version the lowering was
checked against; another reports unsupported. A run that outlives its
wall-clock limit is ended with every process it started, and its partial
events are kept.

## What a run can see

Events come from probes in the emulator — what a device was asked and
answered, what a pin did, what a UART carried — never from the firmware's
account of itself. A number read from the console is recorded as the
firmware's report.

Three rules keep a measure honest:

- **Absence is an observation; an incomplete run is not.** An event that did
  not occur in a completed run is measured as the half-open range after the
  run's end, so `first_read <= 200 ms` fails after a two-second run and stays
  undecided after a 100 ms one. A run that timed out or crashed measures
  nothing.
- **A model warning withdraws what rests on it.** A warning the model's
  descriptor does not expect means the firmware did something the model does
  not cover; every measure over that model has no value, and the evidence
  names the warning. A warning the descriptor expects is the coverage gap it
  stands for.
- **Pin configuration is measured.** Renode's I2C and UART controllers do not
  consult the pins' configuration, so firmware with the wrong pin setup would
  pass every bus measure. `PinConfig` reads what the firmware wrote to the
  mode, alternate-function and output-type registers, judging the output-type
  register by its writes because Renode does not store it.

## Evidence

Each run's evidence names Renode's version and build, the firmware's digest,
the plan's hash, the seed, the digest of every file in the bundle, that the
run was local, the assumptions, and every coverage gap. Confidence is bounded
by the models' qualification: `0.8` for a model only tested in emulation.

## What is not modelled

The descriptors list it, and every run reports it: the clock tree (the core is
taken to run at the 16 MHz the part resets to), I2C DMA, I2C acknowledgement
beyond an absent device, I2C bus timing, the HS3001's conversion time, and the
GPIO output-type register's storage. After an address NACK Renode's I2C model
keeps STOP set where silicon clears it, so firmware that sets START by
read-modify-write of `CR1` has its next transaction swallowed.

[`examples/sensor_node/`](https://github.com/copperheadhq/fang/tree/main/examples/sensor_node/)
is the worked example: the board, its firmware with three deliberately broken
builds, and the two questions it is verified against.
