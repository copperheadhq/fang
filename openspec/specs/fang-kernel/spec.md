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
schema_version: 1.1
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

A link is one interface connection together with the ports that participate in
it. A port is a party to the link when its interface declares at least one
electrical parameter; a port whose interface declares none — a passive pad, a
test point — is a wire on the link rather than a party to it. A link SHALL
continue through a part that declares it bridges the terminals in the path,
and SHALL stop at a part that declares no such bridge. A link over a bus SHALL
merge every connection whose ports share a member into one link, so every
port on the bus is a party to the same link rather than to a separate one per
connection.

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

Interface compatibility SHALL be a deterministic check class, run only over the
parameters every party to the link declares. The kernel SHALL evaluate at
least: source VOH(min) against sink VIH(min) plus margin; source VOL(max)
against sink VIL(max) less margin; source current capability against sink
demand; bus voltage domain compatibility across every party; pull-up supply
validity for every party; open-drain and open-collector requirements; and
protocol, rate, and addressing compatibility.

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
affected entities. A policy narrows or widens that set but never removes the
structural check.

#### Scenario: Downstream artifacts are materialized only after commit

- **WHEN** a transaction has not yet committed
- **THEN** no change is materialized into a CAD file or any other downstream
  artifact
- **AND** external checks such as CAD rule checking have not been run

#### Scenario: External rule-check results are ingested as evidence after commit

- **WHEN** a transaction commits and an external rule check subsequently runs
- **THEN** its results are ingested as evidence
- **AND** they were not consulted before the gate

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
its own. Every digital interface SHALL declare a voltage-domain parameter,
which the bus voltage-domain check depends on for that family.

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
voltage-domain agreement, pull-up supply validity, open-drain requirements, and
protocol, rate, and addressing agreement, over the parameters every party to
the link declares. A check whose inputs are unknown SHALL return undecided
naming the missing input. A link with fewer than two parties has nothing to
compare and yields no result.

#### Scenario: A logic-level shortfall fails

- **WHEN** a source's VOH minimum is below the sink's VIH minimum plus margin
- **THEN** the check fails and names both parameters

#### Scenario: An unknown input returns undecided naming what is missing

- **WHEN** a sink's VIH minimum is unknown
- **THEN** the check returns undecided and names `vih_min` as the missing input
- **AND** it does not pass by default

#### Scenario: A bus checks every party

- **WHEN** three parties share a bus and one is in a different voltage domain
- **THEN** the check reports the mismatch and names the party

#### Scenario: An open-drain bus without a pull-up fails

- **WHEN** an open-drain interface has no pull-up declared on the bus
- **THEN** the check fails naming the missing pull-up

#### Scenario: A datasheet-sourced input cites its evidence

- **WHEN** a compatibility input came from a datasheet
- **THEN** the result cites the evidence entity that supplied it

#### Scenario: A non-party is not asked for a fact it doesn't declare

- **WHEN** a resistor pad sits on a link whose other end declares logic
  levels and a voltage domain
- **THEN** the resistor is not asked for those parameters, because its
  interface declares none
- **AND** the link has only one party, so the check yields no result at all

#### Scenario: A series part joins the two interfaces it stands between

- **WHEN** two ports of the same interface type are joined only through parts
  that each declare they bridge the terminals in the path
- **THEN** the two ports are treated as the two ends of one link
- **AND** they are compared with each other, not with the parts between them

#### Scenario: A mismatch carries through a series part

- **WHEN** the two ends of a series-bridged link disagree on a checked
  parameter, such as their voltage domain
- **THEN** the check reports the mismatch between the two ends
- **AND** the parts bridging the path between them are not asked about it

#### Scenario: A part that declares no bridge ends the link

- **WHEN** two ports of the same interface type are joined only through a
  part that declares no bridge between the terminals in the path, such as a
  transistor
- **THEN** the interface does not continue through that part
- **AND** the two ports are not treated as ends of one link

### Requirement: The Part Model

A part SHALL separate its logical identity, its selected vendor part, its
package, its sourcing identity, its parameterization, and its physical instance.
A part SHALL declare a designator prefix, and a generic part SHALL carry no
vendor identity until one is selected. A part SHALL declare which pairs of its
own terminals it bridges — conducts between — if any; nothing else in the
graph records conduction through a part's own body.

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

#### Scenario: A part records what it bridges

- **WHEN** a two-terminal part such as a resistor is declared
- **THEN** the component entity records that its two terminals are bridged
- **AND** a part such as a transistor or a connector that declares no bridge
  records none

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
