# The Workspace And The Command Line

## Why

Everything the toolchain does is reachable only from Python. There is no way to
point it at a project and get a board out, and no place for a project's state to
live between runs — so nothing persists, and nothing is reproducible across
sessions in the way the standard requires.

This stage delivers the workspace and the commands that drive it.

## What Changes

- Add `fang.workspace`: the `.copperhead/` directory, the manifest, the
  canonical record stream on disk, and the reconstructible cache.
- Add `fang.cli`: `fang init`, `build`, `check`, `netlist`, `export`, `graph`,
  and `diff`, exposed as a console script.
- Persist the mapping table, the tool plan, and the import report alongside the
  design so a second run reuses identity rather than minting it.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `fang-kernel` — adds the workspace layout's guarantees and the command
  surface's contract.

## Impact

- Makes the whole pipeline usable from a terminal: a Fang program in, a
  verified netlist out, with state that survives between runs.
