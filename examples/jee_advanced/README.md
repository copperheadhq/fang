# jee_advanced

Two circuit-analysis questions from the JEE (Advanced) papers, one folder each.
This folder is not itself an example — it holds them.

| | Paper | Asks | Answer |
| --- | --- | --- | --- |
| [`problem_1/`](problem_1/) | 2022, Paper 1, question 1 | which of four claimed currents are correct | all four of (A), (B), (C), (D) |
| [`problem_2/`](problem_2/) | 2015, question 13 | the current I through R (= 2 Ω) | I = 1 A |

Neither is a board. They are here because the question a physics paper asks
once is the question a board asks all day — *is this claim about my circuit
true?* — and the kernel answers it the same way either time: the potentials are
a value, Kirchhoff's current law is a constraint, and the paper's claim is a
constraint the checker decides rather than a comment nobody re-reads.

The pair is worth two folders because they show different halves of that.
`problem_1` checks four claims at once, exactly the four the paper offers.
`problem_2` checks one, and then checks two more the paper never asks for —
that two of its ten resistors carry no current at all, which is the whole trick
of the question and the reason its answer is a round ampere.

Both work the same way, and neither solves anything:

- the program claims the node potentials, derives every branch current from
  them by Ohm's law, and writes Kirchhoff's current law once per node;
- `solve.py` beside it lowers the same graph to SPICE through `fang.simulation`
  and runs ngspice, which is where the potentials came from;
- `out/rationale.md` carries the question, every resistor's value and current,
  and the answer, because each of those is an entity in the graph.

The two paths are independent: ngspice solves, the kernel decides.

## Running them

```bash
fang check examples/jee_advanced/problem_1/problem_1.py
fang check examples/jee_advanced/problem_2/problem_2.py

python examples/jee_advanced/problem_1/solve.py   # needs ngspice on PATH
python examples/jee_advanced/problem_2/solve.py
```
