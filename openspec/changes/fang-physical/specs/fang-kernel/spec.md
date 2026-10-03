# fang-kernel Specification

## ADDED Requirements

### Requirement: The Physical Entity Model

The kernel SHALL hold physical entities in the one graph: board, stackup, layer,
placement, pad, via, trace, zone, and region. Each SHALL carry stable identity,
provenance, and a source location or an import origin, SHALL declare the
identifiers it requires to exist, and SHALL serialize canonically like every
other entity.

A physical entity SHALL name the upper-layer entity it realizes where one
exists: a trace names its net, a placement names its component, a pad names its
pin. It SHALL NOT restate a fact the entity it realizes already carries.
Identity SHALL NOT be derived from geometry, so moving a footprint SHALL NOT
change any identifier.

Where a physical order carries meaning, serialization SHALL preserve it rather
than sorting it. A stackup's layers are ordered top to bottom.

#### Scenario: A physical entity names what it realizes

- **WHEN** a trace is added to the graph
- **THEN** it names the net whose copper it is
- **AND** it does not restate that net's domain, aliases, or members

#### Scenario: Moving a part does not change its identity

- **WHEN** a placement's position changes and nothing else does
- **THEN** every identifier in the graph is unchanged
- **AND** the change is classified as physical, not electrical

#### Scenario: A stackup's layer order is semantic

- **WHEN** a stackup is serialized
- **THEN** its layers appear top to bottom in the order the stackup declares
- **AND** they are not reordered into sorted order

#### Scenario: A physical entity with no upper-layer parent is still traceable

- **WHEN** a board element is imported that realizes nothing in the layers above
- **THEN** it is recorded with its import origin
- **AND** it is not silently dropped and not invented an owner

### Requirement: The Physical Layer Is Compiled, Never Authoritative

A board SHALL be a realization: a compiled projection naming the committed
snapshot it was produced from. Producing or importing one SHALL NOT mutate
semantic state as a side effect. The physical layer SHALL NOT be a peer source
of truth for a fact the layers above it already hold; where the two disagree,
the semantic layer governs and the disagreement SHALL be reported rather than
resolved silently.

The kernel SHALL NOT place components, SHALL NOT route copper, and SHALL NOT
compute a trace geometry of its own. It states the intent, projects it to the
tool that does the work, and reads the result back.

#### Scenario: A board names the snapshot it was compiled from

- **WHEN** a board realization is materialized
- **THEN** it names the committed snapshot it was compiled from
- **AND** materializing it against any other snapshot is refused

#### Scenario: A routed board disagreeing with the netlist is reported

- **WHEN** an ingested board joins two pins the committed netlist does not
- **THEN** the disagreement is reported as a finding against the board
- **AND** the netlist is not rewritten to match the copper

#### Scenario: A pin swap chosen during layout returns through the gate

- **WHEN** an ingested board reflects a pin swap the router chose
- **THEN** the swap is offered as a transaction the gate evaluates
- **AND** the ingest itself changed no semantic state

#### Scenario: The kernel constructs no layout engine

- **WHEN** a program declares its board, its stackup, and its routing rules
- **THEN** no placer, router, or field solver is constructed during elaboration
- **AND** the declarations are recorded as entities and constraints

### Requirement: Physical Attributes Resolve Through The Entity They Realize

A routing or placement constraint SHALL target the semantic entity it is about,
and a reference to a physical attribute of that entity SHALL resolve over the
physical entities realizing it. Where several physical entities realize one
semantic entity, the reference SHALL resolve to the interval they span rather
than to any single one of them, so a rule holds over the whole realization.

A reference to a physical attribute of an entity that nothing realizes SHALL
resolve unknown. Such a constraint is undecided, and undecided SHALL NOT be
reported as a pass.

#### Scenario: A width rule holds over every segment of a net

- **WHEN** a net is routed as several trace segments and a rule requires a
  minimum width of 0.5 mm
- **THEN** the reference resolves to the interval the segments span
- **AND** the rule fails if any one segment is narrower than 0.5 mm

#### Scenario: An unrouted net leaves its routing rule undecided

- **WHEN** a routing rule targets a net that no trace realizes
- **THEN** the rule evaluates undecided
- **AND** it is reported as undecided rather than as satisfied

#### Scenario: A physical reference is dimensionally checked at write time

- **WHEN** a routing constraint compares a width to a quantity that is not a
  length
- **THEN** constructing the expression is refused with the dimension diagnostic
- **AND** the constraint is never stored

### Requirement: Routing And Placement Constraints Are Checked By The Gate

Routing, placement, and manufacturing constraints SHALL be classes within the
one constraint registry and SHALL be evaluated by a check class the commit gate
can require. There SHALL be no second constraint store for design rules.

The check class's scope SHALL be the entities its constraints target, so absent
a project policy the gate requires it exactly when a transaction touches them. A
hard routing constraint that fails SHALL block the commit; an advisory one SHALL
be reported and SHALL NOT block. Whether an undecided routing result blocks SHALL
remain the gate's policy decision, not the evaluator's.

#### Scenario: A failing hard width rule blocks the commit

- **WHEN** a transaction leaves a hard minimum-width rule failing
- **THEN** the gate rejects the proposal
- **AND** the rejection carries the failing rule's identifier and its diff

#### Scenario: An advisory rule reports without blocking

- **WHEN** an advisory placement rule fails
- **THEN** the result is reported against the proposal
- **AND** the commit is not blocked by it

#### Scenario: The routing check is required only when it is touched

- **WHEN** a transaction changes nothing a routing constraint targets
- **THEN** the routing check class is not in the required set for it

#### Scenario: An external rule check re-enters as evidence

- **WHEN** a CAD design-rule check runs against the committed head and returns
  results
- **THEN** the results enter as evidence through an ordinary transaction
- **AND** results produced against anything but the committed head are refused

### Requirement: Physical Intent Is Authored In The Program

A Fang program SHALL be able to declare its board and its stackup, and to record
a constraint in a class other than electrical. A recorded constraint SHALL carry
the class it was declared in, so a routing rule is a routing rule in the graph
and not an electrical one.

Declaring physical intent SHALL follow the existing declaration rules: it is
recorded rather than evaluated, it carries the source location that produced it,
and elaborating the same program twice SHALL produce identical entities.

#### Scenario: A program declares a routing rule

- **WHEN** a program requires a minimum trace width on a rail
- **THEN** a constraint of class `routing` is recorded against that rail
- **AND** no width is evaluated at declaration time

#### Scenario: A declared stackup becomes an entity

- **WHEN** a program declares a four-layer stackup with 1 oz outer copper
- **THEN** a stackup entity is recorded with its layers in order
- **AND** each layer names its copper weight as a quantity, never a bare number

#### Scenario: The declared class survives into the record

- **WHEN** a routing constraint is serialized
- **THEN** its `class` field reads `routing`
- **AND** it carries the same schema as every other constraint

### Requirement: Emitted Design Rules Are Projections

A design-rule file or net class assignment emitted for a layout tool SHALL be a
generated projection of the constraint registry. It SHALL carry the identifier
of the record it projects, SHALL NOT restate a field the constraint record
already defines, and MAY add class-specific fields such as a layer or a net
class name. It SHALL NOT be a place an engineering fact can be recorded.

Emission SHALL be deterministic: the same snapshot emits byte-identical rules.

#### Scenario: An emitted rule carries the identity of what it projects

- **WHEN** a design-rule file is emitted for a layout tool
- **THEN** each rule in it names the constraint identifier it projects
- **AND** it adds only class-specific fields the constraint does not define

#### Scenario: A rule edited in the layout tool is not a source of truth

- **WHEN** an emitted rule file is edited outside the kernel and re-read
- **THEN** the edit is reported as a difference from the registry
- **AND** it is not adopted as the engineering fact

#### Scenario: Emission is byte-identical for the same snapshot

- **WHEN** rules are emitted twice from one committed snapshot
- **THEN** the two emissions are byte-identical

### Requirement: Board Import Reports What It Could Not Represent

Reading an external board file SHALL record every external identifier in the
mapping table alongside the canonical identity, and SHALL report every construct
the adapter could not represent rather than discarding it silently. A board
element the kernel has no entity for SHALL be reported as unrepresented and
SHALL NOT be approximated by an entity that means something else.

#### Scenario: An unrepresentable board construct is reported

- **WHEN** a board file carries a construct the physical entity model has no
  place for
- **THEN** the import reports it as unrepresented with its location
- **AND** it is not mapped onto an entity that means something else

#### Scenario: A board's external identifiers are mapped, never adopted

- **WHEN** a board file's elements carry the layout tool's own identifiers
- **THEN** each is recorded in the mapping table against a derived identity
- **AND** no external identifier becomes a canonical identifier
