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
- [x] 1.3 State the bridging-continuation rule as a normative sentence in
      "Typed Interfaces, Ports, Buses, and Domains" (a link SHALL continue
      through a bridging part and SHALL stop at a non-bridging one), verified
      against `_bridged_ports` and `_series_links` in `fang/compatibility.py`.
      Requested in review: the prior text only showed the rule through
      scenarios, never stated it.
- [x] 1.4 State the multi-drop merge rule as a normative sentence in the same
      requirement (a link over a bus merges every connection sharing a
      member into one link), verified against `find_links`'s `merged`
      grouping in `fang/compatibility.py`. Same review comment: a pre-existing
      gap, addressed now because this change is what makes "link" load-bearing.
- [x] 1.5 Rename "A bus checks every participant" to "A bus checks every
      party" in "Interface Compatibility Evaluation" (the body already said
      "party"; the title hadn't caught up). Requested in review. Deferred
      to sync time: OpenSpec CLI 1.13.0's MODIFIED-block
      scenario check (`findMissingCurrentScenarios` in both `validate` and
      `archive`) matches scenarios by title against the currently-committed
      main spec, so renaming the title here reads as dropping the old
      scenario, and both `validate --strict` and `archive` hard-refuse it.
      There is no scenario-level `RENAMED` marker, only a requirement-level
      one. Confirmed the same check also gates `archive` (same function,
      `specs-apply.js`), in either direction: renaming main's title before
      archiving makes archive see the delta as dropping the new title, and
      renaming the delta's title makes `validate`/archive see it as dropping
      the old one. This change's own delta spec (above) keeps the old title
      so sync and archive went through cleanly; the rename itself was
      applied as a one-line edit directly to
      `openspec/specs/fang-kernel/spec.md` immediately after this change was
      archived, in the same PR. `spec.md` now reads "A bus checks every
      party".
- [x] 1.6 Add the four new scenarios to "Interface Compatibility Evaluation",
      each matched one-to-one to a real test in `tests/test_compatibility.py`:
      `test_a_pad_in_the_path_is_not_asked_what_it_thinks_of_the_bus`,
      `test_a_series_part_joins_the_two_interfaces_it_stands_between`,
      `test_a_series_part_carries_a_mismatch_between_the_ends_through`,
      `test_a_part_that_declares_no_bridge_ends_the_link`.
- [x] 1.7 Add `bridges` to "The Part Model" and its scenario, verified
      against `fang/lang.py:635`, `fang/parts.py:47`, and
      `test_a_part_records_what_it_bridges`.
- [x] 1.8 Add the digital-interface voltage-domain fact to "The Shipped
      Interface Catalogue", verified against `DIGITAL_PARAMETERS` in
      `fang/interfaces.py`.

## 2. Verification

- [x] 2.1 `openspec validate interface-compatibility-parties-and-bridging`
      passes.
- [x] 2.2 `uv run python -m pytest tests/test_compatibility.py -v` still
      passes unchanged (this change touches no code): 19 passed.
- [x] 2.3 `uv run python -m pytest` (full suite) still passes unchanged:
      503 passed, 1 skipped, same as before this change.

## 3. Open item for the maintainer, not fixed here

- [x] 3.1 Note in the PR that "Interface Compatibility Checks" (spec.md:487)
      and "Interface Compatibility Evaluation" (spec.md:1612) are
      near-duplicate requirements predating this change, and ask whether to
      merge them now or track it as a separate issue. The maintainer answered
      in review: keep them consistent without merging, track the merge
      separately. Nothing further to do here.
