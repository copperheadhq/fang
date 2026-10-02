---
title: Verification
description: How an undecided constraint gets decided by a tool, without a second way in.
sidebar:
  order: 7
  attrs:
    data-icon: approve-check
---

A hard constraint over a number nobody has (a rail's ripple, a filter's
corner, an antenna's return loss) evaluates to
[undecided](/concepts/values-and-undecided/) and stays there. Verification is
how it stops being undecided: a question declared in the program, answered by a
tool, with the answer returned through [the gate](/concepts/the-commit-gate/)
like any other change.

## A question is a verification with no result yet

```python
ripple = Parameter("mV")                        # no value: nobody has measured it

under_load = Simulates(
    "rail_tolerance",
    measures={"ripple": PeakToPeak("rail_out.dc", after=1 * ms, until=1.2 * ms)},
    supplies={"controller.vin": 12 * V},
    loads={"rail_out.dc": 2.2 * Ohm},
    analysis=Transient(stop="1.2ms", step="10ns"),
)

def constraints(self):
    require(self.ripple <= 30 * mV)               # undecided until measured
```

The question elaborates to a `Verification` entity whose result is `UNKNOWN`.
It is the same entity a verification by inspection is, before its result is
known; coverage is still a join over the graph, and there is no second kind of
thing to keep in step with the first.

**A program cannot state the answer.** `Simulates(..., result="PASS")` is
refused. A pass nobody computed, with two datasheet citations as its
"evidence", is a citation and not a verification, and it is what this replaces.

## The bench is part of the question

The measured value depends on everything the run assumed, so the question says
all of it: every supply and every load at a part surface, the analysis and its
window, and the parts it deliberately leaves out. Nothing is defaulted. A
question with no supply is not runnable, and the runner says so rather than
choosing a source. Every bench item lands on the evidence as an assumption, and
every part left out as a coverage gap.

## The cheapest level that decides it

The levels run cheapest first: equation, symbolic, behavioural, circuit,
external. If the constraints over a question's parameters already decide --
because a value reached the graph some other way, or because an earlier run's
measurement is there, the constraint evaluator is the answer and nothing
runs. Otherwise the method names the level, and the first registered tool there
answers. A question no tool covers is unroutable: a cheaper answer is not the
same answer, so none is substituted. The level and the tool are written on the
verification, so the graph says how the question was answered.

## The answer comes back through the gate

A run's measurements enter as one ordinary transaction:

```text
SetParameter(ripple, Value.inferred(1.90 mV, source=EVD-..., confidence=0.5))
AddEntity(Evidence: tool, version, level, job hash, measures,
                    assumptions, coverage gaps, input digests)
RemoveEntity + AddEntity(Verification: result, evidence, level, tool)
```

The value is **inferred**, never explicit, and its source is the evidence. The
constraint over it is decided by the gate's own constraint check; there is no
second resolver that consults evidence, which would be a second place a value
could come from.

**A measurement that breaks a hard constraint never reaches the head.** The
gate rejects it, correctly, and the runner records what happened in a second
transaction that sets no parameter: the evidence, and the verification with
result `FAIL`. The design is on record as having failed, with the number that
failed it, and the constraint stays undecided in the graph, which is true: the
design has no accepted value for it.

## A finding, not a proof

A pass is a finding with the confidence its models support. A run over an
ideal switch standing in for a controller reports half the confidence of one
over primitives, and lists the control loop it does not model among its
coverage gaps. First-spin measurement remains the physical evidence.

## Re-elaboration keeps the measurement

The program declares a measured parameter without a value, so elaborating it
again says nothing about the value and does not withdraw it. An unchanged
program rebuilt after a commit is the committed snapshot, byte for byte; a
changed question is answered afresh. A measurement that a constraint tightened
since now breaks does not come back as a value: the rebuild records the failure
instead, as the gate would have had the run met that constraint.

The [verification reference](/reference/verification/) lists the declarations,
the measures, the tools and the command.
