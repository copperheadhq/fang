# Engineering Rationale And The Verification Graph

## Why

The kernel can hold requirements, decisions, and evidence, but a Fang program
cannot create them — so the engineering reasoning lives in a document beside the
design and drifts from it. The rationale queries the standard requires are
answerable only because the fixtures put the entities there by hand.

This stage lets the design record its own reasoning where the engineering
happens.

## What Changes

- Add `fang.rationale`: `Requirement`, `Assumption`, `Decision`, `Evidence`,
  `Calculation`, and `Verification` declarable from a Fang program.
- Attach requirements to the constraints that serve them, so impact propagates.
- Add the verification result graph and impact propagation over a semantic diff.
- Make the six rationale queries answerable over an elaborated design.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `fang-kernel` — adds rationale authoring from the language, the calculation
  and verification entities, and impact propagation's rules.

## Impact

- A claim asserted without a citation is recorded as an assumption, which makes
  the difference between what is known and what is hoped visible in the graph.
