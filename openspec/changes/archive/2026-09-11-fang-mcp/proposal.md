# The Agent Surface

## Why

The spec already binds the agent: a conforming system mutates canonical state
"only through transactions passing the commit gate by every mutation path
including the agent's". No such path exists. An agent working on a Fang project
today has to shell out to `fang` and scrape its text, which throws away exactly
what the kernel is for — the diagnostics, the diff, the undecided results, and
the identity that ties them together — and leaves it holding formatted prose
where the kernel had structure.

The gate's most useful output is a rejection that explains itself. An agent is
the consumer that most needs that explanation, and is currently the one least
able to read it.

## What Changes

- Add `fang.mcp`: a Model Context Protocol server over the kernel, exposing the
  committed snapshot, the netlist, the checks, the views, and the rationale
  queries as tools and resources, and served by a new `fang mcp` command.
- Add the mutation path. A `propose` tool takes transaction operations and
  returns the whole `Proposal` — accepted or rejected, with its diagnostics and
  its diff — and a `commit` tool advances the head. Both go through
  `KernelGraph.propose` and `KernelGraph.commit`; the server adds no route
  around the gate and no operation the gate does not already know.
- A session binds to one project. A Fang program is elaborated on demand under
  the existing sandbox; a workspace is read from `.copperhead/` where one
  exists. The server never executes a program the client names outside the
  project root it was started against.
- Every tool result is canonical JSON, so an agent reading the same state twice
  reads identical bytes and a transcript is comparable across runs.
- Add the `MCP` diagnostic area, so a refusal at the protocol boundary carries a
  code like everything else in the kernel.
- Add an `mcp` optional extra depending on the `mcp` SDK. The project's runtime
  `dependencies` stay empty; `fang mcp` reports what is missing and exits
  non-zero when the extra is not installed, the way `fang sim` does for ngspice.

## Capabilities

### New Capabilities

None. The spec is the whole contract and is self-contained; the agent surface
belongs in it rather than beside it.

### Modified Capabilities

- `fang-kernel` — adds the agent surface's contract: what it exposes, that its
  mutation path is the same gate, that its results are deterministic, and what
  it refuses.

## Impact

- New module `fang/mcp.py` and its tests; a new `mcp` subcommand in `fang/cli.py`.
- `fang/diagnostics.py` gains the `MCP` area and its codes.
- `pyproject.toml` gains one optional extra. This is the project's first runtime
  dependency of any kind, and it stays optional — the core install remains
  standard library only.
- Extends the trust boundary the spec already draws: the server executes Python
  during elaboration and can now advance the head unattended, so both are held
  to the sandbox and the gate rather than to the client's good behaviour.
