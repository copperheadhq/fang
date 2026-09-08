# Design: The Agent Surface

## Context

See [proposal.md](proposal.md) for motivation. The constraints that shape the
approach are all pre-existing:

- `KernelGraph.propose()` already runs the six gate conditions and already
  returns a `Proposal` carrying diagnostics and a diff whether it was accepted
  or rejected. Nothing about the gate needs to change for an agent to use it.
- `serialization.canonical_bytes` already produces deterministic JSON, and
  `Snapshot.as_dict()` and the `as_dict()` on every entity already define what
  the kernel's facts look like as data.
- `fang.sandbox` already enforces the elaboration boundary — sockets replaced,
  `open` filtered, seedless randomness refused.
- `queries.py` already answers the six rationale questions from graph structure.
- The project ships with `dependencies = []` and one optional extra,
  `analysis`, which is the precedent for how an optional dependency is added.

So the work is an adapter, not a new subsystem. The design question is where the
adapter's seams go.

## Goals / Non-Goals

**Goals:**

- One thin translation layer between the protocol and the kernel, with the
  kernel's semantics — undecided, unknown, provenance, the gate — surviving it
  unchanged.
- Determinism inherited from the existing serializer rather than re-derived.
- The trust boundary the spec already draws stays where it is, with the agent
  inside it rather than beside it.

**Non-Goals:**

- No remote or multi-tenant serving. A session is one local project.
- No new query, view, or check. The surface exposes what the kernel computes;
  if an answer is worth having and the kernel cannot produce it, that is a
  different change.
- No agent-side reasoning, planning, or repair. The server answers and gates; it
  does not decide.

## Decisions

### Depend on the `mcp` SDK, behind an optional extra

The protocol's framing, initialization handshake, and capability negotiation are
not this project's business, and they move. Owning a hand-written JSON-RPC
implementation would mean tracking a spec whose value to Fang is zero — the
value here is the kernel's semantics on the other side of the pipe.

*Alternative considered:* implement stdio JSON-RPC in the standard library. It
is a few hundred lines and would preserve the zero-dependency line exactly. It
was rejected because those lines are pure protocol maintenance, and every hour
spent on them is an hour not spent on what the surface actually exposes.

*The cost, stated plainly:* this is the project's first runtime dependency of
any kind, and it sits against the "standard library only" line in the project's
own description. It is mitigated, not eliminated, by keeping it an extra:
`dependencies` stays `[]`, `pip install copperhead-fang` is unchanged, the test
suite runs without it, and only `fang mcp` needs it. The `mcp` package requires
Python 3.10 or newer, comfortably under Fang's 3.11 floor.

The SDK's exact bindings are pinned against the installed version during
implementation rather than written from memory — the surface is
`mcp.server.MCPServer` with `@mcp.tool()` and `@mcp.resource()` decorators, but
the structured-output and error-reporting shapes are verified before use, not
assumed.

### The adapter never lets an SDK type reach the kernel

`fang/mcp.py` splits in two: a set of plain functions that take a snapshot and
return canonical-JSON-ready dictionaries, and a thin registration layer that
hands those functions to the SDK. The first half is what the tests exercise and
what the spec's scenarios are written against; the second half is small enough
to be replaceable if the SDK is ever dropped for a hand-rolled transport.

This is also what keeps `dependencies = []` honest: nothing outside the
registration layer imports `mcp`.

### The agent may commit, and the gate — not the server — is what bounds it

The agent surface exposes `propose` and `commit` as two tools, and an agent can
drive both without a human in the loop.

The reasoning is that the spec already names the mechanism for this. *Security
And Trust Boundaries* requires that "an automatic modification is bounded by the
scope and authority the active project policy grants, enforced at the commit
gate", and *Conformance Claims* requires the gate on "every mutation path
including the agent's". A propose-only server would have moved the safety story
out of the gate and into the adapter, which is exactly the wrong place for it —
it would make the adapter security-relevant and leave the gate's policy
condition untested by the one caller that most needs it.

*Consequence:* `Policy` becomes the real control surface for this feature. The
server SHALL construct no policy more permissive than the project's, and a
transaction reserved for human approval is withheld by the gate's approval
condition, not by a check in the adapter.

*Alternative considered:* propose-only, with commit left to the CLI. Safer in
the narrow sense, but it makes the agent's path structurally different from
every other mutation path, which is the thing the spec's wording rules out.

### Three operation kinds are constructible, and the fourth says why not

`remove_entity`, `connect`, and `set_parameter` are built from a document.
`add_entity` is not, and is refused with a code that states the reason rather
than a code that implies the gate does not know the operation.

The obstacle is real rather than incidental: an entity carries identity,
provenance, and a source location, and the kernel has no rehydration of a typed
entity from a document to mint them with — `Workspace.read_snapshot` records the
same absence for the same reason. Approximating it here would mean inventing
provenance for an entity an agent asserted, which is the one thing the
provenance requirement exists to prevent.

Closing it is a separate change: the rehydration registry, which would also let
a workspace rebuild typed entities, plus a requirement covering how an
agent-authored entity acquires its identity and provenance. Until then an agent
adds entities by authoring them in the program and calling `reload`.

### Two tools, not one — `apply()` stays unexposed

`KernelGraph.apply()` proposes and commits in one call. The surface does not
expose it. Splitting the two is what makes the explanation available *before*
the state moves, and what leaves room for a client-side approval step between
them. `propose` returns the whole `Proposal` — its acceptance, its diagnostics,
its diff, and a handle; `commit` takes that handle and refuses anything the gate
did not accept.

### The project root is a server argument; the client never names a path

`fang mcp <program>` binds the session. The program is elaborated on demand
under the existing sandbox, and `.copperhead/` is read where a workspace exists
— program-primary, matching how `fang build` already works.

Letting a client pass a path per call would turn the server into an arbitrary
Python executor for whoever holds the other end of the pipe. Refusing paths
outside the bound root is the whole of the containment story at this layer;
everything below it is the sandbox that already exists.

Elaboration is cached per session, keyed on the program's content hash, so a
sequence of read-only questions does not re-execute the program each time.

### Responses are the existing canonical serializer's output

Every tool returns a document built with `canonical_bytes`. Determinism is
inherited rather than re-implemented, which is what makes the byte-identity
scenarios in the delta spec testable the same way
[tests/test_serialization.py](../../../tests/test_serialization.py) already
tests the snapshot across hash seeds.

### A new `MCP` diagnostic area

Refusals at the protocol boundary — a path outside the root, an unknown tool, a
commit of an unaccepted proposal — are their own area. Codes are allocated,
never reused, so a new area is cheaper and clearer than stretching `TXN` over a
boundary it does not describe.

### stdio only

The session is bound to a local project root and a local workspace. A network
listener would widen the trust boundary the spec draws for no gain at this
stage. HTTP is a later question, not a deferred part of this one.

## Risks / Trade-offs

- **The SDK's API drifts and breaks `fang mcp`.** → The adapter is two layers;
  only the thin registration layer touches SDK types. Pin a floor version in the
  extra and verify the bindings against the installed package during
  implementation.
- **The first runtime dependency erodes the zero-dependency property.** → It is
  optional and unimported outside one layer. A test asserts the core imports
  cleanly with `mcp` absent, so the property is enforced rather than promised.
- **An agent advances the head in a way a human did not intend.** → The gate's
  policy condition is the control, and the server may not widen it. The response
  to a commit names the revision the head moved to, so the movement is never
  silent.
- **A large snapshot floods the agent's context.** → Entity reads are scoped and
  paginated; the whole snapshot is a resource an agent asks for deliberately,
  not the default payload of every answer.
- **The feature is simply absent in a default install.** → `fang mcp` names the
  missing extra and exits non-zero, the shape `fang sim` already uses for a
  missing ngspice. A test asserts that message rather than skipping quietly.
- **Canonical JSON is verbose where an agent would read prose more cheaply.** →
  Accepted. Determinism and the survival of undecided across the boundary are
  worth more than token count, and a lossy prose rendering is the failure mode
  the spec's "explicit unknowns" rule exists to prevent.

## Migration Plan

Additive. No existing behaviour changes, no serialized format moves, and
`SCHEMA_VERSION` is untouched. Rollback is not installing the extra.

## Open Questions

- Whether the surface should also expose simulation and KiCad export as tools,
  or leave both to the CLI. Deferrable: it adds tools without changing the
  approach, the containment story, or any requirement in the delta spec.
- Whether an HTTP transport is ever wanted, and what the trust boundary would
  have to become if it were.
