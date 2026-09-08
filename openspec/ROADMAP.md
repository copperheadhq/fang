# Fang delivery roadmap

**All eleven stages are delivered.** The suite is green and every acceptance
criterion in the combined spec is demonstrated rather than deferred.

The full code-defined electronics toolchain, chunked into stages. Each stage is
an OpenSpec change with its own proposal, delta spec, and tasks. Every stage
ships working code and tests; nothing is a placeholder.

The ordering is a product ordering, not the spec's evidence ordering: the first
five stages together are the vertical slice from a Fang program to a KiCad
netlist a person can open.

| # | Change | Delivers |
| --- | --- | --- |
| 1 | ✅ `fang-kernel-core` | Entity model, identity, units, values, constraints, transactions, commit gate, serialization, diff, topology |
| 2 | ✅ `fang-language` | The authoring surface: `Module`, `System`, parameters, traits, `require()`, the connect operator, deterministic elaboration, diagnostics |
| 3 | ✅ `fang-interfaces` | Interface catalogue, ports, buses, deterministic pin lowering, compatibility checks with undecided results |
| 4 | ✅ `fang-parts` | Part model: pins, packages, footprints, part traits, sourcing, and a standard library of generic parts |
| 5 | ✅ `fang-netlist` | Net inference from connectivity, designator assignment, netlist IR, KiCad netlist emission |
| 6 | ✅ `fang-cad` | KiCad s-expression reader and writer, project import, the canonical mapping table, lossy-operation reporting, one safe round trip |
| 7 | ✅ `fang-toolplan` | Tool plan emission, handles as symbolic conditions, the tool contract, the operation phase, realizations |
| 8 | ✅ `fang-views` | View compiler, the six required views, the layout boundary, SVG rendering, stable placement seeds |
| 9 | ✅ `fang-simulation` | Simulation models as traits, plans, SPICE lowering, the ngspice backend, result normalization |
| 10 | ✅ `fang-rationale` | Requirement, evidence, decision, and calculation authoring from Fang; the verification graph; impact propagation |
| 11 | ✅ `fang-cli` | The workspace (`.copperhead/`), the manifest, and `fang build`, `check`, `view`, `sim`, `export` |

## The vertical slice

Stages 1 to 6 close the loop that makes the toolchain real:

```
Fang program -> elaboration -> kernel graph -> transaction gate
    -> snapshot -> netlist compiler -> KiCad netlist -> a board file
```

with import running the same path backwards into the same model.

## Invariants every stage holds

These come from the combined spec and are not renegotiated per stage:

- One canonical model. No stage introduces a second persisted representation.
- Deterministic output. Identical inputs give byte-identical snapshots.
- Unknown is representable; undecided is a third truth value.
- Every mutation is a transaction through the one gate.
- Every entity carries identity, provenance, and a source location.
