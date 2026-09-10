# Interface Compatibility: Parties And Series Bridging

## Why

Interface compatibility checking changed behaviour twice, and
`openspec/specs/fang-kernel/spec.md` still describes the old behaviour. Both
changes are already implemented and tested (`fang/compatibility.py`,
`fang/entities.py`, `fang/lang.py`, `fang/interfaces.py`,
`tests/test_compatibility.py`) and are recorded under `[Unreleased]` in
CHANGELOG.md. The spec is the contract, so it has to agree with what the
kernel now does. This closes GitHub issue #1.

1. A link's parties are the ports whose interface declares parameters. A pad
   or a test point declares none and is a wire on the link, not a party to
   it, so it is no longer asked for a fact its interface never carries. A
   check runs only over the parameters every party declares, and a link with
   fewer than two parties has nothing to compare and yields no result at all.
2. A link now continues through a part that declares it bridges its own
   terminals (`Part.bridges`). `TwoPin` and everything built on it bridge
   their two terminals; `Transistor` and `Connector` bridge nothing. Two
   chips joined by two series resistors are compared with each other; before
   this change only the resistors were ever asked anything.

`DIGITAL_PARAMETERS` also gained `voltage`, which the voltage-domain check has
always read and the digital interface family never declared, so a digital
bus's voltage-domain agreement was unevaluable regardless of the parties and
bridging rules above.

## What Changes

- `Typed Interfaces, Ports, Buses, and Domains` gains the definitions of a
  link and a party, and states that a non-party is a wire on the link.
- `Interface Compatibility Checks` and `Interface Compatibility Evaluation`
  both stop saying a check runs over "all participants" / "every
  participant" and say what is now true: a check runs only over the
  parameters every party declares. `Interface Compatibility Evaluation` also
  gains the scenarios for a non-party being skipped, a series part joining
  two interfaces, a mismatch carrying through a series part, and a
  non-bridging part ending the link.
- `The Part Model` gains `bridges` as something a part declares, with the
  reason: nothing else in the graph records conduction through a part's own
  body.
- `The Shipped Interface Catalogue` gains the one fact that is now
  load-bearing: a digital interface declares a voltage-domain parameter,
  which is what the bus voltage-domain check depends on for that family.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `fang-kernel` — the five requirements listed above (one bullet above covers
  two of them, "Interface Compatibility Checks" and "Interface Compatibility
  Evaluation"); nothing else changes.

## Impact

- No code changes. `fang/compatibility.py`, `fang/entities.py`, `fang/lang.py`
  and `fang/interfaces.py` already implement everything this proposal
  describes; `tests/test_compatibility.py` already covers it (477 passing at
  the time the code landed; 503 passing on `main` as of this change).
- `Interface Compatibility Checks` (spec.md:487) and `Interface Compatibility
  Evaluation` (spec.md:1612) are near-duplicate requirements that predate this
  change: the second is a longer, later restatement of the first that was
  never reconciled with it. This proposal updates both so they stay
  consistent with each other, but does not merge them — that duplication is
  a separate concern from issue #1 and is left for the maintainer to decide
  whether to fix now or track separately.
