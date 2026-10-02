# fang-kernel Specification

## Purpose

Fang is the Copperhead hardware kernel and the Python-embedded language that
authors hardware for it. The kernel elaborates a Fang program into the
Engineering Intermediate Representation (EIR), holds that representation as a
live typed graph, mutates it only through validated transactions, and lowers it
into downstream artifacts.

This document is the whole normative surface of the kernel for this repository
and stands alone: the EIR itself, and the kernel and language over it. It
covers stable identity, canonical semantic paths, quantities and units, value
status and unknowns, typed interfaces and their deterministic lowering to pins,
the single constraint registry and its expression language, topology intent,
transactions and the commit gate, deterministic serialization and semantic
diff, provenance, diagnostics, the tool plan, views, simulation, rationale, and
the conformance and acceptance criteria a conforming implementation must pass.

The governing invariant is that there is exactly one canonical model. The
kernel graph is a live realization of the EIR; every other representation is a
lowering of it, a projection of it, or an interchange encoding of it. An
implementation that introduces a second persisted representation of the same
facts is non-conformant.

RFC 2119 keywords in this document are normative.

## Terminology

- **Fang** — the Python-embedded language in which Copperhead hardware is
  authored, and the compiler that elaborates it.
- **Kernel** — the typed runtime that holds engineering state, enforces its
  invariants, and executes transactions against it. The kernel owns semantics;
  it owns no algorithm that needs a solver, an external process, or a CAD
  backend.
- **EIR** — the Engineering Intermediate Representation: the one canonical
  model of a Copperhead design, defined by this document.
- **Kernel graph** — the live realization of the EIR that a kernel holds. It is
  one model, not a model beside the EIR.
- **Elaboration** — executing a Fang program in a sandbox to produce a kernel
  graph and a tool plan. Elaboration builds; it never mutates geometry and
  never calls a tool.
- **Transaction** — the only unit of mutation. A proposal is normalized,
  validated, checked, and then committed or rejected whole.
- **Trait** — a capability attached to an entity, such as being simulatable or
  renderable, in place of a wider class.
- **Lowering** — the deterministic compilation of a kernel-level fact into a
  lower-level one, such as an interface connection into pin connections, or a
  graph snapshot into a physical board IR.
- **Realization** — a compiled downstream artifact that names the graph
  snapshot it came from and carries the provenance of the tools that produced
  it.
- **View** — a deterministic projection of kernel state that answers one
  engineering question.

## Design Principles

These principles are normative. Each requirement below is an application of one
or more of them; where a requirement is silent, the principle governs.

**One canonical model.** There SHALL be exactly one canonical representation of
a Copperhead design, and it is the EIR. Every other representation is either a
live realization of it (the kernel graph), a compiled projection of it (a
physical board IR, a schematic, a simulation graph, a view graph, a netlist),
or an interchange encoding of it. A projection MUST name the snapshot it was
compiled from, and MUST NOT be a place where engineering facts are first
recorded. The failure mode this exists to prevent is a permanent conversion
layer between two models that each partially own the truth.

**Python authors, the kernel decides.** Fang is an authoring and extension
language. Its output is a graph snapshot and a tool plan, both of which are
data. A Fang program SHALL NOT be the persisted design state, SHALL NOT be
required to re-execute in order to read a design, and SHALL NOT reach an engine
implementation directly.

**Interfaces before pins.** System-level authoring, and every agent operation
that has a system-level expression, SHALL operate on typed interfaces. Pin
assignment is a lowering result, recorded with its own provenance, not an
authoring input. This is what makes late pin assignment, compatibility
checking, and part substitution tractable.

**Deterministic elaboration.** Identical source, identical dependency lock, and
identical compiler version SHALL produce an identical graph snapshot and an
identical tool plan. Elaboration runs sandboxed, with no network access and
only declared file inputs readable. Any external input a program consumes MUST
be declared and hashed into the snapshot, or the build is not reproducible and
MUST NOT be treated as such. The prohibition is absolute rather than a default,
because a declared exception would cost exactly the guarantee it exists to
give: external data reaches a program as a declared, hashed file input produced
by an earlier tool call, and fetching it is an operation.

**Transactions before mutation.** Nothing mutates canonical state except a
committed transaction, and no transaction commits without passing the commit
gate. This holds identically for a human edit, a Fang re-elaboration, a CAD
import, and an agent proposal. An agent gets no privileged path and no weaker
gate.

**Compilers, not couplings.** No solver, simulator, layout engine, renderer, or
EDA implementation SHALL become inseparable from the kernel. Each is reached
through a compiler that lowers kernel state into that backend's native input,
and a normalizer that brings its output back. Backend assumptions MUST NOT be
distributed through component definitions.

**Extract before rebuild.** Before writing a new implementation of foundational
graph, module, interface, parameter, or constraint machinery, the implementing
engineer SHALL record in a decision record which existing project was evaluated
for the job and why it was not adopted, wrapped, or extracted. "Not invented
here" is a review comment, not a rationale. Copperhead SHALL NOT build: a
general graph algorithm library, a SPICE solver, an automatic graph-layout
algorithm, a schematic editor, a component database, or an adapter for every
EDA format.

## Layers of Representation

A conforming project SHOULD distinguish the following layers. They MAY be
stored separately, but they MUST share stable identifiers and provenance.

```text
Requirements IR
      v
Architecture IR
      v
Circuit / Connectivity IR
      v
Physical / PCB IR
      v
Manufacturing IR
      v
Outcome / Feedback IR
```

Derivation runs downward. The Physical IR describes board outline, stackup,
layers, components, pads, vias, traces, zones, regions, and dimensions; it is a
compiled realization of the layers above it and never a peer source of truth. A
generated physical representation MUST name the revision or snapshot it was
compiled from, and every physical entity MUST map to a stable identifier of the
upper layers where one exists. Producing a physical candidate MUST NOT mutate
semantic state as a side effect; where a physical result implies a semantic
change, such as a pin swap chosen during layout, that change returns through
the ordinary transaction path. An imported physical representation with no
upper-layer parent is the exception, and its semantic recovery is governed by
the import and provenance requirements below.

## Kernel Architecture

```text
Fang program        CAD import        agent proposal
     |                   |                  |
     v                   v                  v
 elaboration        import adapter     proposal branch
     |                   |                  |
     +-------------------+------------------+
                         |
                         v
                   kernel graph  (the EIR)
                         |
                  transaction gate
                         |
                    graph snapshot
                         |
     +-------------+-----+------+-------------+
     |             |            |             |
     v             v            v             v
 schematic     physical     simulation      view
 compiler      board IR      compiler      compiler
     |             |            |             |
     v             v            v             v
  netlist        layout       backends     SVG / UI
```

Every arrow leaving the snapshot is a lowering. Every arrow entering the kernel
graph is a transaction. There is no third kind of edge.

The subsystems are: the Fang compiler, which elaborates a program into a graph
and a tool plan; the kernel, holding the entity model, the invariants, the
transactions, and the commit gate; the interface compiler, which lowers typed
interface connections to pin connections and checks compatibility; the topology
engine, which represents and verifies physical intent that net equivalence
cannot express; the tool plan runtime, which validates a plan and executes its
calls; the view compiler, which projects graph state into view graphs, lays
them out, and renders them; the simulation compiler, which lowers a simulation
scope into a backend netlist and normalizes results; the CAD adapters, reached
behind one interface; and analysis utilities, which are graph queries over
typed entities.

The kernel graph holds EIR entities and nothing else, mapped onto the layers
above. Electrical entities — system, module, component, interface, port, pin,
net, rail, bus, domain, and parameter — belong to the architecture and circuit
layers. Constraints of every class, including topology intent and the layout
classes, belong to the one constraint model, and there SHALL be no second
constraint registry. Engineering knowledge entities — requirement, assumption,
decision, alternative, evidence, source reference, calculation, verification,
finding, and waiver — belong to the requirements, decision, and evidence
models. Physical entities — footprint, pad, board, layer, region, and the
placement and routing constraints — belong to the physical layer. Model
entities — simulation, behaviour, thermal, cost, supply, and reliability —
attach to components as traits and carry their own provenance. Identity SHALL
NOT be derived from visual coordinates.

## The Project Root

The logical root of an EIR project has the shape below. Every key MUST be
present in a machine-generated root, including one whose collection is empty,
so that a missing key identifies an artifact produced under an older schema
rather than an empty layer. There is exactly one `constraints` key.

```yaml
schema_version: 1.2
project_id: PRJ-...
revision_id: REV-...
requirements: []
architecture: []
interfaces: []
ports: []
buses: []
domains: []
components: []
models: []
nets: []
circuits: []
decisions: []
evidence: []
constraints: []
physical: {}
manufacturing: {}
outcomes: []
provenance: {}
```

This is the logical root, not a required file layout. Canonical persistence MAY
be that one document or a stream of typed entity records, provided the logical
root is reconstructible from the stream without loss and both forms serialize
canonically. The choice between them is not a schema change and MUST NOT alter
identity, ordering, or content.

## Requirements

### Requirement: Stable Entity Identity

Every first-class entity SHALL carry a stable identifier whose origin is
recorded as exactly one of `authored`, `derived`, or `imported`. Identity SHALL
NOT be derived from visual coordinates or from declaration order, and
references SHALL target identifiers rather than display names.

A derived identifier SHALL be a UUIDv5 computed from a project namespace and
the name `<entity-kind> ":" <canonical semantic path>`, where the project
namespace is UUIDv5 of the fixed EIR root namespace
`453c7e27-7e71-4d31-af3e-9da6714fc2ba` and the project identifier. The textual
form is the entity prefix, a hyphen, and the first twelve lowercase hexadecimal
digits of the UUID; the full UUID SHALL also be recorded.

#### Scenario: Derived identity is reproducible across machines and runs

- **WHEN** the same project state is elaborated on a different machine, in a
  different process, and in a different run
- **THEN** every derived identifier is byte-identical to the previous run
- **AND** no identifier depends on iteration order, memory address, wall-clock
  time, host name, or file system layout

#### Scenario: Short-form collision is lengthened deterministically

- **WHEN** a derived short form collides with an identifier already present in
  the revision
- **THEN** four further hexadecimal digits of the same UUID are appended, and
  the appending repeats until the form is unique
- **AND** re-deriving the same project state reproduces the same lengths,
  because the lengthening is a function of the revision's identifier set alone

#### Scenario: Two entities sharing a path are rejected

- **WHEN** a collision survives the whole UUID, meaning two entities share a
  canonical semantic path
- **THEN** the kernel rejects the state rather than resolving the collision

#### Scenario: Identifiers are unique across all three origins

- **WHEN** a revision contains authored, derived, and imported entities together
- **THEN** every identifier is unique within the revision across every origin
- **AND** a validator reports a duplicate as an error

#### Scenario: An external identifier never becomes canonical identity

- **WHEN** an entity is imported from an external file carrying its own identifier
- **THEN** the external identifier is recorded in an explicit mapping alongside
  the canonical identifier
- **AND** the external identifier is not used as the canonical identity

### Requirement: Canonical Semantic Paths

A canonical semantic path SHALL name an entity by its position in the
engineering structure rather than in a file, using the grammar
`path = segment *( "." segment )`, `segment = name [ "[" index "]" ]`,
`name = (ALPHA / DIGIT / "_") *( ALPHA / DIGIT / "_" )`, `index = 1*DIGIT`.
Names SHALL be ASCII, unique among the siblings of one parent, and a path SHALL
resolve to at most one entity within a revision. The grammar admits no escape
sequence.

#### Scenario: A name that the grammar cannot express is transliterated

- **WHEN** a name carries a period, a space, a slash, or any character outside
  `a-z`, `0-9`, and `_`
- **THEN** the name is normalized to Unicode normalization form KD, lowercased,
  every out-of-range character is replaced with `_`, each run of `_` is
  collapsed to a single `_`, and leading and trailing `_` are stripped
- **AND** an empty result becomes `x`
- **AND** a result colliding with a sibling's gets `_2`, `_3`, and so on,
  taking the colliding siblings in ascending order of their original names by
  Unicode code point, so that the first keeps the bare form
- **AND** the original is preserved as the entity's display name

#### Scenario: A name may begin with a digit

- **WHEN** a rail or net is named `3v3` or `12v_rail`
- **THEN** the path is valid and unambiguous, because an index is bracketed

### Requirement: Renames Preserve Identity Through Explicit Keys

Because a derived identifier follows the path, renaming a parent changes the
identity of everything beneath it. An entity MAY therefore carry an explicit
key, which replaces its name in the path used for derivation. Where identity is
preserved across a name change, a semantic diff SHALL report the change as a
rename and SHALL NOT report it as an addition together with a removal.

#### Scenario: A rename with an explicit key is reported as a rename

- **WHEN** an entity carrying an explicit key is renamed and identity is
  preserved across the name change
- **THEN** a semantic diff reports the change as a rename
- **AND** the diff does not report it as an addition together with a removal

### Requirement: Physical Quantities and Units

A physical quantity SHALL be a record and never a bare number. The `kind` field
takes one of `scalar`, `range`, or `tolerance`: a scalar carries `value`, a
range carries `min` and `max` and MAY carry `typical`, and a tolerance carries
`nominal` and a tolerance whose own kind is `relative` or `absolute`. A quantity
MAY carry the conditions under which it holds.

A magnitude SHALL serialize as a decimal string and SHALL NOT serialize as
binary floating point. A unit string is ASCII, built from SI symbols and from
the plain names of units whose symbol is not ASCII, combined with the operators
`*`, `/`, and `^`.

#### Scenario: Canonical form normalizes the symbol and not the magnitude

- **WHEN** a quantity is written with a metric prefix, such as `3.3 V`
- **THEN** the canonical form remains `3.3 V` rather than becoming `3300 mV`

#### Scenario: Dimensions are compared as exponent vectors

- **WHEN** two quantities are compared
- **THEN** they are comparable only where their dimension vectors are equal,
  over the seven SI base dimensions in the fixed order length, mass, time,
  current, temperature, amount of substance, and luminous intensity
- **AND** a dimensionless quantity is the zero vector

#### Scenario: Conversion records its rounding

- **WHEN** a quantity is converted between comparable units
- **THEN** the conversion is exact where the conversion factor is exact
- **AND** the conversion records its rounding where the factor is not exact

#### Scenario: Arithmetic across incompatible units fails at elaboration

- **WHEN** a Fang program adds quantities of unequal dimension
- **THEN** elaboration fails with a `UNIT` diagnostic
- **AND** the failure is not deferred to evaluation as a runtime surprise

### Requirement: Value Status and Explicit Unknowns

Every parameter of an entity SHALL be a value record rather than a bare
quantity, so that how well a value is known travels with the value. The
`status` field takes exactly one of `explicit`, `inferred`, `assumed`, or
`unknown`.

An `inferred` value SHALL carry its source and a confidence. An `assumed` value
SHALL carry its rationale and is an assumption that SHALL be promoted only
through approval or evidence. An `unknown` value SHALL omit the quantity field.

#### Scenario: Null never means unknown

- **WHEN** a value is not known
- **THEN** it is present with status `unknown`, and a null is not used to
  express it
- **AND** a value that does not apply is absent instead, so that a null never
  ambiguously means both "unknown" and "not applicable"

#### Scenario: An inferred value is not treated as explicit

- **WHEN** a consumer reads a value whose status is `inferred` or `assumed`
- **THEN** the consumer does not treat it as an `explicit` value

#### Scenario: Evaluation over an unknown yields undecided

- **WHEN** an expression is evaluated over a value whose status is `unknown`
- **THEN** the result is undecided rather than a pass or a failure

### Requirement: Conflicting Values Are Preserved Until Resolved

Conflicting evidence SHALL remain preservable until resolved. A value with
competing candidates is represented as the candidates and their sources
together.

#### Scenario: Competing candidates are not silently reduced

- **WHEN** two sources supply different values for the same parameter
- **THEN** both candidates and their sources are retained
- **AND** the value is not silently reduced to one winner

#### Scenario: Resolution is recorded as a decision

- **WHEN** a conflict is resolved
- **THEN** the resolution records which candidate was chosen and why, as a
  design decision entity

### Requirement: Typed Connections

Connections between entities SHALL be typed. The minimum set of connection
kinds is `electrical`, `power`, `signal`, `ground`, `mechanical`, `control`,
`dependency`, and `containment`. An untyped connection SHALL NOT be
representable.

An electrical connection SHOULD carry the signal semantics that are known:
direction, voltage domain, current range, impedance, protocol, bandwidth,
timing class, differential pairing, pull configuration, and protection state.
Each is a value record and is therefore unknown-representable rather than
defaulted.

#### Scenario: An untyped connection is rejected

- **WHEN** a program or an import attempts to create a connection with no kind
- **THEN** the kernel rejects it, because the type is not optional

#### Scenario: Unknown signal semantics are unknown, not defaulted

- **WHEN** an electrical connection's impedance is not known
- **THEN** the impedance is recorded with status `unknown`
- **AND** it is not filled in with a default value

### Requirement: Typed Interfaces, Ports, Buses, and Domains

An interface SHALL be a first-class entity representing a typed connection
surface: a named group of signals with roles, electrical parameters, a
direction where one applies, and compatibility rules. A port is an interface
instance owned by a component, module, or architecture block. A bus is an
interface whose participants are many rather than two. A domain groups entities
sharing a voltage, ground, isolation, or timing reference.

The kernel SHALL ship a catalogue of typed interfaces and SHALL allow projects
to define their own. The catalogue SHALL cover at least I2C, SPI, UART, USB 2,
CAN, RS-485, PWM, quadrature encoder, power input, power output, analog input,
analog output, motor phase, JTAG, serial wire debug, clock, and reset.

#### Scenario: System-level connectivity is recorded between interfaces

- **WHEN** an architecture-level or system-level connection is authored
- **THEN** it is recorded between interfaces rather than between pins

#### Scenario: Same-type interfaces are not automatically compatible

- **WHEN** two interfaces of the same catalogue type are connected
- **THEN** compatibility is decided by the compatibility checks, not by the
  type match alone

### Requirement: Deterministic Interface Lowering to Pins

An interface connection SHALL lower to pin connections deterministically for a
given graph state and part selection. The lowering SHALL be recorded as
first-class connectivity carrying provenance that names the interface
connection it was derived from, and SHALL be re-derivable from the same graph
state and part selection.

#### Scenario: A pin-assignment choice is recorded as a decision

- **WHEN** a part offers alternative pin assignments and the lowering selects one
- **THEN** the choice is recorded as a design decision entity with its rationale
- **AND** it is not left as an implicit result

#### Scenario: An incomplete lowering fails explicitly

- **WHEN** a required signal has no pin, two interfaces disagree on membership,
  or a constraint forbids every remaining assignment
- **THEN** the lowering fails with an `IFACE` diagnostic naming the
  unsatisfiable signal
- **AND** no partial pin mapping is produced or recorded

### Requirement: Interface Compatibility Checks

Interface compatibility SHALL be a deterministic check class. The kernel SHALL
evaluate at least: source VOH(min) against sink VIH(min) plus margin; source
VOL(max) against sink VIL(max) less margin; source current capability against
sink demand; bus voltage domain compatibility across all participants; pull-up
supply validity for every participant; open-drain and open-collector
requirements; and protocol, rate, and addressing compatibility.

#### Scenario: A check with unknown inputs returns undecided

- **WHEN** an input to a compatibility check has value status `unknown`
- **THEN** the check returns an undecided result naming the missing input
- **AND** the check does not pass by default

#### Scenario: A datasheet-sourced check cites its evidence

- **WHEN** a compatibility check reads an input that came from a datasheet
- **THEN** the check cites the evidence entity supporting it, so that the
  result is reproducible when the datasheet claim is revised

### Requirement: Exactly One Constraint Registry

There SHALL be exactly one constraint registry for a project. Electrical,
physics, topology, placement, routing, manufacturing, sourcing, and testability
constraints are classes within it. A second constraint store SHALL NOT exist.

#### Scenario: An emitted constraint file is a projection

- **WHEN** a constraint file is emitted for review or for backend compatibility
- **THEN** it is a generated projection of the registry
- **AND** it is not a peer copy that engineering facts can be recorded into

#### Scenario: A projection carries the identity of what it projects

- **WHEN** a downstream representation of a constraint is produced for a layout
  tool, a language surface, or an exported rule file
- **THEN** it carries the identifier of the record it projects
- **AND** it does not restate a field the constraint record already defines
- **AND** it MAY add class-specific fields

### Requirement: The Constraint Record

A constraint SHALL be one entity kind with one schema whatever class it belongs
to, and SHALL carry `id`, `class`, `kind`, `targets`, `expression`, and
`enforcement`. The `class` field takes one of `electrical`, `physics`,
`topology`, `placement`, `routing`, `manufacturing`, `sourcing`, or
`testability`. The `enforcement` field takes one of `hard`, `soft`, or
`advisory`, and states how a violation is treated rather than how bad it is.
The `verification.method` field takes one of `analysis`, `simulation`,
`rule check`, `inspection`, or `test`.

#### Scenario: A non-applicable constraint is reported as not applicable

- **WHEN** a constraint carries an applicability expression that evaluates false
- **THEN** the constraint is reported as not applicable
- **AND** it is not reported as passing

### Requirement: Typed Constraint Expressions

A constraint's expression SHALL be a typed expression tree serialized
canonically. The node kinds are `literal` (a quantity, number, string, or
boolean), `ref` (an entity identifier and an attribute path), arithmetic
(`add`, `sub`, `mul`, `div`, `pow`, `neg`, `abs`, `min`, `max`), comparison
(`lt`, `le`, `eq`, `ne`, `ge`, `gt`), and logical (`and`, `or`, `not`). An
implementation MAY add node kinds under the extension mechanism but SHALL NOT
redefine these.

Every node has a dimension. Multiplication adds dimension vectors and division
subtracts them; an exponent SHALL be a dimensionless integer or rational;
addition, subtraction, and comparison require operands of equal dimension; a
function that is not dimensionally closed requires dimensionless operands.

#### Scenario: A dimension mismatch is rejected where it is written

- **WHEN** an expression compares a quantity in volts against one in amperes
- **THEN** the expression is rejected as an error at the point it is written
- **AND** the mismatch is not reported as a warning, and is not carried into
  evaluation

#### Scenario: Comparison has interval semantics

- **WHEN** operands carry a range or a tolerance
- **THEN** a comparison is true when it holds across the whole operand interval,
  false when it fails across the whole interval, and undecided when it holds
  across only part of it

#### Scenario: Undecided propagates by three-valued logic

- **WHEN** a logical operator combines operands of which at least one is undecided
- **THEN** `and` is false if any operand is false and undecided if none is false
  and any is undecided
- **AND** `or` is true if any operand is true and undecided if none is true and
  any is undecided
- **AND** `not` maps undecided to undecided

#### Scenario: Undecided is neither a pass nor a failure

- **WHEN** a constraint evaluation returns undecided
- **THEN** it is reported as undecided, surfacing as the `UNKNOWN` check result
  state
- **AND** it is not reported as a pass, and is not silently converted into a
  failure
- **AND** whether an undecided result blocks is settled by the gate that
  consumes the result, not by the evaluator

### Requirement: Topology Intent Separate From Electrical Equivalence

A netlist collapses every electrically equivalent point into one net, which is
correct as connectivity and insufficient as engineering intent. The kernel
SHALL represent topology intent separately from electrical equivalence, as a
constraint within the one constraint registry, naming the net or domain it
governs, the topology mode, the centre or bonding point where one applies, the
permitted branches, and whether parallel conductive paths are forbidden.

Domains and bonding points are entities in their own right and SHALL be
referenced by identity.

#### Scenario: A single-point ground is expressible

- **WHEN** a design requires a single-point ground, a defined return path, a
  specific bonding point between two ground domains, or a Kelvin connection
- **THEN** the requirement is recorded as a topology constraint
- **AND** it is not approximated by net membership

### Requirement: Topology Verification Enumerates Conductive Paths

Topology verification SHALL be a deterministic check class evaluated over the
connectivity graph. It SHALL enumerate the conductive paths between the domains
a constraint names, compare them against the permitted set, and report each
unpermitted path with the elements that form it.

#### Scenario: A finding names the paths rather than counting them

- **WHEN** two conductive paths exist where one permitted bond was expected
- **THEN** the finding names each unpermitted path and the elements that form it
- **AND** reporting a count alone is insufficient

#### Scenario: A conditional path carries its condition

- **WHEN** a path's existence depends on a component whose conduction is
  conditional, such as a protection diode or a test jumper
- **THEN** the condition is part of the finding

### Requirement: Transactions Are The Only Unit Of Mutation

Nothing SHALL mutate canonical state except a committed transaction. A
transaction SHALL be atomic: it commits whole or it does not commit. It SHALL
name the snapshot it was proposed against.

Structured operations SHALL be preferred over free-form edits wherever one
exists, and an operation SHALL carry its reason and the requirements it serves
where they are known.

#### Scenario: A stale transaction is rebased or rejected

- **WHEN** a transaction is proposed against a snapshot that is no longer current
- **THEN** it is rebased and re-verified, or rejected
- **AND** it is not applied on the assumption that the intervening change was
  unrelated

#### Scenario: A representable operation is not expressed as a file edit

- **WHEN** an effect is representable as a kernel operation such as `connect` or
  `set_parameter`
- **THEN** it is expressed as that operation
- **AND** it is not expressed as a file edit instead

#### Scenario: Every mutation path uses the same gate

- **WHEN** the mutation originates from a program, a human edit through a tool,
  a re-elaboration, or a CAD import
- **THEN** all of them pass the same validation and the same gate
- **AND** they differ in their origin provenance and in nothing else
- **AND** an agent proposal receives no privileged path and no weaker gate

### Requirement: Proposal Sandbox

A proposal SHALL be elaborated or applied onto a candidate branch of the graph,
never onto canonical state. The branch is normalized, structurally validated,
checked, simulated where required, and diffed, and is then committed or
rejected. The branch is discarded on rejection.

#### Scenario: A rejected proposal leaves canonical state untouched

- **WHEN** a proposal is rejected
- **THEN** canonical state is unchanged
- **AND** the proposal still produces its diagnostics and its diff, because the
  explanation is the useful output of a rejection

### Requirement: The Commit Gate

A transaction SHALL commit only when all of the following hold: it normalizes
into well-formed entities; the resulting graph passes structural validation
including identifier uniqueness and referential integrity; every check class the
active policy marks required for the affected scope has run; no required check
reports a blocking severity; no undecided result covers a requirement the policy
marks as must-be-decided; and the policy's approval requirements, where any
apply, are satisfied.

Absent a project policy, the required set SHALL be structural validation
together with every check class whose scope intersects the transaction's
affected entities, the scope being taken over the head the transaction is based
on as well as over the candidate, so that a removal still requires the check
whose scope held what it removed. A policy narrows or widens that set but never
removes the structural check.

An undecided result SHALL NOT count against a must-be-decided requirement when
every operand that leaves it undecided is a parameter a declared verification
question measures into and that holds no value: the verification's own result
states that constraint, whether the question is unanswered, failed, or answered
without a value (copperhead RFC 12 version 1.3, Sections 9.3 and 12.9). An
undecided result over any other unknown operand still blocks.

#### Scenario: Downstream artifacts are materialized only after commit

- **WHEN** a transaction has not yet committed
- **THEN** no change is materialized into a CAD file or any other downstream
  artifact
- **AND** external checks such as CAD rule checking have not been run

#### Scenario: External rule-check results are ingested as evidence after commit

- **WHEN** a transaction commits and an external rule check subsequently runs
- **THEN** its results are ingested as evidence
- **AND** they were not consulted before the gate

#### Scenario: A removal brings in the check that covered what it removed

- **WHEN** a transaction removes an entity that only the head's scope of a check
  class held, such as the connection tying an address strap pin
- **THEN** that check class is required and runs
- **AND** a result it reports blocks the transaction as any other would

#### Scenario: A question awaiting its answer does not block a must-be-decided requirement

- **WHEN** a program declares a verification question whose measured parameters
  hold no value, under a requirement the policy marks must-be-decided
- **THEN** the program commits, with the constraints over those parameters
  reported undecided

#### Scenario: A recorded failure is not blocked by what it leaves undecided

- **WHEN** a measurement fails a hard constraint and the failed verification is
  recorded by a transaction that sets no parameter
- **THEN** that transaction commits under a must-be-decided requirement

#### Scenario: Another unknown operand still blocks

- **WHEN** a constraint is undecided because of a parameter no declared question
  measures into, under a requirement the policy marks must-be-decided
- **THEN** the transaction is rejected with the undecided-blocked code, naming
  that constraint

### Requirement: Semantic Diff Classification

The kernel SHALL support semantic change detection, and a diff SHALL classify
each change. The classification SHALL distinguish at least: component added,
removed, or changed; connection added or removed; parameter or value changed;
interface changed; pin assignment changed; domain changed; topology intent
changed; model or trait changed; requirement changed; decision changed;
evidence changed; verification status changed; constraint changed; placement,
routing, or other physical change; and rename.

#### Scenario: Presentation change is separable from electrical change

- **WHEN** a change alters only coordinates or presentation
- **THEN** the diff separates it from a change that alters electrical meaning

#### Scenario: A diff carries the impact of a change

- **WHEN** a parameter changes
- **THEN** the diff SHOULD name the calculations, requirements, and
  verifications the change invalidates

### Requirement: Deterministic Canonical Serialization

Machine-generated kernel state SHALL serialize canonically: reserializing an
unchanged state SHALL produce byte-identical output, on any machine and in any
process. JSON is the canonical interchange encoding.

Canonical serialization is UTF-8 with no byte order mark, LF line endings, and
one trailing newline; strings in Unicode normalization form C with no trailing
whitespace; mapping keys sorted ascending by Unicode code point; unordered
collections sorted ascending by entity identifier; physical quantities as
decimal strings and never as binary floating point; a bare number as the
shortest decimal that round-trips to the same value; and timestamps as RFC3339
in UTC with a trailing `Z`.

A collection whose order carries meaning, such as a power-up sequence, a
rationale list, or a provenance list, SHALL preserve its order, and the schema
SHALL state which collections those are.

#### Scenario: No environment-derived value is emitted

- **WHEN** state is serialized
- **THEN** the output contains no wall-clock time, host name, absolute path,
  process identifier, or ordering derived from memory address or hash iteration
  order
- **AND** the exception is a value that is itself recorded engineering data,
  such as the `created_at` field of a provenance record

#### Scenario: The record stream has a fixed canonical form

- **WHEN** state is persisted as a stream of typed entity records
- **THEN** each record is one canonically serialized object on one line
- **AND** records are ordered ascending by entity identifier
- **AND** the stream carries no framing that varies between runs

#### Scenario: Persistence form is not a schema change

- **WHEN** persistence moves between the single logical document and the record
  stream
- **THEN** the logical root is reconstructible from either without loss
- **AND** the choice alters no identity, no ordering, and no content

### Requirement: Schema Versioning and Compatibility

Every machine-readable artifact SHALL carry a `schema_version`. Breaking schema
changes require a major version increment; additive changes, such as a new
optional key or a new entity collection, increment the minor version. The
schema version names the data schema and not the specification document; the
two version lines SHALL NOT be conflated.

The data schema this specification defines is version 1.2, and a
machine-generated root SHALL carry it as `schema_version: 1.2` in the shape
The Project Root gives. Version 1.2 adds, to version 1.1, a port's optional
peripheral instance and address strap and a connection's optional selectors.

The kernel SHALL record, with every snapshot, the schema version, the compiler
version, the dependency lock identity, and the identifiers of any extracted
upstream code in use.

#### Scenario: An unimplemented major version is rejected

- **WHEN** a reader encounters an artifact whose major schema version it does
  not implement
- **THEN** the reader rejects the artifact
- **AND** it does not silently downgrade it

#### Scenario: Unknown fields are preserved

- **WHEN** a reader encounters fields it does not know
- **THEN** it SHOULD preserve them, so that newer producers interoperate with
  older tooling without destructive rewriting

#### Scenario: A snapshot carries the schema version this specification defines

- **WHEN** the kernel serializes a snapshot's logical root
- **THEN** its `schema_version` is 1.2
- **AND** a port or connection that holds none of the keys version 1.2 added
  serializes exactly as it did under version 1.1

### Requirement: Structural Validation

A validator SHALL check identifier uniqueness, referential integrity, type and
unit correctness, schema compatibility, invalid state transitions, cycles where
prohibited, and contradictory mandatory constraints.

#### Scenario: A dangling required reference is rejected

- **WHEN** a required reference names an identifier that does not exist in the
  revision
- **THEN** validation fails and the transaction does not commit

#### Scenario: Every root key is present in machine-generated state

- **WHEN** a project root is generated by a machine
- **THEN** every defined key is present, including one whose collection is empty
- **AND** a missing key therefore identifies an artifact produced under an older
  schema rather than an empty layer

### Requirement: Provenance On Every Derived Or Imported Entity

Every entity whose identity origin is `derived` or `imported` SHALL carry
provenance; an authored entity SHOULD carry provenance. A provenance record
SHALL carry `origin`, `activity`, `actor`, `revision_id`, and `created_at`;
SHALL carry `derived_from` where a parent entity exists; and SHALL carry
`source_location` naming the file and line, where the entity was produced by a
program.

The `origin` field takes one of `generated`, `authored`, `imported`, or
`inferred`. The `actor.kind` field takes one of `tool`, `model`, `human`, or
`adapter`. The `confidence` field takes one of `asserted`, `inferred`, or
`unverified`, and SHALL be present when the origin is `inferred`.

#### Scenario: Provenance is append-only

- **WHEN** a later transformation acts on an entity
- **THEN** it appends a provenance record
- **AND** it does not rewrite or remove an existing one
- **AND** the list remains ordered oldest first

#### Scenario: An untraceable entity is a defect

- **WHEN** an entity is traceable to neither a source location nor an import
- **THEN** the kernel treats it as a defect

### Requirement: Requirement State Transitions

Requirement states SHALL include `KNOWN`, `ASSUMED`, `DERIVED`, `MISSING`,
`CONFLICTING`, `WAIVED`, and `VERIFIED`, and a requirement's state SHALL change
only along the permitted transitions: from `MISSING` to `KNOWN`, `ASSUMED`,
`DERIVED`, or `WAIVED`; from `ASSUMED` to `KNOWN`, `DERIVED`, `CONFLICTING`, or
`WAIVED`; from `DERIVED` to `KNOWN`, `CONFLICTING`, `WAIVED`, or `VERIFIED`;
from `KNOWN` to `DERIVED`, `CONFLICTING`, `WAIVED`, or `VERIFIED`; from
`CONFLICTING` to `KNOWN`, `ASSUMED`, `DERIVED`, or `WAIVED`; from `WAIVED` to
`KNOWN`, `ASSUMED`, or `DERIVED`; and from `VERIFIED` to `KNOWN`,
`CONFLICTING`, or `WAIVED`.

#### Scenario: A transition outside the table is rejected

- **WHEN** a transition is attempted that the table does not permit, such as
  `MISSING` to `VERIFIED` or any transition entering `MISSING`
- **THEN** the validator rejects it

#### Scenario: Every transition records actor, reason, and provenance

- **WHEN** a requirement changes state
- **THEN** the transition records its actor, its reason, and its provenance
- **AND** a transition to `VERIFIED` cites verification evidence
- **AND** a transition to `WAIVED` cites a waiver
- **AND** a transition out of `ASSUMED` to `KNOWN` cites the approval or
  evidence that promoted it

### Requirement: Fang Is Ordinary Python

A Fang program SHALL be an ordinary Python module, usable with ordinary
packaging, functions, imports, and static type checking. Beyond that, Fang SHALL
provide declarative construction with no geometry mutation and no tool call
during elaboration; explicit units on every physical quantity with dimensional
validation at elaboration time; stable identity derived from module path, object
identity, and explicit keys; reusable modules optionally carrying proven layout
templates; typed interfaces as the primary connection surface; traits as the
extension mechanism; and source locations preserved on every entity and every
diagnostic.

#### Scenario: A running Python object graph is not persisted state

- **WHEN** a design is read back
- **THEN** the persisted engineering state is the serialized kernel graph
- **AND** the program is not required to re-execute in order to read the design
- **AND** the Python object graph is not the persisted state

#### Scenario: A program never reaches an engine directly

- **WHEN** a program requests layout, checking, export, or simulation
- **THEN** the request is recorded in the tool plan
- **AND** the program does not reach an engine implementation directly

### Requirement: Deterministic Sandboxed Elaboration

Elaboration SHALL execute the program and return exactly two artifacts: a graph
snapshot and a tool plan. Identical source, identical dependency lock, and
identical compiler version SHALL produce an identical graph snapshot and an
identical tool plan.

Elaboration SHALL run in a sandbox with no network access and only declared file
inputs readable. The prohibition on network access is absolute rather than a
default. Any external input a program consumes SHALL be declared and hashed into
the snapshot.

#### Scenario: The three phases are not interleaved

- **WHEN** a program is elaborated
- **THEN** elaboration builds a graph, operation executes the recorded plan
  against immutable snapshots producing candidate realizations, and commit
  verifies a candidate and attaches it or rejects it without mutation
- **AND** elaboration has no access to tool results, because a program that
  could observe an operation's result would not be reproducible

#### Scenario: Run-to-run variation is excluded

- **WHEN** a program is elaborated twice from unchanged inputs
- **THEN** the result is free of ordering dependence on dictionary iteration,
  wall-clock time, and process identity
- **AND** where the program needs randomness, the seed is declared and recorded

#### Scenario: External data arrives as a declared hashed file

- **WHEN** a program needs data from outside the workspace
- **THEN** the data reaches it as a declared, hashed file input produced by an
  earlier tool call
- **AND** fetching it is an operation belonging to the phase after elaboration

### Requirement: Modules and Systems

A module SHALL be a reusable unit that owns interfaces, parameters,
constraints, and child modules. A system is the root module of a design. Modules
declare what they expose and what they require, and composition is connection
between interfaces rather than between pins.

#### Scenario: A module declares constraints over its own parameters

- **WHEN** a module declares `require(self.vm.voltage <= 60 * V)`
- **THEN** the constraint is recorded declaratively against the module's
  parameters
- **AND** it is not evaluated eagerly at declaration time

### Requirement: Traits As The Extension Mechanism

Behaviour SHALL attach to entities through traits rather than through
progressively wider classes. A trait SHALL declare the protocol it satisfies,
and the kernel SHALL be able to enumerate the entities carrying a given trait
without instantiating any backend.

#### Scenario: Traits supplying models carry their own provenance

- **WHEN** a trait supplies a simulation, behaviour, thermal, cost, supply, or
  reliability model
- **THEN** the trait carries its own provenance, because a model's applicability
  is an engineering claim rather than a fact about the component

#### Scenario: A model result is not evidence beyond its declared conditions

- **WHEN** a consumer reads a model result
- **THEN** it does not treat the result as evidence beyond the conditions the
  model declares

### Requirement: Namespaced Diagnostic Codes

An elaboration diagnostic SHALL carry a stable code, a severity, the entities it
concerns, the source location, and a message. A code has the form
`<AREA>-<NNNN>`, where AREA is one of `ELAB`, `IFACE`, `TOPO`, `UNIT`, `TXN`,
`SIM`, or `IMPORT`, and NNNN is a four-digit number allocated within that area.
An implementation MAY add an area under a vendor namespace but SHALL NOT
allocate within these.

#### Scenario: A code is never reused or renumbered

- **WHEN** a diagnostic is no longer emitted
- **THEN** it is marked retired and its code stays allocated
- **AND** the code is not reused for a different condition and is not renumbered

#### Scenario: A failed elaboration produces no partial graph

- **WHEN** elaboration fails
- **THEN** it produces diagnostics and no partial graph
- **AND** a partially elaborated graph is not committed

### Requirement: Tool Plan Emission

Operations a program requests SHALL be recorded rather than performed.
Elaboration SHALL emit a tool plan naming the graph snapshot it applies to, the
ordered calls, and the source map back to the program. The plan is data and MAY
be inspected, diffed, stored, and replayed without re-executing the program.

Every call in a plan SHALL name a versioned Copperhead tool and SHALL be
executed by the agent runtime under its permission classes, workspace isolation,
event stream, and terminal statuses. A tool call SHALL be idempotent for the
same graph snapshot, content-addressed inputs, configuration, and seed.

#### Scenario: A tool call returns a handle, not a result

- **WHEN** a program calls a tool during elaboration
- **THEN** the call returns a handle naming a result the operation phase will
  produce
- **AND** the handle's attributes are symbolic conditions recorded in the plan
  and resolved when that phase runs

#### Scenario: Reading a handle during elaboration is an error

- **WHEN** a program converts a handle to a boolean, branches on it, or compares
  it to a value during elaboration
- **THEN** elaboration fails with a diagnostic

#### Scenario: An unsupported operation returns unsupported

- **WHEN** a plan requests an operation no tool supports
- **THEN** the runtime returns the unsupported status
- **AND** it does not make a degraded attempt

### Requirement: Realizations Do Not Mutate Semantic State

A tool that produces a downstream artifact SHALL produce a realization: a
compiled projection naming its parent graph snapshot, the compile configuration,
the tools and engines that produced it, and its verification state. A
realization is a candidate until verified.

#### Scenario: A layout-chosen pin swap returns through a transaction

- **WHEN** a compiled result implies a semantic change, such as a pin swap
  chosen during layout
- **THEN** the change returns through a transaction and its gate
- **AND** the realization does not mutate semantic state as a side effect

#### Scenario: A projection names the snapshot it came from

- **WHEN** a physical board representation, a schematic, a simulation graph, a
  view graph, or a netlist is produced
- **THEN** it names the snapshot it was compiled from
- **AND** it is not a place where engineering facts are first recorded

### Requirement: Views Are Deterministic Projections

A view SHALL be a deterministic projection of graph state that answers one
engineering question, generated only from facts in the graph. A conformant
implementation SHALL provide at least the system, interconnect, power, ground,
interfaces, and safety views.

Input to the layout kernel SHALL contain only layout information: node identity,
node dimensions, ports, edges, hierarchy, and layout hints. It SHALL NOT contain
engineering meaning, and no engineering decision SHALL depend on layout output.

#### Scenario: A view contains no fact absent from the snapshot

- **WHEN** a view is generated
- **THEN** it contains no connection, component, or annotation that does not
  exist in the snapshot it names

#### Scenario: Repeated generation is reproducible

- **WHEN** a view is generated twice from unchanged graph state
- **THEN** the view graph is identical
- **AND** the geometry SHOULD be identical

#### Scenario: Placement seeds are presentation state

- **WHEN** a view stores placement seeds to keep relative placement stable
  across projections
- **THEN** the seeds are stored separately from canonical identity
- **AND** a change to a seed classifies as a presentation change

### Requirement: Simulation Is A Compiler Target

Components SHALL NOT implement numerical simulation. A component exposes models;
the kernel compiles a selected scope into a simulator's native input and
normalizes what comes back. Backend assumptions SHALL NOT appear in component
definitions, and the kernel SHALL NOT bind to a simulator wrapper in place of
emitting that simulator's native input.

A simulation request SHALL lower to an explicit plan before any simulator runs.
Plan compilation SHALL validate that every selected component has a compatible
model, that pin maps are complete, that unsupported components are explicitly
abstracted, that model distribution constraints are respected, and that
simulator options are deterministic and recorded.

#### Scenario: An unsatisfiable plan is rejected rather than substituted

- **WHEN** a selected component has no compatible model
- **THEN** the plan is rejected with the reason
- **AND** it is not run with a substitute

#### Scenario: A result records its full context

- **WHEN** a simulation run completes
- **THEN** the normalized result records the plan, the backend and its version,
  the models used and their provenance, the assumptions applied, and the
  coverage the run does not provide
- **AND** sample data is referenced as an artifact rather than inlined

#### Scenario: A simulation pass is not proof of physical correctness

- **WHEN** a simulation passes
- **THEN** it is recorded as a finding with the confidence its model provenance
  and coverage support
- **AND** it is not recorded as proof of physical correctness

### Requirement: External Adapters Report Loss

Adapters SHALL connect the kernel to external formats and tools, and the kernel
SHALL NOT know which adapter is active. Adapters SHALL report unsupported
constructs and SHALL NOT silently discard semantics.

#### Scenario: An import represents what it could not recover

- **WHEN** an import cannot recover a semantic fact
- **THEN** it represents the absence as unknown, inferred, or unverified
- **AND** it does not fabricate intent
- **AND** an inference carries its confidence and is never asserted as a fact

#### Scenario: A lossy import records the unrecoverable fields

- **WHEN** an import is lossy
- **THEN** it records which fields were not recoverable

### Requirement: Workspace Persistence

A project's kernel state SHALL persist beside its sources, separating canonical
state and recorded evidence from derived cache. Everything outside the cache
directory is either canonical state or recorded evidence.

#### Scenario: Deleting the cache loses no engineering fact

- **WHEN** the cache directory is deleted
- **THEN** it is reconstructible
- **AND** no engineering fact is lost

### Requirement: Namespaced Extension Mechanism

Vendors or experimental modules MAY add namespaced extensions. Core readers
SHOULD preserve unknown namespaced extension data where practical. An extension
SHALL NOT redefine a node kind, a field, or an entity kind this specification
already defines.

#### Scenario: An extension does not redefine a core node kind

- **WHEN** an implementation adds an expression node kind
- **THEN** it adds it under the extension mechanism
- **AND** it does not redefine a core node kind

### Requirement: Security And Trust Boundaries

Elaboration executes arbitrary Python and SHALL run under workspace isolation
with no network access, only declared file inputs readable, no write access
outside its output directory, and enforced time and memory budgets. Secrets
SHALL NOT be reachable from an elaboration environment.

Simulator and layout executables SHALL run out of process against temporary
copies of their inputs, with the source project unreachable to them. Every
invocation SHALL be recorded with its identity, version, arguments, seed, exit
status, and resource use.

#### Scenario: An inference is never promoted to a fact for convenience

- **WHEN** a downstream consumer would find an asserted fact more convenient
  than an uncertain judgment
- **THEN** the kernel preserves the uncertainty
- **AND** it does not promote the inference to a fact

#### Scenario: Automatic modification is bounded by policy

- **WHEN** an automatic modification is proposed
- **THEN** it is bounded by the scope and authority the active project policy
  grants, enforced at the commit gate and at execution time
- **AND** safety-critical changes, high-energy systems, mains-connected
  hardware, battery protection, high-voltage designs, and other designated
  restricted classes pass the additional review gates of the applicable safety
  policy

#### Scenario: Findings can be marked as requiring human approval

- **WHEN** a finding, a generated change, or an assumption needs review
- **THEN** the implementation provides a mechanism to mark it as requiring human
  approval

### Requirement: Conformance Claims

A system claiming conformance SHALL produce all required artifacts; reject or
explicitly mark inputs that cannot be represented safely; preserve the required
evidence and provenance; expose unresolved unknowns rather than synthesizing
unsupported certainty; pass every acceptance test; and retain enough information
to reproduce or explain the resulting engineering state.

A conforming system SHALL additionally persist exactly one canonical model with
no second representation of the same facts; elaborate deterministically into a
graph snapshot and a tool plan with source locations on every entity; produce
stable identifiers that survive re-elaboration and repeated import of unchanged
sources; lower typed interface connections deterministically with provenance and
a recorded decision where a choice existed; evaluate interface compatibility
returning undecided rather than passing when an input is unknown; represent
topology intent separately from electrical equivalence and verify it by
enumerating conductive paths; mutate canonical state only through transactions
passing the commit gate by every mutation path including the agent's; execute
requested operations only as tools through a recorded plan with no direct engine
access from a program; generate the required views from graph facts only,
reproducibly for unchanged state; lower a simulation scope to an explicit plan
and normalize and provenance-tag every result; record third-party code
provenance and license terms for every extracted or wrapped component; and
remain useful on an imported project authored entirely outside Fang,
representing missing semantics as unknown.

#### Scenario: A partial implementation names its profile

- **WHEN** an implementation implements only part of this specification
- **THEN** it MAY advertise conformance to an explicitly named profile
- **AND** it does not claim full conformance

### Requirement: Representation Acceptance Tests

A conforming implementation SHALL demonstrate the representation-level
acceptance tests of the Engineering Intermediate Representation.

#### Scenario: AT-R1 lossless CAD import

- **WHEN** a representative KiCad project is imported
- **THEN** the import completes with no unreported data loss

#### Scenario: AT-R2 byte-identical reserialization

- **WHEN** unchanged kernel state is reserialized
- **THEN** the output is byte-identical under the canonical serialization rules

#### Scenario: AT-R3 stable identifiers across formatting changes

- **WHEN** a CAD source undergoes a non-semantic formatting change and is
  re-imported
- **THEN** every identifier is unchanged

#### Scenario: AT-R4 semantic diff of component, connectivity, and constraint changes

- **WHEN** a component, a connection, and a constraint each change
- **THEN** the semantic diff classifies all three changes correctly

#### Scenario: AT-R5 traceability to originating requirement or decision

- **WHEN** a generated component or net is queried for its origin
- **THEN** it traces to its originating requirement or decision where such
  provenance exists

#### Scenario: AT-R6 rejection of dangling required references

- **WHEN** state contains a required reference to a nonexistent identifier
- **THEN** validation rejects it

#### Scenario: AT-R7 explicit reporting of lossy adapter operations

- **WHEN** an adapter operation loses semantics
- **THEN** the loss is reported explicitly

#### Scenario: AT-R8 cross-machine derived identity and rename reporting

- **WHEN** the same project state is processed on different machines and runs
- **THEN** the derived identifiers are identical
- **AND** a rename is reported as a rename rather than as an addition and a
  removal

#### Scenario: AT-R9 provenance on every derived or imported entity

- **WHEN** state contains derived and imported entities
- **THEN** each carries a conforming provenance record

#### Scenario: AT-R10 rejection of an unimplemented major schema version

- **WHEN** an artifact declares a major schema version the implementation does
  not implement
- **THEN** the reader rejects it

#### Scenario: AT-R11 dimensional rejection at write time

- **WHEN** a dimensionally invalid constraint expression is written
- **THEN** it is rejected where it is written rather than at evaluation

#### Scenario: AT-R12 undecided reported as undecided

- **WHEN** a check result is undecided
- **THEN** it is reported as undecided and never as a pass or a failure

#### Scenario: AT-R13 rejection of an invalid requirement state transition

- **WHEN** a requirement state transition outside the permitted table is
  attempted
- **THEN** it is rejected

### Requirement: Kernel Acceptance Tests

A conforming implementation SHALL demonstrate the kernel-level acceptance tests.

#### Scenario: AT-K1 import with every mismatch reported

- **WHEN** a representative existing project is imported into the kernel graph
- **THEN** every mismatch against the source netlist is reported
- **AND** import fidelity is measured rather than gated here

#### Scenario: AT-K2 stable identifiers across repeated import and re-elaboration

- **WHEN** unchanged sources are imported repeatedly and unchanged programs are
  re-elaborated
- **THEN** identifiers are stable across all runs

#### Scenario: AT-K3 byte-identical snapshots from identical inputs

- **WHEN** the same source, dependency lock, and compiler version are elaborated
- **THEN** the snapshots are byte-identical, for the record stream as well as
  for the single document

#### Scenario: AT-K4 reproducible interconnect, power, and ground views

- **WHEN** the interconnect, power, and ground views are generated
- **THEN** no connection is absent from the snapshot
- **AND** repeated generation yields identical view graphs

#### Scenario: AT-K5 ground view and topology finding distinguish intent

- **WHEN** a ground view is generated and a topology check runs
- **THEN** the view represents topology intent distinctly from net equivalence
- **AND** the check names each unpermitted path

#### Scenario: AT-K6 safe edit round-tripped to CAD

- **WHEN** one safe edit is committed and round-tripped to CAD
- **THEN** no unrelated electrical change is introduced

#### Scenario: AT-K7 external rule-check results ingested after commit

- **WHEN** external rule-check results are ingested as evidence
- **THEN** the ingestion happens after commit and never before

#### Scenario: AT-K8 semantic diff separates presentation from electrical change

- **WHEN** a change set contains both a presentation change and an electrical
  change
- **THEN** the diff separates them
- **AND** it names the invalidated requirements

#### Scenario: AT-K9 rejected agent proposal leaves state unchanged

- **WHEN** an agent proposal is rejected
- **THEN** canonical state is unchanged
- **AND** the proposal still produces its diagnostics and its diff

#### Scenario: AT-K10 simulation result names its full context

- **WHEN** a simulation run completes
- **THEN** the result names its plan, backend version, models, assumptions, and
  coverage gaps

### Requirement: Rationale Queries Answerable From Graph State

An implementation SHALL be able to answer, from graph state alone and without a
model call, at least: which requirement caused a component to exist; which
datasheet claim supports a parameter; what depends on a rail, oscillator, or
domain; which requirements lost verification in a change; which assumptions are
still unverified; and which decisions rest on evidence that has since changed.

#### Scenario: A rationale query runs without a model call

- **WHEN** any of the six listed questions is asked
- **THEN** the answer is computed from graph structure alone
- **AND** no model call and no inference step is required

#### Scenario: An uncited claim is recorded as an assumption

- **WHEN** a claim is asserted without a citation
- **THEN** it is recorded as an assumption rather than as evidence

### Requirement: Declarative Module Composition

A module SHALL be declared as an ordinary Python class whose body assigns
parameters, nodes, and child modules. Each declaration is a template: every
instance of the owning module SHALL receive its own child rather than sharing
the one written in the class body.

Declaration order SHALL be the order the class body assigns, so that elaboration
does not depend on dictionary iteration or on memory address.

#### Scenario: Two instances do not share a child

- **WHEN** a module declaring a child module is instantiated twice
- **THEN** each instance owns a distinct child with a distinct identity

#### Scenario: A system is the root module of a design

- **WHEN** a design is elaborated
- **THEN** the root of the canonical semantic path is the system, and every
  entity beneath it is named by its position in the module tree

#### Scenario: Composition is connection between declared surfaces

- **WHEN** a parent connects two children
- **THEN** the connection is recorded between their declared surfaces rather
  than between internal implementation detail

### Requirement: Parameter Declaration And Reference

A parameter SHALL be declared with its unit, and a bare number SHALL NOT be
accepted as one. Reading a parameter off a module instance SHALL yield a
reference usable in a constraint expression, carrying the entity identifier, the
attribute name, and the declared dimension.

Assigning a quantity to a declared parameter SHALL record a value; assigning a
quantity of the wrong dimension SHALL be an elaboration error.

#### Scenario: A unit literal builds a quantity

- **WHEN** a program writes `3.3 * V`
- **THEN** the result is a scalar quantity of 3.3 volts whose magnitude is a
  decimal, not a binary float

#### Scenario: An undeclared parameter value is unknown, not defaulted

- **WHEN** a declared parameter is never assigned
- **THEN** its value is recorded with status `unknown`

#### Scenario: A dimensionally wrong assignment fails at elaboration

- **WHEN** a parameter declared in volts is assigned a quantity in amperes
- **THEN** elaboration fails with a `UNIT` diagnostic naming the parameter and
  its source location

### Requirement: Declared Constraints Are Not Evaluated Eagerly

`require()` SHALL record a constraint against the module that declared it rather
than evaluating it. A comparison between a parameter reference and a quantity
SHALL build an expression node rather than returning a Python boolean.

#### Scenario: A comparison builds an expression

- **WHEN** a program writes `require(self.vm.voltage <= 60 * V)`
- **THEN** a comparison expression node is constructed and stored
- **AND** no truth value is computed at declaration time

#### Scenario: A constraint that cannot yet be decided is recorded as undecided

- **WHEN** a declared constraint references a parameter whose value is unknown
- **THEN** evaluating it later yields undecided
- **AND** it is not silently treated as satisfied

### Requirement: The Connect Operator

Connecting two surfaces SHALL record a typed connection entity with provenance
naming the source location of the connection, and SHALL NOT mutate either
surface.

#### Scenario: Connecting records a typed connection

- **WHEN** a program connects a power output to a power input
- **THEN** a connection entity is recorded whose kind is `power`

#### Scenario: Connecting incompatible surface kinds is refused

- **WHEN** a program connects surfaces whose kinds cannot form a connection
- **THEN** elaboration fails with an `ELAB` diagnostic naming both surfaces

### Requirement: The Elaboration Result

Elaboration SHALL return exactly a graph snapshot, a tool plan, and the
diagnostics it produced. It SHALL NOT return the Python object graph, and the
Python object graph SHALL NOT be reachable from the snapshot.

#### Scenario: A failed elaboration returns no partial graph

- **WHEN** elaboration produces an error-severity diagnostic
- **THEN** the result carries the diagnostics and no snapshot

#### Scenario: Re-elaborating unchanged source is byte-identical

- **WHEN** the same program is elaborated twice
- **THEN** the two snapshots serialize to identical bytes

#### Scenario: Every entity carries the source location that produced it

- **WHEN** any entity is created by elaboration
- **THEN** it carries the file and line of the declaration that produced it

### Requirement: Elaboration Sandbox Enforcement

The sandbox SHALL make undeclared input unavailable rather than merely
discouraged. Network access SHALL be denied outright during elaboration, and a
file input SHALL be readable only when it was declared and hashed into the
snapshot.

#### Scenario: A network call during elaboration fails

- **WHEN** a program opens a socket during elaboration
- **THEN** the attempt raises and elaboration fails with an `ELAB` diagnostic

#### Scenario: An undeclared file input is unavailable

- **WHEN** a program reads a file it did not declare
- **THEN** the read fails rather than silently succeeding

#### Scenario: A declared input is hashed into the snapshot

- **WHEN** a program declares a file input
- **THEN** the snapshot records the input's identifier and its content hash

#### Scenario: Randomness requires a declared seed

- **WHEN** a program uses randomness without declaring a seed
- **THEN** elaboration fails
- **AND** a declared seed is recorded in the snapshot

### Requirement: Trait Registration And Enumeration

A trait SHALL declare the protocol it satisfies, and the kernel SHALL enumerate
the entities carrying a given trait without instantiating any backend.

#### Scenario: Traits are enumerable by protocol

- **WHEN** the kernel is asked for every entity carrying a simulation trait
- **THEN** it answers from recorded traits alone
- **AND** no simulator, layout engine, or renderer is constructed

#### Scenario: A trait attaches to an entity rather than widening its class

- **WHEN** a component gains a footprint, a model, and sourcing metadata
- **THEN** each attaches as a trait
- **AND** the component's class is unchanged

### Requirement: The Shipped Interface Catalogue

The kernel SHALL ship interface definitions covering at least I2C, SPI, UART,
USB 2, CAN, RS-485, PWM, quadrature encoder, power input, power output, analog
input, analog output, motor phase, JTAG, serial wire debug, clock, and reset.
Each definition SHALL own its member signals, their roles, its electrical
parameters, and its compatibility rules, and a project SHALL be able to define
its own.

#### Scenario: Every named interface is present with its signals

- **WHEN** the catalogue is enumerated
- **THEN** each named interface is present
- **AND** each carries at least one required signal with a role

#### Scenario: A project defines its own interface

- **WHEN** a project declares an interface type the catalogue does not carry
- **THEN** it participates in lowering and compatibility exactly as a shipped one

### Requirement: The Pin Model

A part SHALL declare its pins with their canonical electrical roles, and SHOULD
preserve the vendor's pin names. A part SHALL declare which pins can carry which
interface signal, and MAY name several candidates for one signal.

#### Scenario: A pin preserves its vendor name

- **WHEN** a part declares a pin named `PB8`
- **THEN** the pin entity records `PB8` as its vendor name alongside its role

#### Scenario: A signal may name several candidate pins

- **WHEN** a part declares two pins able to carry one interface signal
- **THEN** both are recorded as candidates for that signal

### Requirement: Deterministic Pin Assignment

Lowering an interface connection SHALL assign pins deterministically for a given
graph state and part selection: the same graph SHALL always produce the same
assignment, independent of iteration order or the order connections were
written.

#### Scenario: The same graph lowers identically every time

- **WHEN** the same design is elaborated twice
- **THEN** every pin assignment is identical

#### Scenario: One pin does not carry two signals

- **WHEN** two signals name the same candidate pin
- **THEN** the assignment gives the pin to exactly one of them and finds another
  for the other, or fails explicitly if none remains

#### Scenario: A lowered connection names the interface connection it came from

- **WHEN** an interface connection lowers to pin connections
- **THEN** each pin connection carries provenance naming the interface connection
- **AND** the lowering is re-derivable from the same graph state

### Requirement: A Pin Choice Is A Recorded Decision

Where a part offers alternative pin assignments and the lowering selects one, the
choice SHALL be recorded as a design decision entity naming the alternatives it
rejected.

#### Scenario: An alternative assignment becomes a decision

- **WHEN** a signal has more than one candidate pin and one is chosen
- **THEN** a decision entity records the choice, its rationale, and the rejected
  alternatives

#### Scenario: A single candidate is not a decision

- **WHEN** a signal has exactly one candidate pin
- **THEN** no decision entity is created, because no choice existed

### Requirement: An Incomplete Lowering Fails Explicitly

A lowering that cannot be completed SHALL fail with a diagnostic naming the
unsatisfiable signal, and SHALL NOT produce a partial pin mapping.

#### Scenario: A required signal with no pin fails the lowering

- **WHEN** a required interface signal has no candidate pin on one side
- **THEN** lowering fails with `IFACE-0001` naming that signal
- **AND** no pin connection from that lowering is recorded

#### Scenario: Interfaces disagreeing on membership fail the lowering

- **WHEN** two connected interfaces do not share the required signal set
- **THEN** lowering fails with `IFACE-0002` naming the disagreement

### Requirement: Interface Compatibility Evaluation

The compatibility check SHALL evaluate logic-level margin, current capability,
voltage-domain agreement across every participant, pull-up supply validity,
open-drain requirements, and protocol, rate, and addressing agreement. A check
whose inputs are unknown SHALL return undecided naming the missing input.

#### Scenario: A logic-level shortfall fails

- **WHEN** a source's VOH minimum is below the sink's VIH minimum plus margin
- **THEN** the check fails and names both parameters

#### Scenario: An unknown input returns undecided naming what is missing

- **WHEN** a sink's VIH minimum is unknown
- **THEN** the check returns undecided and names `vih_min` as the missing input
- **AND** it does not pass by default

#### Scenario: A bus checks every participant

- **WHEN** three participants share a bus and one is in a different voltage domain
- **THEN** the check reports the mismatch and names the participant

#### Scenario: An open-drain bus without a pull-up fails

- **WHEN** an open-drain interface has no pull-up declared on the bus
- **THEN** the check fails naming the missing pull-up

#### Scenario: A datasheet-sourced input cites its evidence

- **WHEN** a compatibility input came from a datasheet
- **THEN** the result cites the evidence entity that supplied it

### Requirement: The Part Model

A part SHALL separate its logical identity, its selected vendor part, its
package, its sourcing identity, its parameterization, and its physical instance.
A part SHALL declare a designator prefix, and a generic part SHALL carry no
vendor identity until one is selected.

#### Scenario: A generic part has no vendor identity

- **WHEN** a generic resistor is declared with only a resistance
- **THEN** its manufacturer and part number are absent rather than invented

#### Scenario: Selecting a vendor part records it as sourcing

- **WHEN** a manufacturer and part number are selected for a part
- **THEN** they attach as a sourcing trait rather than replacing the part's
  logical identity

#### Scenario: A designator prefix is declared per part type

- **WHEN** a resistor, a capacitor, and an integrated circuit are declared
- **THEN** their designator prefixes are `R`, `C`, and `U`

### Requirement: The Standard Part Library

The kernel SHALL ship generic parts covering at least resistor, capacitor,
inductor, diode, LED, fuse, crystal, transistor, voltage regulator, connector,
test point, and mounting hole. Each SHALL declare its pins, its pin map, and the
parameters its type carries.

#### Scenario: A two-pin passive lowers to its two pins

- **WHEN** two generic two-pin parts are connected
- **THEN** the connection lowers to a pin connection on each part

#### Scenario: Each library part declares the parameters its type carries

- **WHEN** a capacitor is declared
- **THEN** it carries capacitance, and a voltage rating it may leave unknown

#### Scenario: A part with no electrical function still participates

- **WHEN** a mounting hole is declared
- **THEN** it is a part with a mechanical surface and no electrical pins

### Requirement: Net Inference

Nets SHALL be inferred as the equivalence classes that conductive pin
connections form, and SHALL represent logical connectivity independent of
visual labels. An inferred net SHALL carry provenance naming the connections it
was inferred from.

#### Scenario: Connected pins form one net

- **WHEN** three pins are connected in a chain
- **THEN** one net contains all three

#### Scenario: Unconnected pins form separate nets

- **WHEN** two pins are never connected
- **THEN** they belong to different nets

#### Scenario: A non-conductive connection does not merge nets

- **WHEN** two pins are joined by a dependency or containment connection
- **THEN** they remain in separate nets

#### Scenario: Net inference is reproducible

- **WHEN** the same graph is compiled twice
- **THEN** the nets, their names, and their membership are identical

### Requirement: Deterministic Designator Assignment

Designators SHALL be assigned deterministically from the canonical semantic path
so that the same design always yields the same designator for the same part.
Each part type's declared prefix SHALL be used, and numbering SHALL start at one
within each prefix.

#### Scenario: The same design yields the same designators

- **WHEN** a design is compiled twice
- **THEN** every designator is unchanged

#### Scenario: Numbering is per prefix

- **WHEN** a design holds two resistors and one capacitor
- **THEN** the designators are `R1`, `R2`, and `C1`

#### Scenario: An authored designator is preserved

- **WHEN** a part already carries a designator
- **THEN** assignment keeps it and does not renumber it

### Requirement: The Netlist Is A Projection

A netlist SHALL name the graph snapshot it was compiled from, and SHALL contain
no component, pin, or net absent from that snapshot. Compiling a netlist SHALL
NOT mutate the graph.

#### Scenario: A netlist names its parent snapshot

- **WHEN** a netlist is compiled
- **THEN** it records the content hash of the snapshot it came from

#### Scenario: Compiling does not mutate the graph

- **WHEN** a netlist is compiled from a snapshot
- **THEN** the snapshot's content hash is unchanged afterwards

#### Scenario: Emission is byte-identical for unchanged input

- **WHEN** the same netlist is emitted twice
- **THEN** the two files are byte-identical

### Requirement: The External Identifier Mapping Table

An import SHALL record every external identifier in an explicit mapping table
alongside the canonical identifier it was given. The table SHALL be part of the
persisted state, and re-importing unchanged sources SHALL reuse the same
canonical identifiers.

#### Scenario: An external identifier maps to a canonical one

- **WHEN** a component is imported carrying the reference `R1`
- **THEN** the mapping table records `R1` against the canonical identifier
- **AND** `R1` is not used as the canonical identifier

#### Scenario: Re-importing unchanged sources reuses identifiers

- **WHEN** the same file is imported twice
- **THEN** every canonical identifier is unchanged

#### Scenario: An identifier the exporter wrote is recovered

- **WHEN** a file carries a canonical identifier written by an earlier export
- **THEN** the import reuses it rather than minting a new one

### Requirement: Imports Report What They Could Not Represent

An adapter SHALL report every construct it could not represent and SHALL NOT
silently discard semantics. The report SHALL name the construct and where it
appeared.

#### Scenario: An unsupported construct is reported

- **WHEN** a file carries a construct the adapter does not model
- **THEN** the import report names it
- **AND** the import still produces the entities it could recover

#### Scenario: A lossless import reports no loss

- **WHEN** a file contains only constructs the adapter models
- **THEN** the report is empty

#### Scenario: Missing semantics are unknown rather than invented

- **WHEN** an imported component has no value in the file
- **THEN** its value is recorded as unknown
- **AND** no intent is fabricated for it

### Requirement: One Safe Round Trip

A design imported from CAD, changed through one committed transaction, and
emitted again SHALL differ only by that change. No unrelated electrical change
SHALL appear.

#### Scenario: An unchanged import re-emits unchanged

- **WHEN** a file is imported and immediately re-emitted with no transaction
- **THEN** the components and nets are unchanged

#### Scenario: One safe edit changes only what it names

- **WHEN** one component's value is changed through a transaction and the design
  is re-emitted
- **THEN** only that component's value differs
- **AND** every net and every other component is unchanged

### Requirement: Tool Terminal Statuses

Every tool call SHALL end in exactly one terminal status: succeeded, failed,
unsupported, skipped, or cancelled. A plan requesting an operation no tool
supports SHALL return unsupported rather than a degraded attempt.

#### Scenario: An unregistered tool returns unsupported

- **WHEN** a plan names a tool the registry does not carry
- **THEN** the call ends unsupported
- **AND** no substitute is attempted

#### Scenario: A failing tool ends failed and stops dependents

- **WHEN** a tool raises
- **THEN** its call ends failed
- **AND** a later call conditioned on its success is skipped rather than run

### Requirement: Conditions Resolve In The Operation Phase

A symbolic condition recorded during elaboration SHALL be resolved when the
operation phase runs. A call whose condition resolves false SHALL be skipped,
and the skip SHALL be recorded rather than silently dropped.

#### Scenario: A false condition skips the call

- **WHEN** an export is conditioned on a check passing and the check failed
- **THEN** the export is skipped and the run records why

#### Scenario: A true condition runs the call

- **WHEN** the check passes
- **THEN** the export runs

### Requirement: Tool Calls Are Idempotent

A tool call SHALL be idempotent for the same graph snapshot, content-addressed
inputs, configuration, and seed. Running the same plan against the same snapshot
twice SHALL produce the same results.

#### Scenario: The same plan against the same snapshot repeats its result

- **WHEN** a plan is executed twice against one snapshot
- **THEN** every result is identical

#### Scenario: A different snapshot is a different run

- **WHEN** the snapshot changes
- **THEN** the run is not served from the previous one's results

### Requirement: The Operation Phase Does Not Mutate Canonical State

Operations SHALL execute against immutable snapshots and SHALL NOT mutate the
graph. A realization implying a semantic change SHALL return it through a
transaction.

#### Scenario: Running a plan leaves the graph unchanged

- **WHEN** a plan runs to completion
- **THEN** the graph's head is unchanged

#### Scenario: An implied semantic change returns through the gate

- **WHEN** a tool produces a realization implying a parameter change
- **THEN** that change reaches canonical state only as a committed transaction

### Requirement: The Workspace Layout

A project's kernel state SHALL persist beside its sources under a workspace
directory holding the canonical record stream, a manifest, declared sources,
cited evidence, and a cache. The manifest SHALL record the schema version, the
revision, and the snapshot hash.

#### Scenario: The workspace round-trips a design

- **WHEN** a snapshot is written and read back
- **THEN** every entity is recovered with its identity intact

#### Scenario: The manifest records what produced the state

- **WHEN** a workspace is written
- **THEN** the manifest names the schema version, the revision, the compiler
  version, and the snapshot hash

#### Scenario: Deleting the cache loses no engineering fact

- **WHEN** the cache directory is deleted and the project is rebuilt
- **THEN** the resulting snapshot hash is unchanged

#### Scenario: The mapping table persists between runs

- **WHEN** a project is imported, saved, and imported again
- **THEN** the second import reuses the canonical identifiers of the first

### Requirement: The Command Surface

The command line SHALL expose building, checking, and exporting a design, and
each command SHALL exit non-zero when the work it names did not succeed.

#### Scenario: Building a program writes the workspace

- **WHEN** `build` runs against a Fang program
- **THEN** the workspace holds the design records and the manifest
- **AND** the command exits zero

#### Scenario: A failing check exits non-zero

- **WHEN** `check` runs against a design with a failing hard constraint
- **THEN** the command reports the failure and exits non-zero

#### Scenario: A failed elaboration reports its diagnostics

- **WHEN** a program fails to elaborate
- **THEN** the command prints each diagnostic with its code and source location
- **AND** exits non-zero without writing a partial workspace

### Requirement: The View Specification

A view SHALL be defined by what it includes and what it annotates, and the
compiled specification SHALL be recorded with the view so the question a diagram
answers is inspectable.

A natural-language question MAY compile into a view specification: a model
selects the semantics, and deterministic code performs the traversal, the
layout, and the rendering. Because the compiled specification is recorded with
the view, such a diagram remains reproducible without the model.

#### Scenario: A view records the specification that produced it

- **WHEN** a view is compiled
- **THEN** it carries the specification's name, its included kinds, and its
  annotations

#### Scenario: A view names the snapshot it projects

- **WHEN** a view is compiled from a snapshot
- **THEN** it records that snapshot's content hash

### Requirement: The Required Views

The implementation SHALL provide the system, interconnect, power, ground,
interfaces, and safety views, each answering one engineering question from graph
facts alone.

#### Scenario: Every required view is available by name

- **WHEN** the view registry is enumerated
- **THEN** all six required views are present

#### Scenario: The power view shows only power connectivity

- **WHEN** the power view is compiled over a design with power and signal nets
- **THEN** its edges are power edges and its signal edges are absent

#### Scenario: The ground view distinguishes intent from net equivalence

- **WHEN** the ground view is compiled over a design carrying a topology
  constraint
- **THEN** the constraint appears as an annotation distinct from the net's
  membership

### Requirement: A View Contains Nothing Absent From Its Snapshot

A view SHALL be generated only from facts in the graph, and SHALL expose the
completeness of what it shows.

#### Scenario: Every node and edge traces to an entity

- **WHEN** any view is compiled
- **THEN** every node and every edge names an entity present in the snapshot

#### Scenario: A view reports what is unknown in it

- **WHEN** a view includes an entity carrying unknown parameters
- **THEN** the view reports that incompleteness rather than hiding it

#### Scenario: Repeated generation is identical

- **WHEN** a view is compiled twice from unchanged graph state
- **THEN** the two view graphs are identical

### Requirement: The Layout Boundary

Input to layout SHALL carry only layout information: node identity, node
dimensions, ports, edges, hierarchy, and hints. It SHALL NOT carry engineering
meaning, and no engineering decision SHALL depend on layout output.

#### Scenario: The layout request carries no engineering meaning

- **WHEN** a view graph is prepared for layout
- **THEN** the request holds identity, dimensions, ports, edges, hierarchy, and
  hints, and nothing else

#### Scenario: Layout output becomes a positioned view graph

- **WHEN** layout returns positions
- **THEN** they are applied to the view graph, and rendering remains the
  kernel's own

#### Scenario: Placement seeds are presentation state

- **WHEN** a placement seed is stored
- **THEN** it is kept separately from canonical identity
- **AND** changing it classifies as a presentation change

### Requirement: Rationale Authored From The Program

A Fang program SHALL be able to create requirements, assumptions, decisions,
alternatives, evidence, and calculations where the engineering happens, rather
than in a separate document that drifts. Each SHALL become an entity carrying
the source location that declared it.

#### Scenario: A requirement declared in a program becomes an entity

- **WHEN** a program declares a requirement
- **THEN** a requirement entity exists carrying its statement, state, and source
  location

#### Scenario: A decision names its alternatives and the requirements it serves

- **WHEN** a program records a decision between two parts
- **THEN** the decision entity names the selection, the rejected alternatives,
  the requirements it serves, and the evidence it cites

#### Scenario: A claim without a citation is recorded as an assumption

- **WHEN** a program states a claim and cites no evidence
- **THEN** it is recorded as an assumption rather than as evidence

### Requirement: Calculations Are First-Class

A calculation SHALL be an entity recording its expression, its inputs, its
result, and the requirement it serves, so that a later change can invalidate it.

#### Scenario: A calculation records what it depends on

- **WHEN** a calculation is declared over two parameters
- **THEN** the entity names both as inputs

#### Scenario: Changing an input invalidates the calculation

- **WHEN** a parameter a calculation depends on changes
- **THEN** the semantic diff names that calculation as invalidated

### Requirement: Verification Results Form A Graph

A verification SHALL be an entity naming what it verifies, the method used, the
evidence it rests on, and its result, so that requirement coverage is answerable
from graph structure alone.

#### Scenario: A verification links a requirement to its evidence

- **WHEN** a verification is recorded against a requirement
- **THEN** the requirement's coverage is answerable without inference

#### Scenario: An uncovered requirement is visible

- **WHEN** a requirement has no verification
- **THEN** a coverage query names it as uncovered

### Requirement: Impact Propagation

A change SHALL propagate to the calculations, requirements, and verifications
that depend on what changed, and the diff SHALL name them.

#### Scenario: A parameter change names the requirement it puts at risk

- **WHEN** a parameter under a constraint that serves a requirement changes
- **THEN** the diff names that requirement as impacted

#### Scenario: A verified requirement whose evidence changed is reported

- **WHEN** evidence a verification rests on changes
- **THEN** the affected verification and requirement are named

### Requirement: Simulation Plan Validation

Plan compilation SHALL validate that every selected component has a compatible
model, that pin maps are complete, that unsupported components are explicitly
abstracted, that model distribution constraints are respected, and that
simulator options are deterministic and recorded. A plan failing any of these
SHALL be rejected with the reason.

#### Scenario: A component with no compatible model rejects the plan

- **WHEN** a selected component carries no model for the chosen backend
- **THEN** the plan is rejected naming that component
- **AND** no substitute model is used

#### Scenario: An incomplete pin map rejects the plan

- **WHEN** a model's pin map does not cover the component's pins in scope
- **THEN** the plan is rejected naming the missing pins

#### Scenario: An unsupported component may be explicitly abstracted

- **WHEN** a component without a model is explicitly listed as abstracted
- **THEN** the plan compiles and records the abstraction as an assumption

#### Scenario: A restricted model's terms are respected

- **WHEN** a model forbids redistribution and the plan would embed it
- **THEN** the plan records the restriction and references the model rather than
  inlining it

#### Scenario: Simulator options are deterministic and recorded

- **WHEN** a plan is compiled twice with the same inputs
- **THEN** the two plans are identical, including their options and seed

### Requirement: SPICE Lowering

The kernel SHALL lower a simulation plan into the simulator's native netlist
rather than binding to a wrapper library. The lowering SHALL be deterministic
for a given plan.

#### Scenario: A plan lowers to a netlist naming its nets and devices

- **WHEN** a plan over a resistor divider is lowered
- **THEN** the netlist carries a device line per component and an analysis line
  for the requested analysis

#### Scenario: Lowering is deterministic

- **WHEN** the same plan is lowered twice
- **THEN** the two netlists are byte-identical

#### Scenario: Backend assumptions stay out of component definitions

- **WHEN** a component is defined
- **THEN** it carries models and no backend-specific syntax

### Requirement: Backends Are Reached Across A Process Boundary

A simulator SHALL be reached across a process boundary, and its version SHALL be
recorded with every result. A backend that is not installed SHALL report
unsupported rather than producing a substitute result.

#### Scenario: A missing simulator reports unsupported

- **WHEN** the chosen backend is not installed
- **THEN** the run reports unsupported and names the backend
- **AND** no result is fabricated

#### Scenario: A result records the backend and its version

- **WHEN** a run completes
- **THEN** the normalized result names the backend and the version that ran

### Requirement: Normalized Simulation Results

A result SHALL record the plan, the backend and its version, the models used and
their provenance, the assumptions applied, and the coverage the run does not
provide. Sample data SHALL be referenced as an artifact rather than inlined.

#### Scenario: A result names its full context

- **WHEN** a run completes
- **THEN** its normalized form names the plan, the backend version, the models,
  the assumptions, and the coverage gaps

#### Scenario: A simulation pass is not proof of physical correctness

- **WHEN** a simulation passes its assertions
- **THEN** it is recorded as a finding with a confidence
- **AND** it is not recorded as proof

#### Scenario: Sample data is referenced, not inlined

- **WHEN** a run produces waveform samples
- **THEN** the result references them as an artifact

### Requirement: Verification Level Selection

The kernel SHOULD select the cheapest verification level that can decide a
question, over equation checks, symbolic analysis, behavioural simulation,
circuit simulation, and specialized external analysis. The selected level SHALL
be recorded with the question, so that a cheap answer is distinguishable from an
expensive one.

#### Scenario: A question an equation can decide does not run a simulator

- **WHEN** a question is decidable by calculation
- **THEN** the equation level is selected

#### Scenario: A question needing analog detail selects circuit simulation

- **WHEN** a question needs analog detail no equation covers
- **THEN** the circuit-simulation level is selected

### Requirement: The Agent Surface

The kernel SHALL expose an agent surface speaking the Model Context Protocol,
offering the committed snapshot, the compiled netlist, the check results, the
required views, and the rationale queries.

The agent surface is a projection. It SHALL NOT hold state of its own, and it
SHALL NOT answer from any store other than the kernel graph and the workspace
the kernel already persists.

#### Scenario: The surface holds nothing the kernel does not

- **WHEN** a session runs to completion
- **THEN** no fact it served was read from a store of its own
- **AND** every value it returned is derivable from the snapshot it names

#### Scenario: A rationale question is answered from graph structure

- **WHEN** an agent asks which requirement caused a component to exist
- **THEN** it receives the recorded chain of provenance and decisions
- **AND** no inference step was taken to produce it

#### Scenario: A view is served with what it left out

- **WHEN** an agent requests one of the required views
- **THEN** it receives that view's nodes and edges
- **AND** it receives the notes recording what the view omitted

#### Scenario: The surface names the snapshot it answered from

- **WHEN** any response is returned
- **THEN** it carries the hash of the snapshot it was computed against

### Requirement: Agent Mutation Passes The Commit Gate

An agent SHALL mutate canonical state only by submitting a transaction that the
commit gate evaluates. The agent surface SHALL NOT expose an operation kind the
gate does not evaluate, and SHALL NOT expose any other means of writing an
entity, a parameter, or a connection.

A rejected proposal SHALL be returned with its diagnostics and with the diff the
transaction would have made, because the explanation is the useful output of a
rejection. Advancing the head SHALL require a proposal the gate accepted.

#### Scenario: A rejected transaction returns its explanation

- **WHEN** an agent proposes a transaction the gate rejects
- **THEN** the response carries the rejection's diagnostics and its diff
- **AND** the committed head is unchanged

#### Scenario: A stale base is refused

- **WHEN** an agent proposes against a snapshot that is no longer the head
- **THEN** the proposal is rejected with the stale-base diagnostic
- **AND** no operation is applied

#### Scenario: Committing requires an accepted proposal

- **WHEN** an agent asks to commit a proposal the gate did not accept
- **THEN** the request is refused with a diagnostic code
- **AND** the head does not advance

#### Scenario: An undecided result over a must-be-decided requirement blocks the agent

- **WHEN** an agent proposes a transaction whose checks leave a must-be-decided
  requirement undecided
- **THEN** the gate rejects the proposal
- **AND** the response names the undecided result rather than reporting a pass

#### Scenario: The agent's commit is bounded by the active policy

- **WHEN** an agent commits a transaction whose class the active project policy
  reserves for human approval
- **THEN** the gate withholds the commit for want of approval
- **AND** the response names the approval that is required

### Requirement: Deterministic Agent Responses

Every response the agent surface returns SHALL be canonical. Identical kernel
state SHALL yield byte-identical responses, within one run and across processes.

#### Scenario: The same question twice gives the same bytes

- **WHEN** a tool is called twice against unchanged state
- **THEN** the two responses are byte-identical

#### Scenario: Responses do not depend on hash ordering

- **WHEN** the same question is asked in two processes started with differing
  hash seeds
- **THEN** the two responses are byte-identical

#### Scenario: A magnitude crosses the boundary as a decimal

- **WHEN** a response carries a physical quantity
- **THEN** its magnitude is a decimal string
- **AND** it is not a binary floating point number

### Requirement: The Agent Session Is Bound To One Project

A session SHALL be bound to a single project root, named when the server starts
rather than chosen by the client. Elaboration performed for a session SHALL run
under the elaboration sandbox.

The agent surface SHALL NOT elaborate, read, or write anything outside that root
at a client's request.

#### Scenario: A path outside the project root is refused

- **WHEN** a client names a program or a file outside the bound project root
- **THEN** the request is refused with a diagnostic code
- **AND** nothing outside the root is read or executed

#### Scenario: Elaboration for an agent obeys the sandbox

- **WHEN** a program is elaborated to answer an agent's request
- **THEN** it runs with no network access and only its declared inputs readable
- **AND** a reach outside that boundary is reported as a violation rather than
  served

#### Scenario: Secrets are not reachable from a session

- **WHEN** a program elaborated for a session reads its environment
- **THEN** the secrets of the surrounding environment are not reachable

### Requirement: Undecided Crosses The Agent Boundary Intact

An unknown value and an undecided result SHALL cross the agent surface as
themselves. The surface SHALL NOT render an unknown as null, absent, zero, or
false, and SHALL NOT render an undecided result as either a pass or a failure.

#### Scenario: An undecided check is reported as undecided

- **WHEN** a check is undecided because an operand is unknown
- **THEN** the agent receives a third status distinct from pass and from failure

#### Scenario: An unknown value is distinguishable from an absent one

- **WHEN** a parameter carries an explicitly unknown value
- **THEN** the response distinguishes it from a parameter that was never set

#### Scenario: A conflicting value keeps its candidates

- **WHEN** a parameter holds unresolved conflicting candidates
- **THEN** the response carries every candidate and its source
- **AND** no candidate is selected on the agent's behalf

### Requirement: The Agent Surface Refuses With A Code

Where the agent surface cannot do what was asked, it SHALL refuse with a
namespaced diagnostic code and SHALL NOT return a fabricated, partial, or
plausible result in place of the work it did not do.

#### Scenario: A missing optional dependency is named

- **WHEN** the surface is started without the dependency it needs to serve the
  protocol
- **THEN** it reports what is missing and exits non-zero
- **AND** it does not start a degraded server

#### Scenario: An unknown tool or a malformed argument is refused

- **WHEN** a client calls a tool that does not exist, or passes an argument that
  does not parse
- **THEN** the surface refuses with a diagnostic code
- **AND** no state is read or written on the strength of the request

#### Scenario: A program that fails to elaborate yields diagnostics, not a snapshot

- **WHEN** the bound program fails to elaborate
- **THEN** the agent receives every diagnostic with its code and source location
- **AND** it receives no snapshot, partial or otherwise

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
be recorded as a coverage gap. A measure's window SHALL be along the analysis's
axis and SHALL start before it ends; a window that does not SHALL be refused
where it is declared, and never lowered to a measurement over nothing.

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

#### Scenario: A window that does not start before it ends is refused

- **WHEN** a question averages a surface after 2 ms and until 1 ms, or takes
  any statistic over a window whose start is not before its end
- **THEN** the declaration is refused naming the statistic, the window and the
  surface, with the code an emulation count's empty window is refused with
- **AND** no measurement over the window is lowered

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
its question afresh gives the job its evidence records. Every provenance record
the runner appends to an existing entity, in a measurement, a failure or an
answer at the equation level, SHALL carry a fields list naming each fact it set
there: a measured value by its parameter's path followed by `value`, and on the
verification its result, evidence, level and tool. A measured value kept
across re-elaboration SHALL keep the record that set it.

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

#### Scenario: A record that changes an entity names what it set

- **WHEN** a run's measurements are committed
- **THEN** the part holding a measured parameter gains the run's provenance
  record, its fields list naming the measured value, such as
  `parameters.ripple.value`, and nothing else of the part
- **AND** the verification gains the run's record naming its result, evidence,
  level and tool
- **AND** the evidence the run adds, which the record creates, names no fields

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
rejection for any other reason SHALL record nothing. A committed measurement
carried across re-elaboration that a hard constraint the program now states
fails SHALL NOT be carried into the design: its verification SHALL be carried
with a failed result and its evidence, and the measured parameter without a
value, as the transaction recording the failure leaves them.

#### Scenario: A value that breaks a hard constraint never reaches the head

- **WHEN** a measured value violates a hard constraint
- **THEN** the measured parameter is still unknown on the head
- **AND** the rejection names the constraint that failed

#### Scenario: The failure is recorded as knowledge

- **WHEN** a measured value violates a hard constraint
- **THEN** the head holds the run's evidence and the verification with a failed
  result naming that evidence

#### Scenario: A constraint tightened past a committed measurement records its failure

- **WHEN** a measurement committed as a pass is still current, and the program
  is rebuilt with a hard constraint over it tightened past the measured value
- **THEN** the rebuilt design is persisted, holding the run's evidence and the
  verification with a failed result naming that evidence
- **AND** the measured parameter is unknown in it, and nothing runs again
- **AND** with the constraint relaxed again, the recorded run re-enters and the
  verification passes

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

### Requirement: A Port May Be One Peripheral Instance

A part's interface port SHALL be able to name the peripheral instance it is,
and the instance SHALL be recorded on the port entity. Each candidate pin of a
port SHALL be able to carry the selector that routes the port's signal to that
pin, and a part that declares any selector SHALL name the evidence its
selectors were taken from. When a lowering chooses a pin that carries a
selector, the pin connection it records SHALL carry that selector and the
evidence for it. A lowering SHALL assign the signals of one connection only
from the candidates of the port that connection names. A package pad number
SHALL NOT be used as, or used to derive, a port pin index.

#### Scenario: The instance is recorded on the port

- **WHEN** a part declares an I2C port as the peripheral instance `I2C1`
- **THEN** the port entity in the snapshot names `I2C1`

#### Scenario: Two controllers are two ports

- **WHEN** a part offers I2C on two controllers, declared as two ports, and a
  connection names one of them
- **THEN** every pin the lowering assigns for that connection is a candidate
  of the named port

#### Scenario: The chosen pin's selector reaches the graph

- **WHEN** a lowering assigns `i2c1.scl` to a candidate declared with selector
  `AF4`
- **THEN** the pin connection it records carries `AF4` for that pin
- **AND** it names the evidence entity the part cited for its selectors

#### Scenario: A selector without evidence is refused

- **WHEN** a part declares selectors on its candidates and names no evidence
  for them
- **THEN** elaboration fails with an `IFACE` diagnostic naming the part

#### Scenario: Candidates without selectors lower as before

- **WHEN** a part declares its candidates as a list of pin names
- **THEN** the lowering, the pin connections and the decisions it records are
  identical to those of the previous release

### Requirement: An Addressed Bus Device Carries Its Address

The port of an addressed bus device SHALL be able to carry its address, either
as a fixed dimensionless value or as a strap: one of the device's pins together
with the address each of the device's own pins selects when the strap is tied
to it. A strapped address SHALL be resolved from the board's nets, by the
device pin that shares the strap pin's net. The compatibility check's
addressing rule SHALL read these addresses for every participant of a
multi-drop bus. A port that declares no address SHALL NOT be treated as
addressed.

#### Scenario: Two devices at one address fail

- **WHEN** two devices on one I2C bus declare the fixed address 0x48
- **THEN** the compatibility check fails and names both ports

#### Scenario: A strap tied to ground selects its address

- **WHEN** a device's strap pin shares a net with the device's own ground pin,
  and the strap maps that pin to 0x48
- **THEN** the device's address is resolved as 0x48, and the addressing rule
  compares it like a fixed address

#### Scenario: A strap on no net is reported, not resolved

- **WHEN** a device's strap pin is on no net, or on a net none of the pins in
  its strap map shares
- **THEN** the device's address is unknown
- **AND** the addressing rule returns undecided naming the strap pin

#### Scenario: An ambiguous strap is reported

- **WHEN** a device's strap pin shares a net with two pins of its strap map
- **THEN** the device's address is unknown
- **AND** the addressing rule returns undecided naming the strap pin and both
  pins

#### Scenario: A controller with no address is not reported

- **WHEN** a bus controller's port declares no address
- **THEN** the addressing rule neither fails nor returns undecided on its
  account

#### Scenario: An address is not a bare number

- **WHEN** a port is given an address as a plain integer rather than a
  dimensionless quantity or a strap
- **THEN** elaboration fails with a diagnostic naming the parameter

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
scope with its controller instance, its chosen pins and their selectors, each
a selector the platform descriptor reads, the electrical requirements of its signals, and each device's address, a whole
number the emulator is given as the graph holds it; each
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
effects. A selector the platform cannot read SHALL refuse the plan, and a
pin-configuration measure over a pin whose selector it cannot read SHALL
produce no value, so that no pin is counted as configured with its selector
unchecked.

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

#### Scenario: A selector the platform does not read is refused

- **WHEN** a bus pin's selector is not one the platform descriptor reads, such
  as `AF_4` on a platform that reads `AF0` to `AF15`
- **THEN** the plan is refused naming the pin and the selector
- **AND** a pin-configuration measure over such a pin has no value, rather
  than a count that skipped its selector

### Requirement: Absence Is An Observation; An Incomplete Run Is Not

In a run that completed, an event that did not occur SHALL be measured as not
having occurred before the run's end, so that a constraint bounding its time
from above is decided. In a run that ended on a timeout or a crash, a measure
SHALL produce no value. A measure over a model that reported a warning its
descriptor does not expect SHALL produce no value, and the evidence SHALL name
the warning. A warning the model's descriptor expects SHALL NOT withdraw a
measure; it SHALL be recorded on the evidence as the coverage gap the
descriptor says it stands for. A warning SHALL be matched only against the
expected warnings of the descriptor of the model that reported it.

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

#### Scenario: A warning is expected only by its own model's descriptor

- **WHEN** the sensor's model reports a warning that the platform's descriptor
  lists as expected and the sensor's descriptor does not
- **THEN** every measure over the sensor's events has no value
- **AND** a warning only the sensor's descriptor expects, reported by the
  platform's I2C controller, withdraws the measures over the bus

### Requirement: Emulation Runs Are Deterministic And Identified

The evidence of every run SHALL record the emulator's version and build, the
firmware digest, the plan hash, the seed, and the digest of every file the run
was given. Repeated runs of one plan on one emulator build SHALL produce
byte-identical event records; a run that cannot SHALL report the difference
rather than choose one record. A run SHALL leave its bundle, its event record,
the emulator's log and its outcome in the workspace it is given, whatever
directory the emulator itself ran from, so that a run whose evidence is
committed keeps them beside it. No file of a run's bundle, and nothing else
its job's hash covers, SHALL carry the hash of the snapshot the job was
prepared against: the job names that snapshot beside its identity, so a change
to anything the run does not read leaves the job, and a measurement of it
current, as it was.

#### Scenario: Ten runs give one record

- **WHEN** the demo's startup plan is run ten times on one emulator build
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
nothing. It SHALL NOT change a workspace. It SHALL exit non-zero when a
question is not runnable or a run did not complete, and an emulator that is
not installed SHALL NOT by itself make it fail.

#### Scenario: A bundle is written without an emulator

- **WHEN** `fang emulate --bundle-only` runs on the demo board
- **THEN** it writes the plan, the platform description, the script, the probes
  and the manifest, and runs nothing

#### Scenario: Emulate prints what it measured

- **WHEN** `fang emulate` runs on the demo board with the emulator installed
- **THEN** it prints each question's measures and leaves any workspace
  untouched

#### Scenario: A run that does not complete fails the command

- **WHEN** `fang emulate` runs a question and the run ends on a timeout or a
  crash
- **THEN** it prints how the run ended and that its measures have no value,
  and exits non-zero

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
