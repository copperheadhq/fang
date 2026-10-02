# fang-kernel Specification

## ADDED Requirements

### Requirement: Verification Questions Are Declared

A Fang program SHALL be able to declare a verification question beside the
requirement it serves: the parameters it measures into, the measures that
produce them, the method, and for a circuit question the bench. The question
SHALL elaborate to a verification entity whose result is unknown, carrying its
source location. A program SHALL NOT be able to declare a computed result for a
question; a result is produced only by a run. A parameter a question measures
into SHALL be declared without a value, and a program that gives it one, by a
default or an assignment, SHALL fail elaboration.

#### Scenario: A declared question becomes an unanswered verification

- **WHEN** a program declares a simulation question against a requirement
- **THEN** a verification entity exists naming that requirement, the method, the
  measured parameters, and the bench
- **AND** its result is unknown

#### Scenario: A question cannot state its own answer

- **WHEN** a program declares a question and supplies a result
- **THEN** the declaration is refused

#### Scenario: A measure names a declared parameter

- **WHEN** a question measures into a name that is not a declared parameter of
  the module declaring it
- **THEN** elaboration fails with a diagnostic naming the parameter

#### Scenario: A measured parameter is declared without a value

- **WHEN** a program gives a value to a parameter one of its questions measures
  into
- **THEN** elaboration fails with a diagnostic naming the parameter

#### Scenario: A verification by inspection is still declarable

- **WHEN** a program records a verification by inspection or test with its
  result
- **THEN** it elaborates as before, and is not routed to any tool

### Requirement: The Bench Is Explicit

A circuit question SHALL name every source and load applied and the analysis
window, each source and load at a part surface a pin map resolves. The runner
SHALL NOT supply a default source, load, or window. Every bench item SHALL be
recorded on the run as an assumption, and every part the bench abstracts SHALL
be recorded as a coverage gap.

#### Scenario: A question without a bench does not run

- **WHEN** a circuit question names no supply
- **THEN** the question is reported as not runnable, naming what is missing
- **AND** no source is assumed

#### Scenario: A bench item is recorded as an assumption

- **WHEN** a question applies a supply and a load and is prepared
- **THEN** the prepared run names each as an assumption with its surface and
  quantity

#### Scenario: An abstracted part is a coverage gap

- **WHEN** a bench abstracts a part
- **THEN** the prepared run names that part among its coverage gaps

#### Scenario: A surface no pin map resolves is refused

- **WHEN** a bench or a measure names a surface that resolves to no pins
- **THEN** preparation is refused naming the surface

#### Scenario: A load is a current or a resistance by its dimension

- **WHEN** one load is given in amperes and another in ohms
- **THEN** the first lowers to a current sink and the second to a resistor
- **AND** a load of any other dimension is refused

### Requirement: The Cheapest Verification Level Is Chosen And Recorded

The runner SHALL route a question to the cheapest level that can decide it. A
question every one of whose measured parameters holds a value, and whose
constraints the kernel's own evaluator already decides, SHALL be answered at the
equation level with no tool run. A measured parameter with no value SHALL NOT
let the evaluator answer. The chosen level and tool SHALL be recorded on the
verification entity. A question no registered tool covers SHALL be reported
unroutable rather than answered by a tool at another level.

#### Scenario: A question the evaluator decides runs no tool

- **WHEN** every parameter a question measures into holds a value and every
  constraint over them already evaluates to a decided status
- **THEN** the question is routed to the equation level
- **AND** no tool is prepared or run

#### Scenario: A measure nobody took is not decided by the evaluator

- **WHEN** a question measures into a parameter that holds no value and no
  constraint reads, while the constraints over its other parameters are decided
- **THEN** the question is routed to its tool rather than to the evaluator
- **AND** while nothing measures that parameter, the result is unknown, naming
  the missing measure

#### Scenario: An undecided circuit question routes to a circuit simulator

- **WHEN** a simulation question's constraint is undecided
- **THEN** it is routed to the circuit level and names the simulator

#### Scenario: The level is recorded with the answer

- **WHEN** a question is answered
- **THEN** the verification entity names the level and the tool that answered it

#### Scenario: A question nothing covers is unroutable

- **WHEN** a question names a method no registered tool covers
- **THEN** it is reported unroutable
- **AND** it is not answered by a tool at another level

### Requirement: Verification Tools Sit Behind One Protocol

Every verification tool SHALL say which questions it covers, whether it is
available, and its version; SHALL prepare its native input deterministically
from the snapshot and the question; SHALL run across a process boundary or read
a declared model file; and SHALL read its output into decimal measurements
containing nothing the output did not. A tool that is not installed SHALL report
unsupported by name and SHALL NOT be substituted. Every file a run reads beside
its native input SHALL be named in the run's bundle by a name that holds no
machine-specific path and that no other file of the run shares; the same file
read twice SHALL be one entry.

#### Scenario: Preparation is deterministic

- **WHEN** the same question is prepared twice over the same snapshot
- **THEN** the two native inputs are byte-identical

#### Scenario: A modelled part is instantiated from its model

- **WHEN** a part carrying a subcircuit model is in scope of a circuit question
- **THEN** the native input instantiates that subcircuit with the part's pins
  mapped onto the model's ports in the model's declared order
- **AND** the model is referenced rather than inlined

#### Scenario: Two model files at one relative path stay two files

- **WHEN** two parts declared in different folders name different model files
  by the same relative path
- **THEN** the run's bundle names each file apart, from its content
- **AND** each part is instantiated from its own file
- **AND** two different files declaring one subcircuit are refused, naming the
  parts, since a deck holds one definition of a subcircuit

#### Scenario: Pins on different nets landing on one model port are refused

- **WHEN** a part's pin map lands several pins on one model port and those
  pins are on different nets
- **THEN** the question is not runnable, naming the part, the port and the nets
- **AND** pins landing on one port that share a node are one terminal

#### Scenario: A measure lowers to a measurement directive

- **WHEN** a question asks for a peak-to-peak over a window at a surface
- **THEN** the native input carries a measurement over that window between the
  surface's node and its return

#### Scenario: Output is read into decimal measurements

- **WHEN** a tool's output reports a measured number
- **THEN** the measurement carries it as a decimal quantity in the measured
  parameter's unit, with the tool and its version

#### Scenario: A measure the output does not report is not invented

- **WHEN** a requested measure is absent from the tool's output or reported as
  failed
- **THEN** no measurement is produced for it
- **AND** the question's result is unknown, naming the missing measure

#### Scenario: A missing tool reports unsupported by name

- **WHEN** the tool a question routes to is not installed
- **THEN** the question is reported unsupported, naming the tool
- **AND** no other tool answers it and no result is fabricated

#### Scenario: A second simulator shares the lowering

- **WHEN** the same question is prepared for two SPICE-compatible simulators
- **THEN** the devices and bench are identical and only each simulator's own
  analysis and measurement conventions differ

### Requirement: Measurements Re-enter Through The Commit Gate

A measurement SHALL enter canonical state only as a transaction against the
committed head that sets each measured parameter to an inferred value whose
source is the run's evidence, adds that evidence carrying the structured
measurement record, and replaces the declared verification under its original
identity. A run already recorded for the same job and the same tool version
SHALL NOT be run again: its recorded measurements SHALL re-enter by the same
transaction, citing its evidence as it stands rather than adding it again, and
the result SHALL be what the gate decides on the head now. The constraint over a measured parameter SHALL be decided by the
gate's existing constraint check and by nothing else. A committed measurement
SHALL be kept across re-elaboration only while it is current: while preparing
its question afresh gives the job its evidence records.

#### Scenario: A measured parameter is an inferred value with its evidence

- **WHEN** a run's measurements are committed
- **THEN** each measured parameter holds an inferred value whose source is the
  evidence entity and whose confidence is the run's
- **AND** it is never recorded as an explicit value

#### Scenario: The undecided constraint is decided by the gate

- **WHEN** the measurement transaction is proposed
- **THEN** the constraint over the measured parameter is evaluated by the
  constraint check and reports a decided status

#### Scenario: The evidence carries the whole record

- **WHEN** a run's evidence is read
- **THEN** it names the tool and its version, the level, a hash of the native
  input, the run's terminal status, whether it ran locally or on a hosted
  runner, the run's confidence, each measure with its quantity or the reason it
  has none, the assumptions, and the coverage gaps
- **AND** it names the digest of every input file the run read that the
  snapshot does not hold, such as a model file

#### Scenario: The verification keeps its identity

- **WHEN** a question is answered
- **THEN** the verification entity has the identifier it was declared with, its
  result, the evidence, and a provenance record for the run

#### Scenario: A recorded run re-enters rather than running again

- **WHEN** a question is asked again with the same job on the same tool
  version as a completed run its verification already cites, after a change
  to the constraints over its measured parameters
- **THEN** no tool runs and no evidence is added
- **AND** the run's recorded measurements re-enter through the gate, and the
  verification's result is what the gate now decides, so a failure whose
  constraint was relaxed passes and a pass whose constraint became undecided is
  unknown
- **AND** the question is reported current only when the gate decides what the
  head already holds

#### Scenario: Measurements against a stale head are refused

- **WHEN** a run was prepared against a snapshot that is no longer the head
- **THEN** its measurements are refused rather than applied

#### Scenario: Re-elaboration does not withdraw a measured value

- **WHEN** a program whose measured parameter holds a committed measurement is
  elaborated again into the same workspace, unchanged
- **THEN** the parameter keeps the measured value and the evidence that is its
  source
- **AND** the program, which declared the parameter without a value, is not
  recorded as having changed it

#### Scenario: A measurement is kept only while it is current

- **WHEN** a program whose measured parameter holds a committed measurement is
  elaborated again with a change to anything the run rested on, such as a part
  in the circuit, a model file, or the firmware image, while the question
  itself is unchanged
- **THEN** preparing the question again gives a job other than the one the
  evidence records, and the measured value and the verification answered from
  it are not kept
- **AND** the question is answered again rather than reported current
- **AND** whether a measurement is kept does not depend on whether the tool is
  installed, or which version is

#### Scenario: Confidence is bounded by model provenance

- **WHEN** a run rests on a model whose provenance is assumed
- **THEN** the measurement's confidence is lower than that of a run over
  primitives and cited models

### Requirement: A Failing Measurement Is Recorded And Not Applied

WHEN the measurement transaction is rejected because a hard constraint over a
measured value failed, the head SHALL NOT move, the rejection SHALL be returned
with its diagnostics, and the runner SHALL record the evidence and the
verification with a failed result in a transaction that sets no parameter. A
rejection for any other reason SHALL record nothing.

#### Scenario: A value that breaks a hard constraint never reaches the head

- **WHEN** a measured value violates a hard constraint
- **THEN** the measured parameter is still unknown on the head
- **AND** the rejection names the constraint that failed

#### Scenario: The failure is recorded as knowledge

- **WHEN** a measured value violates a hard constraint
- **THEN** the head holds the run's evidence and the verification with a failed
  result naming that evidence

#### Scenario: An unrelated rejection records nothing

- **WHEN** the measurement transaction is rejected for a reason other than a
  failed constraint over a measured value
- **THEN** the head is unchanged and no evidence is added

#### Scenario: A run that measured nothing is recorded under a must-be-decided requirement

- **WHEN** a run produces no value for a measure, and the policy marks the
  requirement the question serves must-be-decided
- **THEN** the run's evidence is recorded and the verification reads unknown
- **AND** the constraints the run left undecided do not block that
  transaction, because the verification's own result states them

#### Scenario: Two questions measuring into one constraint are both answered

- **WHEN** a hard constraint reads parameters measured by two questions under a
  must-be-decided requirement
- **THEN** the first question's measurements enter although the constraint is
  still undecided for the other's parameter
- **AND** the second question's measurements decide it

### Requirement: Rule Checks Are Evidence

A rule-check question SHALL run the external checker over the artifact the
kernel lowers, SHALL record every violation the checker reports with its rule,
severity, and the items it names, and SHALL record each excluded rule with its
declared reason. A violation of error severity SHALL make the verification
fail; a warning SHALL NOT. A report of a schema the reader is not written for,
or one lacking a field the reader reads, SHALL fail the run with the reason and
leave the verification unknown; it SHALL NOT be read as a report of no
violations.

#### Scenario: A violation is recorded with its rule and items

- **WHEN** the checker reports a violation
- **THEN** the evidence names the rule, the severity, and the items

#### Scenario: An excluded rule is recorded with its reason

- **WHEN** a question excludes a rule with a reason
- **THEN** violations of that rule do not affect the result
- **AND** the evidence names the rule, the reason, and how many were excluded

#### Scenario: An exclusion without a reason is refused

- **WHEN** a question excludes a rule and gives no reason
- **THEN** the declaration is refused

#### Scenario: Errors fail and warnings do not

- **WHEN** the checker reports only warnings
- **THEN** the verification passes and the warnings are recorded
- **AND** one violation of error severity makes it fail

#### Scenario: A report the reader is not written for is not a pass

- **WHEN** the checker writes a report of another schema, or one without its
  sheets
- **THEN** the run fails with the reason and no verdict is drawn
- **AND** the verification stays unknown

### Requirement: A Touchstone Model Is Data

A part MAY carry a Touchstone model as a trait with its provenance. An RF
question over it SHALL be answered by reading the file and composing the named
matching parts in closed form, at the equation level, and the measurement's
confidence SHALL be bounded by the model's provenance. The named parts SHALL
form, in the order named, the ladder the graph connects from the port to the
model, each series part joining one node to the next and each shunt part
joining its node to ground, and a part that does not SHALL be refused by name.
A frequency outside the file's range SHALL be refused rather than
extrapolated, and the file's frequencies SHALL be scaled and compared exactly,
so that a frequency the file names is inside its range. A return loss is in
decibels, and SHALL be measured only into a parameter declared in decibels; a
decibel SHALL NOT convert to, or be compared or combined with, any other
dimensionless unit.

#### Scenario: A one-port file answers a return-loss question

- **WHEN** a question asks the return loss of a part carrying a one-port model
  at a frequency inside the file's range
- **THEN** the measurement is the return loss interpolated at that frequency, in
  decibels

#### Scenario: A matching network is composed from the graph's values

- **WHEN** the question names a series and a shunt part between the port and the
  model
- **THEN** the measurement accounts for both, using the values the graph holds

#### Scenario: Matching parts out of their ladder are refused

- **WHEN** the question names its matching parts in an order the graph does not
  connect them in, or names a part off the chain between the port and the model
- **THEN** the question is refused, naming the part that breaks the chain
- **AND** nothing is composed

#### Scenario: A matching part with an unknown value leaves the question unanswered

- **WHEN** a named matching part's value is unknown
- **THEN** no measurement is produced and the result is unknown, naming the part

#### Scenario: A frequency outside the file is refused

- **WHEN** the question's frequency lies outside the file's range
- **THEN** the question is refused naming the range
- **AND** nothing is extrapolated

#### Scenario: A frequency the file names is inside its range

- **WHEN** the question's frequency is the file's last point, written in the
  file's own frequency unit
- **THEN** the question is answered at that point and not refused

#### Scenario: A return loss goes only into a decibel parameter

- **WHEN** a question measures a return loss into a parameter declared in a
  dimensionless unit other than decibels, such as percent
- **THEN** elaboration fails with a unit diagnostic
- **AND** a constraint comparing a decibel parameter with such a unit is refused
  where it is written

#### Scenario: The file's format options are honoured

- **WHEN** two files describe the same network in different units, formats, and
  reference resistances
- **THEN** they give the same measurement

### Requirement: The Verify Command

The `verify` command SHALL route and run every declared question, print each
question's level, tool, measurements, and result or the reason it did not run,
exit non-zero when any verification failed, and persist measurements only when
asked to commit into an existing workspace. It SHALL persist measurements and
nothing else: where the program's design differs from the one persisted, the
commit SHALL be refused before anything runs, saying to run `build` first, and
nothing SHALL be written. A measurement made stale by a file the program reads
but does not hold, a model or a firmware image, is not a change to the design:
its question SHALL run again and its answer SHALL be committed. What it persists
SHALL first pass the commit gate whole, as what `build` persists does; a design
the gate rejects SHALL NOT be written, and the command SHALL report the gate's
diagnostics and exit non-zero.

#### Scenario: Verify reports each question

- **WHEN** `verify` runs against a program with declared questions
- **THEN** each question is printed with its level, its tool, its measurements,
  and its result

#### Scenario: A failed verification exits non-zero

- **WHEN** any question's verification fails
- **THEN** the command exits non-zero

#### Scenario: An unsupported question is reported and is not a failure

- **WHEN** a question's tool is not installed
- **THEN** the command names the tool as unsupported
- **AND** that alone does not make the exit non-zero

#### Scenario: Nothing persists without a commit

- **WHEN** `verify` runs without being asked to commit
- **THEN** the workspace is unchanged

#### Scenario: A program changed since its build is not committed

- **WHEN** `verify` is asked to commit, and the program has changed since its
  design was persisted, such as a part retuned or a constraint tightened
- **THEN** the command refuses, saying to run `build` first, and exits non-zero
- **AND** nothing runs and nothing is written to the workspace

#### Scenario: A measurement made stale outside the program is committed

- **WHEN** `verify` is asked to commit, the program is unchanged, and a model
  file a committed measurement rests on has changed
- **THEN** the question runs again
- **AND** its answer is committed

#### Scenario: A commit the gate rejects writes nothing

- **WHEN** `verify` is asked to commit a design the commit gate rejects
- **THEN** nothing is written to the workspace
- **AND** the command reports the gate's diagnostics and exits non-zero

#### Scenario: A program with no questions says so

- **WHEN** `verify` runs against a program declaring no question
- **THEN** the command says there is nothing to verify and exits zero

### Requirement: Verification Acceptance Test

A conforming implementation SHALL demonstrate the verification-layer acceptance
test.

#### Scenario: AT-V1 an undecided constraint is decided by a run that entered through the gate

- **WHEN** a program declares a parameter with no value, a hard constraint over
  it, and a circuit question measuring into it with an explicit bench, and
  verification runs with the simulator installed
- **THEN** the constraint that was undecided is decided on the committed head
- **AND** the parameter's value is inferred with the run's evidence as its
  source
- **AND** the verification names its level and tool, and the evidence names the
  tool's version
- **AND** with the constraint tightened past the measured value, the head does
  not move and the verification reads failed with its evidence
