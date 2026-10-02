# Tasks: Verification Backends

Golden source: [RFC-0001](../../../rfcs/RFC-0001-verification-backends.md).

## 1. Diagnostics and entity fields

- [ ] 1.1 Allocate the `SIM` codes named in design.md with `_allocate`, at the
      bottom of a new `SIM` block; verify the registry tests still pass and no
      code was reused.
- [ ] 1.2 Add optional `level` and `tool` fields to `Verification`, omitted from
      `as_dict()` when absent; verify an existing snapshot's hash is unchanged
      (the examples' committed outputs still match before any example is edited).
- [ ] 1.3 Add the `Touchstone` trait to `fang/traits.py` (source, ports,
      provenance); verify it registers and enumerates like `Simulatable`.

## 2. Declaring questions

- [ ] 2.1 Add the measure specs (`PeakToPeak`, `Average`, `Maximum`, `Minimum`,
      `ValueAt`, `Crossing`, `ReturnLoss`) and the `Simulates`, `Checks` and
      `Evaluates` declarations in `fang/verification.py`, each refusing a
      `result`; verify a declaration with a result raises.
- [ ] 2.2 Refuse a `Checks` exclusion with no reason; verify with a test.
- [ ] 2.3 Elaborate a question into a `Verification` with result `UNKNOWN` and
      `extensions["question"]` holding the canonical question dictionary, with
      every surface resolved to `(component id, pin)` pairs at elaboration time;
      verify the entity names the requirement, method, measured parameters and
      bench, and that two elaborations are byte-identical.
- [ ] 2.4 Fail elaboration with a `SIM` diagnostic when a measure names an
      undeclared parameter or a surface with no pins; verify each names what is
      wrong.
- [ ] 2.5 Verify a plain `Verifies(..., method="inspection", result="PASS")`
      elaborates exactly as before and is never routed.

## 3. SPICE lowering for a real run

- [ ] 3.1 Instantiate a modelled part as an `X` device, reading the port order
      from the model's `.subckt` line and mapping pins through the trait's
      `pin_map`; verify the device line, that the model is `.include`d not
      inlined, and that an unreached port is refused by name.
- [ ] 3.2 Lower bench supplies and loads to `V`, `I` and `R` devices at the
      resolved nodes, refusing a load of any other dimension; verify each
      device line and the refusal.
- [ ] 3.3 Lower measures to the ngspice dialect (a `.control` block) and to the
      Xyce dialect (`.measure` lines), sharing devices and bench; verify the two
      decks differ only in analysis and measurement lines, and that
      preparation is byte-identical twice.
- [ ] 3.4 Parse ngspice's `name = value` measurement lines and failed-measure
      lines, and Xyce's measure file, into `Decimal`; verify against output
      captured from the installed ngspice 45.2 and a captured Xyce measure file,
      and that a failed or absent measure yields no measurement.
- [ ] 3.5 Add `XyceBackend` beside `NgspiceBackend`; verify it reports
      unsupported by name where Xyce is absent.

## 4. The protocol, routing and the runner

- [ ] 4.1 Define `Tool`, `Question`, `Job`, `RawRun` and `Measurement`, and the
      default tool registry in its documented order; verify `Job.input` hashes
      identically across two preparations.
- [ ] 4.2 Implement `route()`: equation level when every constraint over the
      measured parameters is already decided, else the first covering tool at
      the method's level, else unroutable; verify all three, and that no tool is
      prepared for an equation-level answer.
- [ ] 4.3 Report a question with no supply as not runnable naming what is
      missing, and a missing tool as unsupported by name with nothing
      substituted; verify both.
- [ ] 4.4 Record bench items as assumptions and abstracted parts as coverage
      gaps on the job; verify.
- [ ] 4.5 Bound confidence by model provenance; verify a run over an assumed
      model reports lower confidence than one over primitives.

## 5. Re-entry through the gate

- [ ] 5.1 Build the measurement transaction — inferred `SetParameter`s sourced
      from the evidence, the structured `Evidence`, the replaced `Verification`
      with result, evidence, level, tool and a provenance record; verify each
      against a `KernelGraph`, and that the verification keeps its identifier.
- [ ] 5.2 Verify the previously undecided constraint is decided by the gate's
      constraint check on the accepted proposal.
- [ ] 5.3 On a rejection caused by a failed hard constraint over a measured
      parameter, record evidence and a `FAIL` verification in a second
      transaction that sets no parameter; verify the head holds both and the
      parameter is still unknown.
- [ ] 5.4 Verify a rejection for any other reason records nothing, and that
      measurements prepared against a stale head are refused.

## 6. Rule checks

- [ ] 6.1 Add `fang/rulecheck.py`: run `kicad-cli sch erc --format json` over a
      scratch copy of the compiled schematic and parse violations; verify the
      parser against JSON captured from kicad-cli 9.0.8, and that an absent
      `kicad-cli` reports unsupported by name.
- [ ] 6.2 Apply declared exclusions, recording rule, reason and count; verify
      errors fail, warnings do not, and excluded rules do neither.

## 7. Touchstone

- [ ] 7.1 Add `fang/rf.py`: read `.s1p`/`.s2p` with option-line units, the RI,
      MA and DB formats and reference resistance, and interpolate; verify two
      files in different formats give the same measurement, and that a frequency
      outside the range is refused naming the range.
- [ ] 7.2 Compose named series and shunt parts into the one-port from the
      graph's values, leaving the question unanswered when a value is unknown;
      verify against a hand-computed match.
- [ ] 7.3 Quantize to six significant figures at the `Decimal` boundary; verify
      the measurement's text is stable.

## 8. The command

- [ ] 8.1 Add `fang verify` with `--commit`; verify it prints level, tool,
      measurements and result per question, exits non-zero on a failed
      verification, zero on an unsupported one and on a program with no
      questions, and leaves the workspace untouched without `--commit`.

## 9. Examples, used as tests

- [ ] 9.1 Add `examples/rc_filter/`: a corner-frequency question answered once
      at the equation level and once by ngspice AC; README and `out/`.
- [ ] 9.2 Add `examples/antenna_match/`: a chip antenna's Touchstone model
      through an L match, return loss at 2.44 GHz; the model file is synthetic
      and says so in its header and provenance; README and `out/`.
- [ ] 9.3 Extend `examples/buck_regulator/`: `ripple` and `output` parameters,
      their constraints, a `Simulates` question under full load with an
      `ideal_buck.sub` model of assumed provenance, replacing the hand-asserted
      `Verifies`; update its README.
- [ ] 9.4 Add `verification.txt` to `examples/regenerate.py` for examples that
      declare a question, at three significant figures and without versions;
      teach `tests/test_examples.py` to skip that file by name where the tool is
      absent; regenerate and verify the examples suite passes.
- [ ] 9.5 Add `tests/test_verification.py`, `tests/test_rulecheck.py` and
      `tests/test_rf.py` covering every scenario in the delta spec, and
      `test_at_v1_*` in `tests/test_acceptance.py`; verify the whole suite
      passes, and passes with `PATH` stripped of ngspice and kicad-cli (skips
      named, nothing failing).

## 10. Documents

- [ ] 10.1 Add `site/docs/.../reference/verification.md` and
      `concepts/verification.md`; update `reference/cli.md` and
      `reference/simulation.md`; verify internal links resolve.
- [ ] 10.2 Update `README.md`, `CLAUDE.md`, `CHANGELOG.md`,
      `openspec/ROADMAP.md` (stage 13) and `examples/README.md`; add
      `rfcs/README.md` and `graft rfcs` to `MANIFEST.in`; verify the counts
      quoted anywhere match the tree.
- [ ] 10.3 Quote the requirement names in each new module's docstring; verify
      `openspec validate fang-verification --strict` passes.
