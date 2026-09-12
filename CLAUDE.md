# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Fang is the Copperhead hardware kernel plus the Python-embedded language that authors hardware
for it. The kernel elaborates a Fang program into the Engineering Intermediate Representation
(EIR), holds it as a live typed graph, mutates it only through validated
transactions, and lowers it into downstream artifacts.

Pure Python 3.11+, standard library only. NetworkX is an optional extra used for graph *analysis*
only — it is never a persisted or public representation.

## Commands

```bash
pip install -e ".[dev]"          # add ",analysis" for the NetworkX-backed queries
python -m pytest                 # whole suite (504 tests, ~10s); addopts = -q, testpaths = tests
fang build examples/sensor_board/sensor_board.py   # the console script, after an editable install
python -m pytest -rs             # also lists the acceptance tests deferred to later phases
python -m pytest tests/test_graph.py::test_name -x
python -m pytest -k "at_k7"      # acceptance criteria are named test_at_r*/test_at_k*
openspec list                    # OpenSpec CLI (v1.12) drives the change workflow
python -m build                  # dist/*.whl and dist/*.tar.gz; twine check --strict them
```

There is no linter or formatter configured; match the surrounding style.

## Packaging

The distribution is **`copperhead-fang`** on PyPI (the bare name `fang` is taken
by an unrelated package); the import name stays `fang`. The version has one
source of truth, `fang.__version__`, which `pyproject.toml` reads dynamically
and the release workflow checks against the git tag — never write a version
literal anywhere else. `SCHEMA_VERSION` beside it is the serialized-EIR version
and moves independently. The sdist ships the tests, the examples they read, and
the spec, so `python -m pytest` runs from inside an unpacked sdist; keep
[MANIFEST.in](MANIFEST.in) in step when adding anything the suite reads.
[RELEASING.md](RELEASING.md) is the release procedure.

## The governing invariant

There is exactly one canonical model, the EIR. The kernel graph is its live realization;
everything else is a lowering of it, a projection of it, or an interchange encoding of it.
**Never introduce a second persisted representation of the same facts.** `ConstraintRegistry`
enforces this literally: constructing a second registry for a project raises `ELAB-0012`;
downstream tools get a generated `Projection`, never their own store.

Four further invariants the tests hold, and which any change must preserve:

- **Determinism.** Identical inputs give byte-identical snapshots. Verified across processes
  with differing `PYTHONHASHSEED` (see [tests/test_serialization.py:102](tests/test_serialization.py#L102)).
  Magnitudes are `Decimal` strings under a fixed `Context(prec=34)`, never binary floats;
  serialization sorts by Unicode code point except for the collections in
  `serialization.ORDERED_COLLECTIONS`, whose order is semantic.
- **Explicit unknowns.** `null` never means "unknown". `Value.unknown()` is a distinct status.
- **Undecided is a third truth value** (`Truth.UNKNOWN` / `CheckStatus.UNKNOWN`). An unknown
  operand makes a check undecided; it is never silently a pass or a failure. Whether undecided
  *blocks* is the gate's policy decision, made in `KernelGraph.propose`, not by the evaluator.
- **Dimensional rejection at write time.** `Arithmetic.__post_init__` checks dimensions when the
  expression is constructed, so a dimensionally invalid expression cannot be stored, let alone
  evaluated. Type and unit correctness therefore never needs re-checking in `validation.validate`.

## Architecture

The dependency order is roughly the order below; lower layers never import higher ones.

**Foundations.** [fang/units.py](fang/units.py) is dimension vectors over the seven SI bases,
unit algebra, and `Quantity` (scalar, range, or tolerance, with a decimal magnitude).
[fang/values.py](fang/values.py) wraps a quantity in a status — explicit, inferred, assumed, or
unknown — and models unresolved `ConflictingValue` candidates. [fang/identity.py](fang/identity.py)
derives identifiers as UUIDv5 over `(project namespace, "<kind>:<canonical semantic path>")`,
rendered as a prefix plus 12 hex digits, lengthened 4 digits at a time only against the revision's
existing identifier set — so re-derivation reproduces the same lengths. The three origins are
`derive()`, `authored()`, `imported()`. [fang/provenance.py](fang/provenance.py) is append-only.

**The entity model.** [fang/entities.py](fang/entities.py) holds `Entity` and its subclasses
(Component, Net/Rail, Connection, Interface/Port/Bus, Domain, Requirement, Decision, Evidence,
Model). Every entity is a frozen dataclass carrying identity, parameters, provenance, and a source
location, and exposes two protocol methods the rest of the kernel relies on:
`references()` (drives referential integrity, diff impact, and topology adjacency) and `as_dict()`
(drives canonical serialization). **A new entity kind must implement both**, and be registered in
`identity.PREFIXES` and in `graph._COLLECTION_OF`.

**Constraints.** [fang/constraints.py](fang/constraints.py) is the single registry plus a typed
expression tree (`Literal`, `Ref`, `Arithmetic`, `Comparison`, `Logical`) evaluated over
`Interval` arithmetic against a `Resolver` supplied by a snapshot. A `Ref` to an unknown value
yields `Truth.UNKNOWN`, which propagates through Kleene three-valued `and`/`or`/`not`.
[fang/topology.py](fang/topology.py) adds `TopologyConstraint` over enumerated conductive paths.

**The graph and the gate.** [fang/graph.py](fang/graph.py) is the centre of the system.
`Snapshot` is immutable and content-hashed. `Transaction` names the base snapshot it was built
against and carries `Operation`s (`AddEntity`, `RemoveEntity`, `Connect`, `SetParameter`).
`KernelGraph.propose()` applies the transaction **to a copy** and runs six gate conditions in
order: stale-base rejection, normalization into well-formed entities, structural validation,
every required `CheckClass` has run, no blocking check result, no undecided result over a
must-be-decided requirement, and policy approvals satisfied. Only `commit()` advances the head.
Rejection is correct by construction — the candidate is simply discarded — and a rejected
`Proposal` still returns its diagnostics and its diff, because the explanation is the useful
output of a rejection.

Two ordering rules the gate encodes and that new code must not invert:
`materialize()` refuses a `Realization` whose parent is not the committed snapshot, and
`ingest_external_results()` refuses results produced against anything but the committed head —
external check results re-enter as `Evidence` through an ordinary transaction.

**Above the graph.** [fang/validation.py](fang/validation.py) checks identifier uniqueness,
referential integrity, provenance traceability, prohibited cycles, contradictory mandatory
constraints, and the requirement state machine. [fang/diff.py](fang/diff.py) classifies each
change as electrical or presentation-only and propagates invalidation.
[fang/queries.py](fang/queries.py) answers rationale questions on demand.
[fang/serialization.py](fang/serialization.py) is canonical JSON and the record stream.
[fang/diagnostics.py](fang/diagnostics.py) is a code registry over the areas
`ELAB IFACE TOPO UNIT TXN SIM IMPORT`; **codes are allocated, never reused, and retired rather
than deleted** — add new ones via `_allocate` at the bottom of the relevant area block.

## The spec is the contract

The working contract is [openspec/specs/fang-kernel/spec.md](openspec/specs/fang-kernel/spec.md),
a self-contained normative document: terminology, design principles, layers of representation,
kernel architecture, and the project root, then 81 requirements over 222 scenarios and 23
acceptance tests. There is no other standards document in this repository — the spec is the whole
contract. Read the relevant requirement before changing kernel behaviour. Module docstrings quote
the requirement they implement by name (e.g. `Spec: "The Commit Gate"`) — keep that link intact.

[tests/test_acceptance.py](tests/test_acceptance.py) holds exactly one test per acceptance
criterion, AT-R1..AT-R13 and AT-K1..AT-K10, and all 23 pass. The only skips in the suite are for
optional binaries that may not be installed (NetworkX, ngspice); each names what is missing. If a
criterion ever has to be deferred again, skip it with the reason named rather than weakening the
assertion, so the suite reports what is actually demonstrated.

Other tests share [tests/conftest.py](tests/conftest.py), whose fixtures build one small vertical
slice (regulator, controller, rail, ground domains). Its identifiers are *computed* with `derive`
rather than written down, so fixtures cannot drift from the derivation rules; time is pinned to
`FIXED_TIME`; and an autouse fixture releases the project's `ConstraintRegistry` after each test.
Tests import it as `from conftest import ...`.

## Examples are folders, and they carry their outputs

Every example under [examples/](examples/) is a folder: `<name>/<name>.py`, a
`README.md` explaining what it is for, and the files `fang` produces from it
under `out/` — the KiCad netlist, the netlist and check and graph listings, the
views worth looking at, and a `rationale.md` for the examples that record any
reasoning. `python examples/regenerate.py` rewrites them all;
[tests/test_examples.py](tests/test_examples.py) rebuilds them and compares, so
a committed output cannot drift from the program beside it. Two things in an
output are normalized before that comparison and only two: the compiler version
and the snapshot hash, which covers provenance and so covers this checkout's
absolute path. Add an example by adding the folder — the suite discovers it —
and give it a `README.md` and an `out/`, or it is not an example.

## Work is organized as OpenSpec changes

[openspec/ROADMAP.md](openspec/ROADMAP.md) chunks the toolchain into 11 stages, each an OpenSpec
change with a proposal, a delta spec, and tasks. All eleven are archived under
`openspec/changes/archive/<date>-<id>/`; a new stage starts with `/opsx:propose`. The ordering is a
product ordering: stages 1–6 close the loop from a Fang program to a KiCad netlist. **All eleven
stages are delivered**, and every acceptance criterion in the spec is demonstrated rather than
deferred. Every stage ships working code and tests — nothing is a placeholder.

Use the `/opsx:*` skills (propose, apply, update, sync, archive, explore) for that workflow rather
than editing `openspec/` artifacts ad hoc. `openspec/config.yaml` carries project context that
those skills read.

## The site and the brand

[site/](site/) holds the landing page for `fang.copperhead.sh` and the brand assets. It is one
self-contained `index.html` with no build step, serving `site/` as the document root.
[site/BRAND.md](site/BRAND.md) fixes the mark's geometry, the palette, and the voice; the palette
is copperhead's own, taken from `docs.copperhead.sh`, with two values nudged for contrast and the
reason recorded. Fang is a sub-brand of copperhead, so a change to the identity belongs upstream
in copperhead's system first.

RFC 2119 keywords in the spec and RFCs are normative.
