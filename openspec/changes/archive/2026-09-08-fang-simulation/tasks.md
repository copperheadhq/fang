# Tasks: Simulation As A Compiler Target

- [x] 1.1 Implement the analysis types: operating point, transient, DC sweep, AC.
- [x] 1.2 Implement the simulation scope and the plan it compiles into.
- [x] 1.3 Reject a plan whose component has no compatible model.
- [x] 1.4 Reject a plan whose pin map is incomplete.
- [x] 1.5 Allow an explicitly abstracted component and record the abstraction.
- [x] 1.6 Respect a model's distribution restriction by reference rather than inlining.
- [x] 1.7 Record deterministic options and a declared seed.
- [x] 2.1 Implement SPICE lowering emitting native netlist text.
- [x] 2.2 Prove lowering is deterministic.
- [x] 2.3 Keep backend syntax out of component definitions.
- [x] 3.1 Implement the ngspice backend across a process boundary.
- [x] 3.2 Report unsupported when the simulator is absent.
- [x] 3.3 Record the backend version with every result.
- [x] 4.1 Implement result normalization with plan, backend, models, assumptions,
      and coverage gaps.
- [x] 4.2 Reference sample data as an artifact rather than inlining it.
- [x] 4.3 Record a pass as a finding with a confidence, never as proof.
- [x] 5.1 Implement verification level selection.
- [x] 6.1 Cover every scenario in this change's delta spec.
