# Tasks: Verification Backends

Implements copperhead RFC 12 version 1.3, Sections 12.7 to 12.10
([copperheadhq/copperhead-rfcs#6](https://github.com/copperheadhq/copperhead-rfcs/pull/6)).

Groups 1 to 7 are the spine and land first, proven on ngspice, as RFC 12
Appendix B.12 has it. Groups 8 to 10 — Xyce, rule checks and Touchstone —
follow on the same protocol and are off the critical path; group 11 closes the
change.

## 1. Diagnostics and entity fields

- [x] 1.1 Allocate the `SIM` codes named in design.md with `_allocate`, at the
      bottom of a new `SIM` block; verify the registry tests still pass and no
      code was reused.
- [x] 1.2 Add optional `level` and `tool` fields to `Verification`, omitted from
      `as_dict()` when absent; verify an existing snapshot's hash is unchanged
      (the examples' committed outputs still match before any example is edited).

## 2. Declaring questions

- [x] 2.1 Add the circuit measure specs (`PeakToPeak`, `Average`, `Maximum`,
      `Minimum`, `ValueAt`, `Crossing`) and the `Simulates` declaration in
      `fang/verification.py`, refusing a `result`; verify a declaration with a
      result raises.
- [x] 2.2 Elaborate a question into a `Verification` with result `UNKNOWN` and
      `extensions["question"]` holding the canonical question dictionary, with
      every surface resolved to `(component id, pin)` pairs at elaboration time;
      verify the entity names the requirement, method, measured parameters and
      bench, and that two elaborations are byte-identical.
- [x] 2.3 Fail elaboration with a `SIM` diagnostic when a measure names an
      undeclared parameter or a surface with no pins, or a parameter the
      program gives a value (SIM-0002, as for a stated result); verify each
      names what is wrong.
- [x] 2.4 Verify a plain `Verifies(..., method="inspection", result="PASS")`
      elaborates exactly as before and is never routed.

## 3. The protocol, routing and the runner

- [x] 3.1 Define `Tool`, `Question`, `Job`, `RawRun` and `Measurement`, and the
      default tool registry in its documented order; verify `Job.input` hashes
      identically across two preparations.
- [x] 3.2 Implement `route()`: equation level when every measured parameter
      holds a value and every constraint over them is already decided, else the
      first covering tool at the method's level, else unroutable; verify all
      three, that no tool is prepared for an equation-level answer, and that a
      measured parameter with no value and no constraint keeps the question
      off the evaluator.
- [x] 3.3 Report a question with no supply as not runnable naming what is
      missing, and a missing tool as unsupported by name with nothing
      substituted; verify both.
- [x] 3.4 Record bench items as assumptions and abstracted parts as coverage
      gaps on the job; verify.
- [x] 3.5 Bound confidence by model provenance; verify a run over an assumed
      model reports lower confidence than one over primitives.

## 4. SPICE lowering for a real run, on ngspice

- [x] 4.1 Instantiate a modelled part as an `X` device, reading the port order
      from the model's `.subckt` line and mapping pins through the trait's
      `pin_map`; verify the device line, that the model is `.include`d not
      inlined, that an unreached port is refused by name, and that the model
      file's digest is recorded among the job's inputs.
- [x] 4.2 Lower bench supplies and loads to `V`, `I` and `R` devices at the
      resolved nodes, refusing a load of any other dimension; verify each
      device line and the refusal.
- [x] 4.3 Lower measures to the ngspice dialect (a `.control` block) behind the
      dialect seam the Xyce dialect will share; verify that preparation is
      byte-identical twice.
- [x] 4.4 Parse ngspice's `name = value` measurement lines and failed-measure
      lines into `Decimal`; verify against output captured from the installed
      ngspice 45.2, and that a failed or absent measure yields no measurement.

## 5. Re-entry through the gate

- [x] 5.1 Build the measurement transaction — inferred `SetParameter`s sourced
      from the evidence, the structured `Evidence` with its input digests, the
      replaced `Verification` with result, evidence, level, tool and a
      provenance record; verify each against a `KernelGraph`, and that the
      verification keeps its identifier.
- [x] 5.2 Verify the previously undecided constraint is decided by the gate's
      constraint check on the accepted proposal.
- [x] 5.3 On a rejection caused by a failed hard constraint over a measured
      parameter, record evidence and a `FAIL` verification in a second
      transaction that sets no parameter; verify the head holds both and the
      parameter is still unknown.
- [x] 5.4 Verify a rejection for any other reason records nothing, and that
      measurements prepared against a stale head are refused.
- [x] 5.5 When a program is elaborated again into a workspace whose head holds a
      measured value for a parameter the program declares without one, keep
      the measured value and its evidence while the measurement is current
      (preparing its question afresh gives the job its evidence records);
      verify an unchanged re-elaboration leaves both in place and records no
      change to the parameter, that a changed part, model file or firmware
      drops both so the question runs again, and that the installed tool is
      never consulted.

- [x] 5.6 Re-enter a run already recorded for the same job and tool version
      through the gate instead of running it again or reporting it current:
      set the parameters from its measurement record, cite its evidence as it
      stands, and report current only when the gate decides what the head
      holds; verify a relaxed constraint passes a recorded failure, a
      constraint that became undecided unseats a recorded pass, and an
      unchanged one is current with nothing committed.

## 6. The command

- [x] 6.1 Add `fang verify` with `--commit`; verify it prints level, tool,
      measurements and result per question, exits non-zero on a failed
      verification, zero on an unsupported one and on a program with no
      questions, and leaves the workspace untouched without `--commit`.
- [x] 6.2 Gate what `verify --commit` writes as `build` gates what it writes,
      the whole design proposed against an empty snapshot with the default
      checks; verify a design holding a measurement that breaks a tightened
      constraint is refused with the gate's diagnostics and nothing written.

## 7. The spine's examples and acceptance test

- [x] 7.1 Add `examples/rc_filter/`: a corner-frequency question answered once
      at the equation level and once by ngspice AC; README and `out/`.
- [x] 7.2 Extend `examples/buck_regulator/`: `ripple` and `output` parameters,
      their constraints, a `Simulates` question under full load with an
      `ideal_buck.sub` model of assumed provenance, replacing the hand-asserted
      `Verifies`; update its README.
- [x] 7.3 Add `verification.txt` to `examples/regenerate.py` for examples that
      declare a question, at three significant figures and without versions;
      teach `tests/test_examples.py` to skip that file by name where the tool is
      absent; regenerate and verify the examples suite passes.
- [x] 7.4 Add `tests/test_verification.py` covering every scenario in the delta
      spec that the spine delivers, and `test_at_v1_*` in
      `tests/test_acceptance.py`; verify the whole suite passes, and passes with
      `PATH` stripped of ngspice (skips named, nothing failing).

## 8. Xyce

- [x] 8.1 Add the Xyce dialect (`.measure` lines) behind the dialect seam;
      verify the ngspice and Xyce decks differ only in analysis and measurement
      lines.
- [x] 8.2 Parse Xyce's measure file into `Decimal`; verify against a captured
      measure file, and that a failed or absent measure yields no measurement.
- [x] 8.3 Add `XyceBackend` beside `NgspiceBackend`; verify it reports
      unsupported by name where Xyce is absent.

## 9. Rule checks

- [x] 9.1 Add the `Checks` declaration, refusing a `result`, and refuse an
      exclusion with no reason; verify both with tests.
- [x] 9.2 Add `fang/rulecheck.py`: run `kicad-cli sch erc --format json` over a
      scratch copy of the compiled schematic and parse violations; verify the
      parser against JSON captured from the installed kicad-cli, and that an
      absent `kicad-cli` reports unsupported by name.
- [x] 9.3 Apply declared exclusions, recording rule, reason and count; verify
      errors fail, warnings do not, and excluded rules do neither.
- [x] 9.4 Add `tests/test_rulecheck.py` covering the delta spec's rule-check
      scenarios; verify it passes with `PATH` stripped of kicad-cli.

## 10. Touchstone

- [x] 10.1 Add the `Touchstone` trait to `fang/traits.py` (source, ports,
      provenance); verify it registers and enumerates like `Simulatable`.
- [x] 10.2 Add the `ReturnLoss` measure and the `Evaluates` declaration,
      refusing a `result`; verify a declaration with a result raises.
- [x] 10.3 Add `fang/rf.py`: read `.s1p`/`.s2p` with option-line units, the RI,
      MA and DB formats and reference resistance, and interpolate; verify two
      files in different formats give the same measurement, and that a frequency
      outside the range is refused naming the range.
- [x] 10.4 Compose named series and shunt parts into the one-port from the
      graph's values, leaving the question unanswered when a value is unknown;
      verify against a hand-computed match.
- [x] 10.5 Quantize to six significant figures at the `Decimal` boundary; verify
      the measurement's text is stable.
- [x] 10.6 Add `examples/antenna_match/`: a chip antenna's Touchstone model
      through an L match, return loss at 2.44 GHz; the model file is synthetic
      and says so in its header and provenance; README and `out/`.
- [x] 10.7 Add `tests/test_rf.py` covering the delta spec's Touchstone
      scenarios; verify the whole suite passes.
- [x] 10.8 Read and compare a file's frequencies as decimals; verify a
      question at the file's last point is answered, not refused.
- [x] 10.9 Keep `dB` apart from every linear dimensionless unit in conversion,
      in expressions, in parameter values and in what a measure writes; verify
      each refusal, and that a `ReturnLoss` into a percent parameter fails
      elaboration.

## 11. Documents

- [x] 11.1 Add `site/docs/.../reference/verification.md` and
      `concepts/verification.md`; update `reference/cli.md` and
      `reference/simulation.md`; verify internal links resolve.
- [x] 11.2 Update `README.md`, `CLAUDE.md`, `CHANGELOG.md`,
      `openspec/ROADMAP.md` (in flight) and `examples/README.md`; verify the
      counts quoted anywhere match the tree.
- [x] 11.3 Quote the requirement names in each new module's docstring; verify
      `openspec validate fang-verification --strict` passes.
