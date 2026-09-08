---
title: Values and undecided
description: Unknown is a status, and undecided is a third truth value.
sidebar:
  order: 3
---

A number in an engineering model is never only a number. How well it is known
travels with it, and the kernel refuses to lose that on the way through a
calculation.

## Every value carries a status

```python
from fang.lang import V, kOhm

Resistor(resistance=10 * kOhm)   # explicit: someone wrote it
```

| Status | Means |
| --- | --- |
| `explicit` | Someone wrote it |
| `inferred` | The kernel computed it from other facts |
| `assumed` | A working claim with no evidence behind it |
| `unknown` | Not known, which is itself a value rather than a gap |

**`null` never means "unknown."** `Value.unknown()` is a distinct status, so a
field that is absent and a field that is known to be unavailable are different
facts and stay different.

A value whose sources disagree becomes a `ConflictingValue` holding the
candidates. It is not resolved by picking the first, the newest or the most
precise. It stays unresolved and visible until something decides it.

## Quantities have dimensions

A `Quantity` is a decimal magnitude over a dimension vector on the seven SI
bases. It can be a scalar, a range or a nominal with a tolerance:

```python
from fang.lang import V, between, tolerance

between(3.0 * V, 3.6 * V)          # a range
tolerance(10 * kOhm, "1%")         # nominal and tolerance
```

**Dimensional errors are rejected where they are written.** `Arithmetic` checks
dimensions in `__post_init__`, so `3 * V + 10 * kOhm` raises
[`UNIT-0001`](/reference/diagnostics/) at construction. A dimensionally invalid
expression cannot be stored, let alone evaluated. That is why nothing downstream
re-checks units.

## Undecided is a truth value

Constraints evaluate to one of three values, not two:

| `Truth` | When |
| --- | --- |
| `true` | Satisfied |
| `false` | Violated |
| `undecided` | An operand is unknown |

Undecided propagates through Kleene three-valued logic, which is stronger than
saying unknown poisons everything. `false and undecided` is `false`, because no
value of the unknown operand could make the conjunction true. `true or undecided`
is `true`. The kernel decides what it can and stops exactly where it must.

Check results carry the same idea, plus one more case:

| `CheckStatus` | Means |
| --- | --- |
| `PASS` | Decided and satisfied |
| `FAIL` | Decided and violated |
| `UNKNOWN` | Not decidable on what is known |
| `NOT_APPLICABLE` | The check does not cover this |

`UNKNOWN` and `NOT_APPLICABLE` are separate because "we could not tell" and
"there was nothing to tell" are different engineering situations. Collapsing
them is how a checklist comes to report coverage it does not have.

## Undecided is never silently a pass

An undecided result is never quietly a pass and never quietly a failure.
Whether it **blocks** is a policy decision made by the commit gate in
`KernelGraph.propose`, not by the evaluator. The evaluator's job is to be honest
about what it knows. The gate's job is to decide what to do about it.

That separation is what lets an early-stage design proceed with unknowns while a
release gate refuses them, with no change to any constraint.
