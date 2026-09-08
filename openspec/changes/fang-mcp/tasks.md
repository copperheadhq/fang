# Tasks: The Agent Surface

## 1. Packaging and diagnostics

- [x] 1.1 Add the `mcp` optional extra to `pyproject.toml` with a pinned floor
      version; verify `pip install -e ".[mcp]"` resolves and `pip install -e .`
      still installs nothing beyond the standard library.
- [x] 1.2 Verify the SDK's actual server bindings against the installed package
      — server construction, tool and resource registration, structured output,
      and error reporting — and record what was found before writing against it.
- [x] 1.3 Add the `MCP` area to `diagnostics.AREAS` and allocate its codes with
      `_allocate`: path outside the project root, unknown tool, malformed
      argument, commit of an unaccepted proposal, missing dependency; verify
      `test_diagnostics`-style registry assertions still pass and no code was
      reused.

## 2. The projection layer

- [x] 2.1 Add `fang/mcp.py` with the kernel-facing half: plain functions from a
      snapshot to canonical-JSON-ready dictionaries, importing nothing from the
      SDK. Verify by importing the module with `mcp` uninstalled.
- [x] 2.2 Project the snapshot, entity reads, and the manifest, each response
      naming the snapshot hash it was computed against; verify against the
      conftest fixture slice.
- [x] 2.3 Project the netlist, the check results, and the required views
      including each view's notes; verify a view response carries the same nodes,
      edges, and notes as `views.view()` produced.
- [x] 2.4 Project all six rationale queries from `queries.py`; verify the
      causing-requirement answer is the recorded chain for the fixture's
      regulator.
- [x] 2.5 Serialize every response through `serialization.canonical_bytes`;
      verify two calls against unchanged state are byte-identical and that a
      quantity's magnitude crosses as a decimal string.
- [x] 2.6 Verify byte-identity across processes started with differing
      `PYTHONHASHSEED`, the way `tests/test_serialization.py` already does.

## 3. Undecided and unknown across the boundary

- [x] 3.1 Render `CheckStatus.UNKNOWN` as a third status distinct from pass and
      failure; verify an undecided check reaches the client as undecided.
- [x] 3.2 Render an explicitly unknown value distinguishably from an absent one;
      verify a set-but-unknown parameter and a never-set parameter differ in the
      response.
- [x] 3.3 Render a `ConflictingValue` with every candidate and its source;
      verify no candidate is selected in the projection.

## 4. The mutation path

- [x] 4.1 Implement the `propose` tool over `KernelGraph.propose`, accepting the
      operation kinds the gate evaluates that are constructible from a document
      — `remove_entity`, `connect`, and `set_parameter`; verify an unrecognized
      operation kind is refused with a code rather than applied, and that
      `add_entity` is refused with a diagnostic naming why (see the note below).
- [x] 4.2 Return the whole `Proposal` — acceptance, diagnostics, and diff — on
      rejection as well as acceptance; verify a rejected transaction returns its
      diff and leaves the head unchanged.
- [x] 4.3 Verify a proposal against a stale base is rejected with
      `TXN_STALE_SNAPSHOT` and applies no operation.
- [x] 4.4 Verify a transaction leaving a must-be-decided requirement undecided is
      rejected, and the response names the undecided result.
- [x] 4.5 Implement the `commit` tool over `KernelGraph.commit`, taking a handle
      from `propose`; verify committing an unaccepted proposal is refused with an
      `MCP` code and the head does not advance.
- [x] 4.6 Carry the project's active `Policy` into every proposal and construct
      no more permissive one; verify a transaction reserved for human approval is
      withheld by the gate and the response names the approval required.
- [x] 4.7 Name the revision the head moved to in every successful commit
      response; verify the head's movement is never silent.
- [x] 4.8 Verify `KernelGraph.apply()` is not reachable from any exposed tool.

## 5. Session binding and containment

- [x] 5.1 Bind a session to one project root given as a server argument, with the
      client unable to name a path; verify a request naming a program outside the
      root is refused with an `MCP` code and nothing outside the root is read.
- [x] 5.2 Elaborate the bound program on demand under `fang.sandbox`; verify a
      network reach during elaboration is reported as a violation rather than
      served, and that secrets in the surrounding environment are unreachable.
- [x] 5.3 Read `.copperhead/` where a workspace exists, falling back to the
      elaborated program; verify both paths answer with the same entity set for
      an unchanged program.
- [x] 5.4 Cache elaboration per session on the program's content hash; verify a
      second read-only request does not re-execute the program.
- [x] 5.5 Scope and paginate entity reads; verify the whole snapshot is served
      only when asked for deliberately.
- [x] 5.6 Verify a program that fails to elaborate yields every diagnostic with
      its code and source location, and no snapshot.

## 6. The transport layer and the command

- [x] 6.1 Add the SDK registration layer — the only place importing `mcp` —
      registering each projection as a tool or resource over stdio; verify an
      unknown tool and a malformed argument are refused with `MCP` codes.
- [x] 6.2 Add the `fang mcp` subcommand binding a program and serving over
      stdio; verify it appears in `fang --help` and exits non-zero on a usage
      error.
- [x] 6.3 Report the missing extra and exit non-zero when `mcp` is not
      installed, without starting a degraded server; verify with a test that
      asserts the message rather than skipping.

## 7. Closing out

- [x] 7.1 Add `tests/test_mcp.py` covering every scenario in this change's delta
      spec; verify the whole suite passes with and without the `mcp` extra
      installed.
- [x] 7.2 Add the module docstring quoting the requirement it implements by
      name, matching the convention in the rest of `fang/`.
- [x] 7.3 Update `CLAUDE.md`, `README.md`, and `MANIFEST.in` for the new module,
      the new extra, and anything the suite reads; verify `python -m pytest`
      passes from inside an unpacked sdist.


## Note on `add_entity`

The gate evaluates four operation kinds. Three are exposed. `add_entity` is
refused with `MCP-0006` carrying its reason, because building a typed entity
from a document means minting identity, provenance, and a source location, and
the kernel has no rehydration registry to mint them with — `Workspace.read_snapshot`
records the same absence. Closing it is a separate change: it needs the registry
(which would also let a workspace rebuild typed entities) and a requirement
covering how an agent-authored entity acquires its identity and provenance.
Until then an agent adds entities by authoring them in the Fang program and
calling `reload`.
