## MODIFIED Requirements

### Requirement: Emulation Models Declare What They Cover

The component that runs firmware and the devices around it SHALL reach the
emulator through models naming a descriptor the toolchain ships. A descriptor
SHALL state the part it stands for, the inputs it accepts with their units, the
faults it supports, the events it can produce, what it does not model, the
warnings the model is expected to report with the coverage gap each stands for,
its provenance and its qualification state: experimental, tested in
emulation, or hardware-correlated. A platform descriptor SHALL name the
emulator that runs it, SHALL map the component's ports and pins to that
emulator's, and, where the part's clock is set by configuration held outside
its firmware, SHALL declare the configuration the part ships with and the
values it covers. Where its emulator gives no warning when firmware writes a
register the model does not implement, a platform descriptor SHALL name those
registers. A model naming no descriptor SHALL be refused, and no part SHALL
fall back to a generic model.

#### Scenario: An unknown model is refused

- **WHEN** a part's emulation model names a descriptor the toolchain does not
  ship
- **THEN** the plan is refused naming the part and the descriptor
- **AND** no substitute model is used

#### Scenario: What a model does not cover is a coverage gap

- **WHEN** a run uses a model whose descriptor lists behaviour it does not
  model
- **THEN** every listed behaviour is a coverage gap on the run's evidence

#### Scenario: A pin's emulator port is the descriptor's, not a guess

- **WHEN** an observation names a pin the platform descriptor does not map
- **THEN** the plan is refused naming the pin
- **AND** no port is derived from the pin's name or pad number

#### Scenario: Every platform descriptor names its emulator

- **WHEN** the shipped descriptors are loaded
- **THEN** the STM32F401RE's names Renode and the ATtiny84A's names simavr
- **AND** the ATtiny84A's maps OC0A to PB2, OC0B to PA7, OC1A to PA6 and OC1B
  to PA5, and declares the low fuse 0x62, the high fuse 0xDF and the extended
  fuse 0xFF as the part ships

### Requirement: Emulation Questions Are Declared

A Fang program SHALL be able to declare an emulation question beside the
requirement it serves, naming the run's virtual duration, its stimuli, its
faults, the parts it abstracts, its measures, each by part surface, and,
where its target's platform declares clock configuration, the configuration
the part is programmed with. The question SHALL elaborate to a verification
with result unknown and method `emulation`, routed at the behavioural level,
and SHALL record the emulator its target's platform model names. Only that
emulator's tool SHALL cover the question: a question is never run on an
emulator its platform model does not describe, and where that emulator is
missing the question is reported unsupported. A question that records no
emulator, being one elaborated before emulators were recorded, SHALL be
covered by Renode's tool, since every such question was Renode's. A program
SHALL NOT be able to declare a computed result for it.

#### Scenario: A question elaborates to an unanswered verification

- **WHEN** a program declares an emulation question
- **THEN** the snapshot holds a verification with result unknown, method
  `emulation`, the requirement it serves, the emulator its target's platform
  model names, and the question's stimuli, faults, measures and duration

#### Scenario: A question routes to the emulator

- **WHEN** an emulation question's measured parameters are not already decided
- **THEN** it is routed at the behavioural level to the tool of the emulator
  its target's platform model names: Renode for the STM32F401RE board, simavr
  for the ATtiny84A board

#### Scenario: One emulator never stands in for another

- **WHEN** an ATtiny84A question is verified on a machine with Renode installed
  and simavr absent
- **THEN** the question is reported unsupported naming simavr, and Renode is
  not run

#### Scenario: A question with no recorded emulator is Renode's

- **WHEN** a verification's question was recorded with no emulator
- **THEN** it routes to Renode's tool

#### Scenario: A question cannot state its result

- **WHEN** an emulation question is declared with a result
- **THEN** elaboration fails with a `SIM` diagnostic

### Requirement: The Emulation Plan Resolves Everything Before Anything Runs

Compiling an emulation question SHALL resolve, or refuse naming what is
missing: the target component with its platform model and firmware; the scope,
being the target and every component sharing a net with a pin the question
touches, each carrying a peripheral model or listed as abstracted; each bus in
scope with its controller instance, its chosen pins and their selectors, each
a selector the platform descriptor reads, the electrical requirements of its signals, and each device's address, a whole
number the emulator is given as the graph holds it; each
observation point, a signal with several loads being observed on its one pin;
each stimulus and fault against its model's declarations, a stimulus setting an
input to one value at a time within the run, on a device present in the run;
each measure against what the probes can record; the clock, where the
platform declares clock configuration, from the configuration the binding or
the question states; and the run's virtual duration, which has no default and SHALL be positive. A measure that would read the same whatever the
firmware did SHALL be refused rather than measured: a pin-configuration measure
over a port that is no bus in scope with pins of the target, a match naming a
detail its measure does not filter on, a count or a fraction of a window over
a window that is empty or not bounded by times, and a bus match over a device a
fault removes. Every abstracted part SHALL be a coverage gap. The plan SHALL be
canonical and identified by the hash of its canonical form. A plan that
carries no clock SHALL be written in the schema it was written in before
clocks were added, so that a plan that changes in nothing it carries keeps its
hash.

#### Scenario: A component with no model and no abstraction refuses the plan

- **WHEN** a component in scope carries no peripheral model and is not listed as
  abstracted
- **THEN** the plan is refused naming the component and nothing runs

#### Scenario: An unsupported fault refuses the plan

- **WHEN** a question declares a fault its model does not support
- **THEN** the plan is refused naming the fault and the model

#### Scenario: A stimulus of the wrong dimension refuses the plan

- **WHEN** a stimulus sets a model input to a quantity whose dimension the input
  does not accept
- **THEN** the plan is refused naming the input

#### Scenario: A plan without a duration is refused

- **WHEN** a question names no run duration
- **THEN** the plan is refused rather than given a default

#### Scenario: A run of no time or less is refused

- **WHEN** a question names a run duration that is zero or negative
- **THEN** the declaration is refused with the duration's `SIM` diagnostic
- **AND** a plan carrying such a duration is neither compiled nor lowered,
  since its script would run nothing and still finish as completed

#### Scenario: A stimulus that cannot be applied is refused

- **WHEN** a stimulus sets an input to a range or a tolerance, falls before the
  run starts or after it ends, or sets an input of a device a fault removes
- **THEN** the plan is refused naming the input

#### Scenario: A pin configuration over no bus is refused

- **WHEN** a pin-configuration measure names a port that is not an I2C bus of
  the target with a device on it
- **THEN** the plan is refused naming the port, rather than measuring zero
  having checked no pin

#### Scenario: A match detail no measure reads is refused

- **WHEN** a match names a detail its measure does not filter on, such as a
  register for an I2C read
- **THEN** the plan is refused naming the detail, rather than counting every
  event of the match's kind

#### Scenario: An empty or untimed count window is refused

- **WHEN** a count's window, or a fraction of a window's, ends before it
  starts, or is bounded by anything but times
- **THEN** the declaration is refused

#### Scenario: A bus match over an absent device is refused

- **WHEN** a measure matches reads or writes of a device the question's fault
  makes absent
- **THEN** the plan is refused naming the measure, because an absent device
  records nothing and the measure would read the same whatever the firmware did

#### Scenario: A signal with several loads is observed on its one pin

- **WHEN** an edge is measured on a signal of the target that drives two loads
- **THEN** the plan observes the one pin the signal lands on

#### Scenario: An address that is no whole number is refused

- **WHEN** a device on a bus in scope declares an address that is not a whole
  number
- **THEN** the plan is refused naming the device and the address, rather than
  giving the emulator another address in its place

#### Scenario: The plan carries the board's facts

- **WHEN** the demo board's startup question is compiled
- **THEN** the plan names I2C1 as the sensor's controller, the chosen pins with
  their selectors, open drain on both signals, and the address 0x44

#### Scenario: The same question compiles to the same plan

- **WHEN** a question is compiled twice from the same snapshot, on two machines
- **THEN** the two plans are byte-identical and have the same hash

#### Scenario: A plan with no clock is written as before

- **WHEN** the demo board's startup question is compiled
- **THEN** its plan is written in the schema `fang.emulation/v2`, byte for byte
  as before this change, with the same hash
- **AND WHEN** an ATtiny84A question is compiled
- **THEN** its plan carries the clock and is written in the schema
  `fang.emulation/v3`

### Requirement: The Emulator Script Carries Only What The Lowering Writes

The emulator's native input SHALL be a function of the plan alone. The script
SHALL contain only commands from the lowering's fixed set, SHALL fix the
emulator's random seed before anything else, SHALL apply every stimulus at its
virtual time from within the script, and SHALL take no input from the host once
the run starts. No text from a Fang program SHALL reach the emulator's monitor
or scripting language. Every duration SHALL be written in a form the emulator
reads as the duration the plan means. Every probe SHALL have a name of its own,
derived from the whole path of the entity it observes, and a lowering that
would give two probes one name SHALL be refused. Where the emulator's native
input is a program built against its library, the lowering SHALL write the
program's source as the toolchain ships it and a configuration the program
reads, holding only lines of the lowering's fixed set, each value a validated
identifier, an integer or a file name of the bundle; the program SHALL fix,
from the plan's seed and before anything else, every value the emulator would
otherwise draw from the process, such as simavr's device serial number.

#### Scenario: The seed comes first

- **WHEN** a plan is lowered
- **THEN** the script's first command fixes the seed the plan records

#### Scenario: Durations are written as the emulator reads them

- **WHEN** a stimulus is at 100 ms
- **THEN** the script advances to it with the duration 0.1 s, in a form that
  cannot be read as 100 s

#### Scenario: Program text does not reach the script

- **WHEN** a program names a surface or a string containing characters the
  monitor would interpret
- **THEN** the plan is refused, or the text never appears in the script

#### Scenario: Two devices whose paths end alike get two probes

- **WHEN** a plan holds two devices whose paths share their last segment
- **THEN** their probes have different names, and a plan in which two probes
  would share a name is refused by the lowering

#### Scenario: Lowering is deterministic

- **WHEN** the same plan is lowered twice
- **THEN** the platform description and the script are byte-identical

#### Scenario: A runner's configuration carries only what the lowering writes

- **WHEN** an ATtiny84A plan is lowered
- **THEN** the bundle holds the runner's source as shipped, the firmware, its
  flash image, the plan, a manifest, and a configuration whose every line is
  of the lowering's fixed set and names the plan's seed
- **AND** an entity identifier that is not of the lowering's validated form is
  refused rather than written

#### Scenario: The seed fixes what simavr would draw from the process

- **WHEN** an ATtiny84A plan is run twice, in two processes
- **THEN** the device serial number simavr gives the core is the one the
  plan's seed determines, the same in both runs, and not one drawn from the
  process identifier

### Requirement: Observation Comes From Probes, Not From The Firmware's Report

Bus and pin events SHALL be recorded by probes in the emulated platform, each
event carrying a sequence number, its virtual time in integer nanoseconds, the
entity it came from, a type and a payload. A value read from the firmware's
serial output SHALL be recorded as the firmware's report and SHALL NOT satisfy a
measure stated at the bus. Where the platform model observes it, a pin's level
SHALL be recorded only while the firmware drives the pin, whichever peripheral
drives it, and a pin the firmware stops driving SHALL be recorded as released,
at neither level.

#### Scenario: An I2C transaction is recorded at the device

- **WHEN** the firmware reads the sensor
- **THEN** the event record holds the transaction with its virtual time and the
  sensor's entity identifier

#### Scenario: A pin edge is recorded on the pin the board assigns

- **WHEN** the firmware drives the pin the board assigns to the status signal
- **THEN** the event record holds the edge, attributed to that signal

#### Scenario: A printed value is the firmware's report

- **WHEN** a measure reads a number from the firmware's serial output
- **THEN** the evidence records it as the firmware's report
- **AND** it cannot be the measure for a requirement stated at the bus

#### Scenario: A timer's output is recorded only on a driven pin

- **WHEN** an ATtiny84A timer's compare output is enabled on a pin the
  firmware has not made an output
- **THEN** no level is recorded for the pin until the firmware makes it one
- **AND WHEN** the firmware makes the pin an input again
- **THEN** the pin is recorded as released

### Requirement: Absence Is An Observation; An Incomplete Run Is Not

In a run that completed, an event that did not occur SHALL be measured as not
having occurred before the run's end, so that a constraint bounding its time
from above is decided. In a run that ended on a timeout or a crash, or that its
emulator ended of its own accord before the run's virtual duration, a measure
SHALL produce no value. A fraction of a window SHALL be decided over the part
of the window the run observed: where the window begins before the pin's first
recorded level or ends after the run's end, its value SHALL be the interval
spanned by every level the unobserved part could have held. A measure over a
model that reported a warning its descriptor does not expect SHALL produce no
value, and the evidence SHALL name the warning; a warning the platform model's
descriptor does not expect SHALL withdraw every measure of the run. A warning
the model's descriptor expects SHALL NOT withdraw a measure; it SHALL be
recorded on the evidence as the coverage gap the descriptor says it stands
for. A warning SHALL be matched only against the expected warnings of the
descriptor of the model that reported it.

#### Scenario: A read that never happens fails its bound

- **WHEN** a completed two-second run contains no read of the sensor and a
  constraint requires the first read within 200 ms
- **THEN** the constraint is decided as failed

#### Scenario: A short run cannot fail a later bound

- **WHEN** a completed 100 ms run contains no read of the sensor and a
  constraint requires the first read within 200 ms
- **THEN** the constraint stays undecided

#### Scenario: A timed-out run decides nothing

- **WHEN** a run is ended by its wall-clock limit
- **THEN** none of its measures has a value and their constraints stay
  undecided

#### Scenario: A run the emulator ends early decides nothing

- **WHEN** the firmware halts the core in a way the emulator takes for the end
  of the program, before the run's virtual duration
- **THEN** the run has not completed, and none of its measures has a value

#### Scenario: An unexpected model warning withdraws its measures

- **WHEN** the sensor's model reports an access it does not implement, and its
  descriptor does not expect that warning
- **THEN** every measure over the sensor's events has no value
- **AND** the evidence names the warning

#### Scenario: A platform warning withdraws every measure

- **WHEN** the ATtiny84A's model reports a warning its descriptor does not
  expect
- **THEN** every measure of the run has no value, whichever pin it is over
- **AND** the evidence names the warning

#### Scenario: An expected warning is a coverage gap

- **WHEN** the I2C controller's model warns of a write to a timing register its
  descriptor lists as an expected warning
- **THEN** the measures over the bus keep their values
- **AND** the evidence lists the coverage gap the descriptor names for it

#### Scenario: A warning is expected only by its own model's descriptor

- **WHEN** the sensor's model reports a warning that the platform's descriptor
  lists as expected and the sensor's descriptor does not
- **THEN** every measure over the sensor's events has no value
- **AND** a warning only the sensor's descriptor expects, reported by the
  platform's I2C controller, withdraws the measures over the bus

#### Scenario: A window partly before the first level is an interval

- **WHEN** a fraction of a window at level 0 is measured over a window that
  begins 2 ms before the pin's first recorded level, in a 10 ms window whose
  observed 8 ms the pin spent 4 ms low
- **THEN** the measure is the interval from 0.4 to 0.6
- **AND** a constraint that the fraction is at most 0.7 is decided as passed,
  and one that it is at least 0.5 stays undecided

### Requirement: Emulation Runs Are Deterministic And Identified

The evidence of every run SHALL record the emulator's version and build, the
firmware digest, the plan hash, the seed, and the digest of every file the run
was given. Where the emulator's native input is a program built on the host
against its library, the emulator's build SHALL name the library it was built
against by its digest, and the run's outcome SHALL record the compiler.
Repeated runs of one plan on one emulator build SHALL produce byte-identical
event records; a run that cannot SHALL report the difference rather than
choose one record. A run SHALL leave its bundle, its event record, the
emulator's log and its outcome in the workspace it is given, whatever
directory the emulator itself ran from, so that a run whose evidence is
committed keeps them beside it. No file of a run's bundle, and nothing else
its job's hash covers, SHALL carry the hash of the snapshot the job was
prepared against: the job names that snapshot beside its identity, so a change
to anything the run does not read leaves the job, and a measurement of it
current, as it was.

#### Scenario: Ten runs give one record

- **WHEN** the demo's startup plan is run ten times on one emulator build
- **THEN** the ten event records are byte-identical

#### Scenario: Ten simavr runs give one record

- **WHEN** an ATtiny84A plan is run ten times on one simavr build
- **THEN** the ten event records are byte-identical

#### Scenario: Evidence identifies every input

- **WHEN** a run's evidence is read
- **THEN** it names the emulator version and build, the firmware digest, the
  plan hash, the seed and the digest of every bundle file

#### Scenario: An unrelated change leaves the job as it was

- **WHEN** the demo's startup question is prepared against two snapshots that
  differ only in an entity the run does not read, or only in the checkout the
  program sits in
- **THEN** the two jobs have the same hash, and the plan in each bundle names
  no snapshot
- **AND WHEN** the firmware is rebuilt and the question prepared again
- **THEN** the job's hash differs

#### Scenario: A committed run keeps its files

- **WHEN** `verify --commit` runs an emulation question, whether or not the
  run completes
- **THEN** the workspace's simulations directory holds the run's bundle, its
  event record, the emulator's log and its outcome
- **AND WHEN** `verify` runs the question without `--commit`
- **THEN** nothing is written into the workspace

### Requirement: The Emulator Is Reported, Never Substituted

A missing emulator, or one outside the versions the lowering was checked
against, SHALL report unsupported naming what is missing: an installed
emulator of another version SHALL be reported by its version, not as missing.
A run that the emulator cannot make on the host, such as from a temporary
directory whose path it cannot read, SHALL be reported unsupported naming the
reason before the emulator starts, never as a crashed run. Where the
emulator's native input is a program built on the host, a missing compiler,
headers or library, or a build that fails, SHALL be reported unsupported naming
what is missing or the compiler's message, never as a crashed run. A run that
exceeds its wall-clock limit SHALL be ended with its whole process group, its
partial events kept, and the run reported failed with the verification left
unknown.

#### Scenario: A missing emulator reports unsupported

- **WHEN** an emulation question is verified and the emulator is not installed
- **THEN** the question is reported unsupported naming the emulator
- **AND** no result is fabricated

#### Scenario: An unchecked emulator version reports unsupported

- **WHEN** the installed emulator reports a version the lowering was not
  checked against
- **THEN** the question is reported unsupported naming that version and the
  versions the lowering was checked against

#### Scenario: simavr 1.6 is refused for the fault it has

- **WHEN** the installed simavr reports version 1.6
- **THEN** an ATtiny84A question is reported unsupported naming 1.6, the
  version the lowering was checked against, and that 1.6 wires the ATtiny84's
  compare outputs to the wrong pins

#### Scenario: A runner that cannot be built reports unsupported

- **WHEN** simavr's executable is installed but no C compiler is, or its
  headers are not beside it, or the runner fails to build
- **THEN** the question is reported unsupported naming what is missing or the
  compiler's message, and nothing is reported as a crashed run

#### Scenario: A temporary path the emulator cannot read reports unsupported

- **WHEN** the temporary directory a run would be made in has a space in its
  path
- **THEN** the question is reported unsupported naming the directory, and the
  emulator is not started

#### Scenario: A hung run is ended whole

- **WHEN** a run exceeds its wall-clock limit
- **THEN** no process of the run survives, its partial events are kept, and the
  verification stays unknown

### Requirement: The Emulate Command

`fang emulate` SHALL compile each emulation question's plan, write its bundle,
run the question on the emulator its platform model names where that emulator
is installed, and print each measure's value or the reason it has none. With
`--bundle-only` it SHALL write the bundle and run nothing. It SHALL NOT change
a workspace. It SHALL exit non-zero when a question is not runnable or a run
did not complete, and an emulator that is not installed SHALL NOT by itself
make it fail.

#### Scenario: A bundle is written without an emulator

- **WHEN** `fang emulate --bundle-only` runs on the demo board
- **THEN** it writes the plan, the platform description, the script, the probes
  and the manifest, and runs nothing

#### Scenario: An ATtiny84A bundle is written without simavr

- **WHEN** `fang emulate --bundle-only` runs on the Quiet Orbit board
- **THEN** it writes each question's plan, runner configuration, runner
  source, firmware, flash image and manifest, and runs nothing

#### Scenario: Emulate prints what it measured

- **WHEN** `fang emulate` runs on the demo board with the emulator installed
- **THEN** it prints each question's measures and leaves any workspace
  untouched

#### Scenario: Emulate names the emulator each question ran on

- **WHEN** `fang emulate` runs a program whose questions run on simavr
- **THEN** it prints simavr and its version for each run, not Renode

#### Scenario: A run that does not complete fails the command

- **WHEN** `fang emulate` runs a question and the run ends on a timeout or a
  crash
- **THEN** it prints how the run ended and that its measures have no value,
  and exits non-zero

### Requirement: Emulation Acceptance Tests

The suite SHALL hold one test per emulation acceptance criterion, AT-F1, AT-F2
and AT-F3, each skipped by name where the emulator it needs is absent.

#### Scenario: AT-F1, a requirement over firmware behaviour is decided through the gate

- **WHEN** `verify` runs the demo's startup question with the emulator
  installed
- **THEN** the constraints over its measures are decided on the committed head,
  each measured parameter is inferred with the run's evidence as its source,
  and the evidence names the emulator version, the firmware digest and the plan
  hash
- **AND WHEN** the same question runs against the wrong-address build
- **THEN** the head does not move and the verification reads failed, with the
  first read observed absent

#### Scenario: AT-F2, what cannot be modelled cannot pass

- **WHEN** the sensor's model is removed and the sensor is not abstracted, or a
  fault its model does not support is declared
- **THEN** the plan is refused naming the sensor or the fault, and nothing runs
- **AND WHEN** the startup plan runs ten times
- **THEN** the ten event records are byte-identical

#### Scenario: AT-F3, a part whose fuses set its clock, on a second emulator

- **WHEN** `verify` runs the Quiet Orbit board's fade question, its fuses
  stated as programmed for the 8 MHz clock, with simavr installed
- **THEN** it routes to simavr, the constraints over its measures are decided
  as passed on the committed head, and the evidence names simavr's version,
  the firmware digest and the plan hash
- **AND WHEN** the same firmware runs with the fuses the part ships with
- **THEN** the head does not move and the verification reads failed, its
  pulse-width output measured at an eighth of the rate
- **AND WHEN** a question states a low fuse that selects an external clock
- **THEN** the plan is refused naming the fuse, and nothing runs

## ADDED Requirements

### Requirement: Fuses Set An AVR Part's Clock And Are Stated

Where a platform descriptor declares clock configuration, the configuration
SHALL be stated by the firmware binding or by the question, the question's
taking precedence: either as the values of the fuse bytes the part is
programmed with, or as `factory`, the values the descriptor declares the part
ships with. A plan whose configuration is stated by neither SHALL be refused
with its own `SIM` diagnostic, naming the part and how to state it, and SHALL
NOT assume one. A fuse value SHALL be refused, naming the fuse and the bits,
where it selects a clock source the descriptor does not model, or differs from
the part's shipped value in a bit the descriptor does not model. The plan SHALL
resolve the oscillator the fuses select and the clock prescaler they set at
reset, and SHALL record as assumptions the frequency the core starts at, where
the fuses came from, and the time the part spends between reset and its first
instruction, which the run does not model. A change the firmware makes to the
clock prescaler at run time SHALL be modelled as the part makes it: a change
enabled by its timed sequence takes effect, one written outside it does not,
and event times thereafter follow the new clock.

#### Scenario: A part as it ships runs at an eighth of its oscillator

- **WHEN** an ATtiny84A question states its fuses as `factory`
- **THEN** the plan's clock is the internal 8 MHz oscillator divided by 8, and
  its assumptions say the core starts at 1 MHz from the factory fuses

#### Scenario: The fuses the board is programmed with set the clock

- **WHEN** the binding states the low fuse 0xE2
- **THEN** the plan's clock is the internal 8 MHz oscillator undivided

#### Scenario: Unstated fuses refuse the plan

- **WHEN** neither the ATtiny84A's firmware binding nor the question states
  fuses
- **THEN** the plan is refused with the clock's `SIM` diagnostic, naming the
  part, and nothing runs

#### Scenario: A clock source the model does not cover is refused

- **WHEN** a question states a low fuse whose clock-select bits choose an
  external clock
- **THEN** the plan is refused naming the low fuse and its clock-select bits

#### Scenario: An unmodelled fuse bit is refused

- **WHEN** a question states a high fuse that enables the watchdog permanently
- **THEN** the plan is refused naming the high fuse and the bit, rather than
  running without it

#### Scenario: The firmware's own prescaler change is modelled

- **WHEN** firmware on a part with its factory fuses writes the clock
  prescaler's enable bit and, within four cycles, a division of 1
- **THEN** the run records the change, and the pulse-width output's edges
  after it are eight times as frequent as before it
- **AND WHEN** the division is written more than four cycles after the enable
  bit
- **THEN** the clock does not change

### Requirement: Registers An Engine Does Not Model Are Watched

Where a platform descriptor names registers its emulator does not model, the
run SHALL watch the firmware's writes to them, and a write that sets a bit the
descriptor names as unmodelled SHALL be recorded as a model warning from the
platform, naming the register and the value written. The descriptor SHALL NOT
list such a warning as expected, so that it withdraws every measure of the
run.

#### Scenario: A calibration write withdraws the run

- **WHEN** ATtiny84A firmware writes the oscillator calibration register
- **THEN** the run records a model warning naming the register and the value
- **AND** every measure of the run has no value, the evidence naming the
  warning

#### Scenario: A modelled bit does not warn

- **WHEN** ATtiny84A firmware sets only the Timer/Counter1 bit of the power
  reduction register, which the model implements
- **THEN** no warning is recorded and the run's measures keep their values

### Requirement: The Fraction Of A Window A Pin Spends At A Level Is Measured

A Fang program SHALL be able to measure the fraction of a window of virtual
time that a pin of the target spent at a level, naming the pin by part
surface, the level as 0 or 1, and the window by two times, the start before
the end. Its value SHALL be dimensionless: the time the pin was recorded at
the level within the window, over the window's length. Time the pin spent
released counts at neither level. The window SHALL be decided only over what
the run observed, as the absence requirement states.

#### Scenario: A fraction over a fully observed window

- **WHEN** a pin is recorded low for 3 ms of a 10 ms window, and at known
  levels for all of it
- **THEN** the fraction at level 0 is 0.3 and the fraction at level 1 is 0.7

#### Scenario: A level other than 0 or 1 is refused

- **WHEN** a fraction of a window names the level 2
- **THEN** the declaration is refused

#### Scenario: Released time is at neither level

- **WHEN** a pin is released for 4 ms of a 10 ms window and low for the rest
- **THEN** the fraction at level 0 is 0.6 and the fraction at level 1 is 0
