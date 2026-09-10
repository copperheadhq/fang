# Tasks: Interface Compatibility: Parties And Series Bridging

Documentation-only: the behaviour is already implemented and tested. Every
task here is verifying the spec against the code, not writing new code.

## 1. Spec text

- [x] 1.1 Add the link/party definitions to "Typed Interfaces, Ports, Buses,
      and Domains", verified against `fang/compatibility.py`'s module
      docstring and `_declared_parameters`.
- [x] 1.2 Correct "all participants" / "every participant" to the party rule
      in both "Interface Compatibility Checks" and "Interface Compatibility
      Evaluation", verified against `check_link`'s `parties`/`shared`
      computation.
- [x] 1.3 Add the four new scenarios to "Interface Compatibility Evaluation",
      each matched one-to-one to a real test in `tests/test_compatibility.py`:
      `test_a_pad_in_the_path_is_not_asked_what_it_thinks_of_the_bus`,
      `test_a_series_part_joins_the_two_interfaces_it_stands_between`,
      `test_a_series_part_carries_a_mismatch_between_the_ends_through`,
      `test_a_part_that_declares_no_bridge_ends_the_link`.
- [x] 1.4 Add `bridges` to "The Part Model" and its scenario, verified
      against `fang/lang.py:635`, `fang/parts.py:47`, and
      `test_a_part_records_what_it_bridges`.
- [x] 1.5 Add the digital-interface voltage-domain fact to "The Shipped
      Interface Catalogue", verified against `DIGITAL_PARAMETERS` in
      `fang/interfaces.py`.

## 2. Verification

- [x] 2.1 `openspec validate interface-compatibility-parties-and-bridging`
      passes.
- [x] 2.2 `uv run python -m pytest tests/test_compatibility.py -v` still
      passes unchanged (this change touches no code) — 19 passed.
- [x] 2.3 `uv run python -m pytest` (full suite) still passes unchanged —
      503 passed, 1 skipped, same as before this change.

## 3. Open item for the maintainer, not fixed here

- [ ] 3.1 Note in the PR that "Interface Compatibility Checks" (spec.md:487)
      and "Interface Compatibility Evaluation" (spec.md:1612) are
      near-duplicate requirements predating this change, and ask whether to
      merge them now or track it as a separate issue.
