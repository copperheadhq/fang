# Simulation As A Compiler Target

## Why

Components must not implement numerical simulation, and nothing in the kernel
currently compiles one either — so a design's analog behaviour is unverifiable
except by building the board. The risk this stage has to avoid is the opposite
one: a simulator wired in so deeply that its assumptions leak into component
definitions, or a pass mistaken for proof.

## What Changes

- Add `fang.simulation`: simulation models as traits, the analysis types, the
  explicit plan, and plan validation.
- Add SPICE lowering: the kernel emits a simulator's native netlist rather than
  binding to a wrapper.
- Add the ngspice backend across a process boundary, reporting unsupported when
  the simulator is absent rather than substituting anything.
- Add result normalization recording the plan, the backend and its version, the
  models and their provenance, the assumptions applied, and the coverage gaps.
- Add the verification-level selector that picks the cheapest level that can
  decide a question.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `fang-kernel` — adds the analysis types, plan validation's rules, the SPICE
  lowering's determinism, and the normalized result's required fields.

## Impact

- A simulation pass becomes a finding with the confidence its provenance
  supports, never proof of physical correctness.
