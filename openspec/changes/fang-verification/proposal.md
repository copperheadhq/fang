# Verification Backends

The golden source for this change is
[rfcs/RFC-0001-verification-backends.md](../../../rfcs/RFC-0001-verification-backends.md).
Its section 3 is the survey of tools and their ranking; its section 6 is the
normative text this change's delta spec carries.

## Why

The kernel holds constraints it cannot decide and has no way to find out. A
hard constraint over a parameter nobody has a number for — a rail's ripple, a
filter's corner, an antenna's return loss — evaluates to undecided and stays
there, because no path exists from a solver's output to a value the constraint
evaluator can read: `fang sim` prints a finding and the graph never hears of it.
In the same gap a program can write `Verifies(..., result="PASS")` and the
coverage query believes a pass no computation produced.

## What Changes

- Add declared **verification questions**: `Simulates`, `Checks` and
  `Evaluates`, written beside the requirement they serve. Each elaborates to a
  `Verification` entity whose result is `UNKNOWN` until a tool answers it, and
  none lets a program state its own computed result.
- Add the explicit **bench**: supplies and loads applied at part surfaces, the
  analysis window, and the parts deliberately abstracted. Nothing about a bench
  is defaulted, and every item is recorded as an assumption on the run.
- Add **measures** — peak-to-peak, average, maximum, minimum, value at a point,
  crossing, return loss — each taken at a part surface and written into one
  declared parameter.
- Add the **tool protocol** (`covers`, `available`, `version`, `prepare`, `run`,
  `read`) and **routing** by verification level: a question the constraint
  evaluator already decides is answered at the equation level with no tool run;
  otherwise the cheapest registered tool that covers it, recorded on the
  verification.
- Add **re-entry through the commit gate**: measured parameters as inferred
  values whose source is the run's `Evidence`, that evidence carrying the
  structured measurement record, and the declared `Verification` replaced under
  its own identity. A measurement that would violate a hard constraint does not
  advance the head; it is recorded as a failed verification with its evidence.
- Add four tools: **ngspice** (operating point, transient, AC), **Xyce** (the
  same lowering; reports unsupported where not installed), **KiCad ERC** over
  the schematic the kernel draws, and **Touchstone** models read in-tree for RF
  questions.
- Extend SPICE lowering with what a real run needs: subcircuit instantiation
  for modelled parts, bench devices, and measurement directives.
- Add `fang verify`, and a `verification.txt` to the outputs an example ships.
- Add two examples and extend one, each used by the suite: `rc_filter/` (one
  question answered at two levels), `antenna_match/` (a Touchstone model
  through an L match), and `buck_regulator/` (ripple and regulation under load,
  replacing a hand-asserted pass).
- Nothing is removed and nothing breaks: `Verifies` stays for verifications by
  inspection and test, and `fang sim` stays as the low-level command.

## Capabilities

### New Capabilities

None. The project holds one capability and this change extends it.

### Modified Capabilities

- `fang-kernel` — adds the requirements for declared questions, the explicit
  bench, level routing, the tool protocol, measurement re-entry through the
  gate, recording a failing measurement, rule checks as evidence, Touchstone
  models as data, the verify command, and one acceptance criterion, AT-V1.
  No existing requirement's text changes.

## Impact

- New modules `fang/verification.py` (questions, benches, measures, the
  protocol, routing, the runner, re-entry), `fang/rulecheck.py` (KiCad ERC) and
  `fang/rf.py` (Touchstone reading and two-port composition).
- `fang/simulation.py` gains subcircuit and bench lowering, measurement
  directives, the ngspice output parser and the Xyce backend;
  `fang/rationale.py`, `fang/elaborate.py`, `fang/entities.py` and
  `fang/traits.py` gain the declarations, their entity fields and the
  `Touchstone` trait; `fang/cli.py` gains `verify`; `fang/diagnostics.py`
  gains codes in the `SIM` area.
- No new runtime dependency. ngspice, Xyce and kicad-cli are found on the path
  and their absence is reported by name; scikit-rf is named in the RFC as a
  future extra and nothing here imports it.
- `examples/regenerate.py` and `tests/test_examples.py` learn the new output
  and skip it, by name, where ngspice is absent.
- Docs: a verification reference page and a concepts page on the site, the CLI
  and simulation pages, `README.md`, `CLAUDE.md`, `CHANGELOG.md`,
  `openspec/ROADMAP.md` (stage 13), and `MANIFEST.in` for `rfcs/`.
