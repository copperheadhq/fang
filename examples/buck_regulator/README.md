# buck_regulator

12 V to 3.3 V, with the reasoning kept beside the circuit. The converter itself
is ordinary. What is not ordinary is that the argument for it sits in the same
graph as the inductor.

## The program

[`buck_regulator.py`](buck_regulator.py) records five kinds of reasoning as
entities, not comments:

```python
rail_tolerance = Requires("The 3V3 rail holds 3.3 V within 3% for 0 to 1.5 A over a 6 to 15 V input", ...)
part_choice    = Chooses("Which converter makes the 3V3 rail?", selected="TPS62130", ...)
ripple_current = Cites("Recommended inductor ripple is 20 to 40% of the maximum output current", ...)
inductor_value = Calculates("L = v_out * (1 - v_out / v_in) / (f_sw * ripple_current)", ...)
under_load     = Simulates("rail_tolerance", measures={"ripple": ..., "output": ...}, ...)
```

So "why is this 4.7 µH?" has an answer the graph can give: a calculation, over a
datasheet claim, serving a requirement, which a question verifies. Nobody had
to write a design document. Nothing here can drift from the design either,
because it *is* the design. Change the evidence and the decision resting on it
is flagged.

The output voltage is deliberately not a parameter of the controller. The
feedback divider on the board sets it, which is why the divider carries the
constraint that produces it.

## The question

The requirement used to be closed by a `Verifies(..., result="PASS")` whose
evidence was two datasheet citations: a citation, not a verification. It is
now a question, and the program cannot state its answer.

`ripple` and `output` are parameters with no value, each with a constraint:
ripple at most 30 mV, the output between 3.2 and 3.4 V. The question measures
both on a bench it names in full: 12 V on the controller's input, 2.2 Ohm
across the rail header (1.5 A at 3.3 V), and a transient to 1.2 ms measured
over its last 0.2 ms. It leaves out the input connector, the fuse, the reverse
diode and the header, so the supply lands on the controller.

The controller is simulated by [`ideal_buck.sub`](ideal_buck.sub): two ideal
switches at a fixed duty of 0.275. It is not a model of the TPS62130, and the
program says so: the trait's provenance is an assumption, which halves the
confidence of every number measured over it, and what it leaves out, the
control loop above all, is recorded as a coverage gap on every run.

[`out/verification.txt`](out/verification.txt) is what `fang verify` finds:
3.29 V and 1.90 mV of ripple, both inside their constraints, so the
verification passes at confidence 0.5. Those numbers enter the graph as
inferred values whose source is the run's evidence, through the commit gate,
and the constraints over them are decided by the gate's own constraint check.

## What comes out

11 parts, 9 nets, 121 entities, 18 checks. None failed and four undecided:
three are the rail's own numbers, until `fang verify` measures them.

[`out/rationale.md`](out/rationale.md) is the file to read. It is the whole
argument, projected out of the graph in identifier order:

> ### system.inductor_value (`CALC-7d60a2e8f772`)
>
> `L = v_out * (1 - v_out / v_in) / (f_sw * ripple_current)`
>
> Result: 4.7 uH at 1.25 MHz for 30% ripple at 1.5 A
>
> - Over `system.inductor` (Inductor, `CMP-64dfc4cd840c`)

- [`out/verification.txt`](out/verification.txt): the question, answered
- [`out/buck_regulator.net`](out/buck_regulator.net), [`out/netlist.txt`](out/netlist.txt)
- [`out/checks.txt`](out/checks.txt), [`out/graph.txt`](out/graph.txt)

![the power view](out/views/power.svg)

![the system view](out/views/system.svg)

## Running it

```bash
fang check   examples/buck_regulator/buck_regulator.py
fang verify  examples/buck_regulator/buck_regulator.py      # needs ngspice
fang view    examples/buck_regulator/buck_regulator.py power -o power.svg
```
