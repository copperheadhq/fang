# fang-kernel Specification

## ADDED Requirements

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
