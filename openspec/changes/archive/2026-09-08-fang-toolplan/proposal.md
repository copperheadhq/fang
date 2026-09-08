# The Tool Runtime And Realizations

## Why

Elaboration records a plan but nothing runs it. The three phases the standard
separates — elaboration, operation, commit — currently stop after the first, so
a program can ask for a netlist, a check, and an export, and get none of them.

This stage delivers the operation phase: the tool contract, the runtime that
executes a plan against immutable snapshots, and the realizations it produces.

## What Changes

- Add `fang.runtime`: the tool contract, the registry, terminal statuses, and
  the executor that resolves symbolic conditions and runs calls in order.
- Add the built-in tools: `netlist`, `check`, and `export`.
- Produce realizations naming their parent snapshot, and route any implied
  semantic change back through a transaction.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `fang-kernel` — adds the tool contract's terminal statuses, condition
  resolution, idempotence, and the operation phase's isolation from canonical
  state.

## Impact

- Completes the three-phase pipeline: a program elaborates, its plan runs, and
  what the run produced attaches only through the gate.
