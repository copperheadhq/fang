# Tasks: Fang Language Surface

## 1. Declaration model

- [x] 1.1 Implement the module metaclass collecting declarations in class-body order.
- [x] 1.2 Implement per-instance materialization so two instances never share a child.
- [x] 1.3 Implement `System` as the root module and canonical path assignment.
- [x] 1.4 Capture the source location of every declaration at declaration time.

## 2. Parameters and units

- [x] 2.1 Implement `Parameter(unit, ...)` with a declared dimension.
- [x] 2.2 Implement the unit literals so `3.3 * V` builds a decimal quantity.
- [x] 2.3 Implement `ParameterRef` with comparison operators building expression nodes.
- [x] 2.4 Record an unassigned parameter as `unknown` rather than defaulting it.
- [x] 2.5 Reject a dimensionally wrong assignment with a `UNIT` diagnostic.
- [x] 2.6 Support range and tolerance literals.

## 3. Constraints

- [x] 3.1 Implement `require()` recording a constraint against the declaring module.
- [x] 3.2 Ensure no truth value is computed at declaration time.

## 4. Connectivity

- [x] 4.1 Implement `Electrical` and the surface kinds the connect operator accepts.
- [x] 4.2 Implement the connect operator recording a typed connection with provenance.
- [x] 4.3 Refuse a connection between surfaces whose kinds cannot connect.

## 5. Traits

- [x] 5.1 Implement the trait protocol and registration on entities.
- [x] 5.2 Implement enumeration by protocol with no backend instantiated.

## 6. Tool plan

- [x] 6.1 Implement plan emission naming the snapshot, the ordered calls, and the source map.
- [x] 6.2 Implement handles whose attributes are symbolic conditions.
- [x] 6.3 Make reading a handle during elaboration an `ELAB` error.

## 7. Sandbox

- [x] 7.1 Deny network access outright during elaboration.
- [x] 7.2 Make an undeclared file input unavailable.
- [x] 7.3 Hash every declared input into the snapshot.
- [x] 7.4 Require a declared seed for randomness and record it.

## 8. Elaboration

- [x] 8.1 Implement the elaborator returning a snapshot, a plan, and diagnostics.
- [x] 8.2 Produce no partial graph on failure.
- [x] 8.3 Prove re-elaboration of unchanged source is byte-identical.
- [x] 8.4 Feed the result through the existing transaction gate unchanged.

## 9. Tests

- [x] 9.1 Cover every scenario in this change's delta spec.
- [x] 9.2 Add an end-to-end test elaborating a small system into a committed graph.
