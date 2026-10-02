## ADDED Requirements

### Requirement: Firmware Is Bound And Its Digest Is Evidence

A Fang program SHALL be able to bind a firmware file, named relative to the
program that declares the component, and the target it was built for, to the
component that runs it, as a trait of that component. The binding SHALL NOT
carry the file's digest. Every emulation run SHALL record the digest of the
firmware it ran on its evidence, and a verification whose evidence names a
digest other than the current digest of the file the run resolved SHALL be
reported stale, the file being resolved for that check exactly as it was for
the run. A question SHALL be able to name a firmware file of its own, relative
to the program that declares the question.

#### Scenario: Rebuilding firmware does not change the snapshot

- **WHEN** the bound firmware file is rebuilt with different contents and the
  program is elaborated again
- **THEN** the snapshot is byte-identical to the one before the rebuild

#### Scenario: Evidence names the firmware it ran

- **WHEN** an emulation run completes
- **THEN** its evidence names the firmware file and its digest

#### Scenario: A verification over an older build is stale

- **WHEN** a verification's evidence names a firmware digest and the bound file
  now has a different one
- **THEN** the verify command reports the verification as stale and names the
  file

#### Scenario: Staleness reads the file the run read

- **WHEN** a question is declared in a program in another directory from the
  one that declares the component, and names no firmware of its own
- **THEN** the run and the staleness check both resolve the bound firmware
  relative to the program that declares the component
- **AND** a rebuild of that file reports the verification stale, and nothing
  else does

#### Scenario: A question names its own build

- **WHEN** a question names a firmware file other than the component's binding
- **THEN** the run uses that file and its evidence names it

### Requirement: Emulation Models Declare What They Cover

The component that runs firmware and the devices around it SHALL reach the
emulator through models naming a descriptor the toolchain ships. A descriptor
SHALL state the part it stands for, the inputs it accepts with their units, the
faults it supports, the events it can produce, what it does not model, the
warnings the model is expected to report with the coverage gap each stands for,
its provenance and its qualification state: experimental, tested in
emulation, or hardware-correlated. A platform descriptor SHALL map the component's ports and
pins to the emulator's. A model naming no descriptor SHALL be refused, and no
part SHALL fall back to a generic model.

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

### Requirement: Emulation Questions Are Declared

A Fang program SHALL be able to declare an emulation question beside the
requirement it serves, naming the run's virtual duration, its stimuli, its
faults, the parts it abstracts and its measures, each by part surface. The
question SHALL elaborate to a verification with result unknown and method
`emulation`, routed at the behavioural level. A program SHALL NOT be able to
declare a computed result for it.

#### Scenario: A question elaborates to an unanswered verification

- **WHEN** a program declares an emulation question
- **THEN** the snapshot holds a verification with result unknown, method
  `emulation`, the requirement it serves, and the question's stimuli, faults,
  measures and duration

#### Scenario: A question routes to the emulator

- **WHEN** an emulation question's measured parameters are not already decided
- **THEN** it is routed at the behavioural level to the emulation tool

#### Scenario: A question cannot state its result

- **WHEN** an emulation question is declared with a result
- **THEN** elaboration fails with a `SIM` diagnostic

### Requirement: The Emulation Plan Resolves Everything Before Anything Runs

Compiling an emulation question SHALL resolve, or refuse naming what is
missing: the target component with its platform model and firmware; the scope,
being the target and every component sharing a net with a pin the question
touches, each carrying a peripheral model or listed as abstracted; each bus in
scope with its controller instance, its chosen pins and their selectors, the
electrical requirements of its signals, and each device's address; each
observation point, a signal with several loads being observed on its one pin;
each stimulus and fault against its model's declarations, a stimulus setting an
input to one value at a time within the run, on a device present in the run;
each measure against what the probes can record; and the run's virtual
duration, which has no default and SHALL be positive. A measure that would read the same whatever the
firmware did SHALL be refused rather than measured: a pin-configuration measure
over a port that is no bus in scope with pins of the target, a match naming a
detail its measure does not filter on, a count over a window that is empty or
not bounded by times, and a bus match over a device a fault removes. Every
abstracted part SHALL be a coverage gap. The plan SHALL be canonical and
identified by the hash of its canonical form.

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

- **WHEN** a count's window ends before it starts, or is bounded by anything
  but times
- **THEN** the declaration is refused

#### Scenario: A bus match over an absent device is refused

- **WHEN** a measure matches reads or writes of a device the question's fault
  makes absent
- **THEN** the plan is refused naming the measure, because an absent device
  records nothing and the measure would read the same whatever the firmware did

#### Scenario: A signal with several loads is observed on its one pin

- **WHEN** an edge is measured on a signal of the target that drives two loads
- **THEN** the plan observes the one pin the signal lands on

#### Scenario: The plan carries the board's facts

- **WHEN** the demo board's startup question is compiled
- **THEN** the plan names I2C1 as the sensor's controller, the chosen pins with
  their selectors, open drain on both signals, and the address 0x44

#### Scenario: The same question compiles to the same plan

- **WHEN** a question is compiled twice from the same snapshot, on two machines
- **THEN** the two plans are byte-identical and have the same hash

### Requirement: The Emulator Script Carries Only What The Lowering Writes

The emulator's native input SHALL be a function of the plan alone. The script
SHALL contain only commands from the lowering's fixed set, SHALL fix the
emulator's random seed before anything else, SHALL apply every stimulus at its
virtual time from within the script, and SHALL take no input from the host once
the run starts. No text from a Fang program SHALL reach the emulator's monitor
or scripting language. Every duration SHALL be written in a form the emulator
reads as the duration the plan means. Every probe SHALL have a name of its own,
derived from the whole path of the entity it observes, and a lowering that
would give two probes one name SHALL be refused.

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

### Requirement: Observation Comes From Probes, Not From The Firmware's Report

Bus and pin events SHALL be recorded by probes in the emulated platform, each
event carrying a sequence number, its virtual time in integer nanoseconds, the
entity it came from, a type and a payload. A value read from the firmware's
serial output SHALL be recorded as the firmware's report and SHALL NOT satisfy a
measure stated at the bus.

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

### Requirement: Pin Configuration Is Measured

Where the emulator does not route a peripheral through its pins'
configuration, the run SHALL record the configuration the firmware gives the
pins each bus in scope uses — every write to their configuration registers,
and the registers' values at the end of the run where the model stores them —
and a measure SHALL compare the result with the mode, selector and output type
the board requires, measuring the number of pins that differ. A register the
model accepts without storing SHALL be judged by the firmware's writes to it,
never by a read-back. A probe SHALL NOT read a register that has read side
effects.

#### Scenario: Correctly configured pins measure zero

- **WHEN** the firmware configures the I2C pins in alternate-function mode at
  the board's selector, open drain
- **THEN** the pin-configuration measure is zero

#### Scenario: A push-pull build is caught

- **WHEN** the firmware configures the I2C pins push-pull
- **THEN** the pin-configuration measure counts both pins, though every bus
  transaction succeeded

#### Scenario: An unstored register is judged by its writes

- **WHEN** the model accepts writes to the output-type register without storing
  them, and the firmware writes open drain for both I2C pins
- **THEN** the measure counts neither pin, although the register reads back 0

### Requirement: Absence Is An Observation; An Incomplete Run Is Not

In a run that completed, an event that did not occur SHALL be measured as not
having occurred before the run's end, so that a constraint bounding its time
from above is decided. In a run that ended on a timeout or a crash, a measure
SHALL produce no value. A measure over a model that reported a warning its
descriptor does not expect SHALL produce no value, and the evidence SHALL name
the warning. A warning the model's descriptor expects SHALL NOT withdraw a
measure; it SHALL be recorded on the evidence as the coverage gap the
descriptor says it stands for.

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

#### Scenario: An unexpected model warning withdraws its measures

- **WHEN** the sensor's model reports an access it does not implement, and its
  descriptor does not expect that warning
- **THEN** every measure over the sensor's events has no value
- **AND** the evidence names the warning

#### Scenario: An expected warning is a coverage gap

- **WHEN** the I2C controller's model warns of a write to a timing register its
  descriptor lists as an expected warning
- **THEN** the measures over the bus keep their values
- **AND** the evidence lists the coverage gap the descriptor names for it

### Requirement: Emulation Runs Are Deterministic And Identified

The evidence of every run SHALL record the emulator's version and build, the
firmware digest, the plan hash, the seed, and the digest of every file the run
was given. Repeated runs of one plan on one emulator build SHALL produce
byte-identical event records; a run that cannot SHALL report the difference
rather than choose one record.

#### Scenario: Ten runs give one record

- **WHEN** the demo's startup plan is run ten times on one emulator build
- **THEN** the ten event records are byte-identical

#### Scenario: Evidence identifies every input

- **WHEN** a run's evidence is read
- **THEN** it names the emulator version and build, the firmware digest, the
  plan hash, the seed and the digest of every bundle file

### Requirement: The Emulator Is Reported, Never Substituted

A missing emulator, or one outside the versions the lowering was checked
against, SHALL report unsupported naming what is missing: an installed
emulator of another version SHALL be reported by its version, not as missing.
A run that the emulator cannot make on the host, such as from a temporary
directory whose path it cannot read, SHALL be reported unsupported naming the
reason before the emulator starts, never as a crashed run. A run that exceeds
its wall-clock limit SHALL be ended with its whole process group, its partial
events kept, and the run reported failed with the verification left unknown.

#### Scenario: A missing emulator reports unsupported

- **WHEN** an emulation question is verified and the emulator is not installed
- **THEN** the question is reported unsupported naming the emulator
- **AND** no result is fabricated

#### Scenario: An unchecked emulator version reports unsupported

- **WHEN** the installed emulator reports a version the lowering was not
  checked against
- **THEN** the question is reported unsupported naming that version and the
  versions the lowering was checked against

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
run the emulator where it is installed, and print each measure's value or the
reason it has none. With `--bundle-only` it SHALL write the bundle and run
nothing. It SHALL NOT change a workspace.

#### Scenario: A bundle is written without an emulator

- **WHEN** `fang emulate --bundle-only` runs on the demo board
- **THEN** it writes the plan, the platform description, the script, the probes
  and the manifest, and runs nothing

#### Scenario: Emulate prints what it measured

- **WHEN** `fang emulate` runs on the demo board with the emulator installed
- **THEN** it prints each question's measures and leaves any workspace
  untouched

### Requirement: Emulation Acceptance Tests

The suite SHALL hold one test per emulation acceptance criterion, AT-F1 and
AT-F2, each skipped by name where the emulator is absent.

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
