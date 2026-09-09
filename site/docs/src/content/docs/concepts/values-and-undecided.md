---
title: Values and undecided
description: How the kernel represents a value it does not know, and a constraint it cannot decide.
sidebar:
  order: 3
  attrs:
    data-icon: question-circle
---

Every value carries how well it is known alongside the number itself, and that
status survives arithmetic.

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
| `unknown` | Not known |

**`null` never means "unknown."** `Value.unknown()` is a distinct status, so an
absent field and a field known to be unavailable are different facts and the
model keeps them apart.

A value whose sources disagree becomes a `ConflictingValue` holding the
candidates. The kernel does not resolve it by picking one; the candidates stay
visible until something decides between them.

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
expression cannot be stored, so nothing downstream re-checks units.

## Undecided is a truth value

Constraints evaluate to one of three values, not two:

| `Truth` | When |
| --- | --- |
| `true` | Satisfied |
| `false` | Violated |
| `undecided` | An operand is unknown |

Undecided propagates through Kleene three-valued logic rather than poisoning
every expression it touches. `false and undecided` is `false`, because no value
of the unknown operand could make the conjunction true. `true or undecided` is
`true`.

Check results carry the same idea, plus one more case:

| `CheckStatus` | Means |
| --- | --- |
| `PASS` | Decided and satisfied |
| `FAIL` | Decided and violated |
| `UNKNOWN` | Not decidable on what is known |
| `NOT_APPLICABLE` | The check does not cover this |

`UNKNOWN` and `NOT_APPLICABLE` are separate because "we could not tell" and
"there was nothing to tell" are different engineering situations.

## Undecided is never silently a pass

An undecided result is never quietly a pass or a failure. Whether it **blocks**
is a policy decision, made by the commit gate in `KernelGraph.propose` rather
than by the evaluator. That separation lets an early-stage design proceed with
unknowns while a release gate refuses them, with no change to any constraint.
