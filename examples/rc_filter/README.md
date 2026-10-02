# rc_filter

A first-order RC low-pass ahead of an ADC, and one question about it, asked
twice. It is the smallest board that shows a constraint nobody can decide
getting decided: by a simulator, through the commit gate, and then by nothing
more than the evaluator.

## The program

[`rc_filter.py`](rc_filter.py) puts 10 kOhm and 10 nF between two connectors
and requires the -3 dB corner to lie between 1.5 and 1.7 kHz. The corner is a
parameter with no value, because nothing on the page has measured it; the
constraint over it is undecided, and `fang check` says so.

The question is declared beside the requirement it serves, with its bench in
full: 1 V driven into the input, an AC sweep from 10 Hz to 1 MHz, and the two
connectors deliberately left out. The corner is where the output falls through
1/sqrt(2) of the input.

```python
corner_check = Simulates(
    "corner_spec",
    measures={"corner": Crossing("adc.line", level=707.1 * mV, edge="falling")},
    supplies={"source.line": 1 * V},
    analysis=ACSweep(variation="dec", points=100, start="10", stop="1meg"),
    abstracted=("source", "adc"),
)
```

`Simulates` has no `result` argument. A question's result is produced by a run;
a program that tries to state one is refused.

## What comes out

4 parts, 3 nets, 37 entities, 2 checks, none failed and both undecided -- until
the question is answered.

[`out/verification.txt`](out/verification.txt) is the file to read. On the
elaborated program the constraint is undecided, so the question routes to the
circuit level and ngspice answers it: 1590 Hz, inside the band, PASS. The
measurement re-enters as a transaction -- the corner set to an inferred value
whose source is the run's evidence -- and the gate's constraint check decides
the constraint. Asked again on that committed head, the same question is
answered at the equation level: the evaluator already decides the constraint,
so nothing runs.

- [`out/rc_filter.net`](out/rc_filter.net), [`out/netlist.txt`](out/netlist.txt)
- [`out/checks.txt`](out/checks.txt): the two constraints over the corner, undecided
- [`out/graph.txt`](out/graph.txt), [`out/rationale.md`](out/rationale.md)

![the interconnect view](out/views/interconnect.svg)

The listing gives three significant figures and no tool version, so it stays
put when ngspice moves a number in its fourth figure. The evidence keeps every
figure ngspice printed, the version, the hash of the deck, and the assumptions
and coverage gaps listed above.

## Running it

```bash
fang verify examples/rc_filter/rc_filter.py                 # nothing persists
fang build  examples/rc_filter/rc_filter.py
fang verify examples/rc_filter/rc_filter.py --commit        # the corner enters the workspace
fang verify examples/rc_filter/rc_filter.py                 # answered at the equation level
```

`fang verify` needs ngspice on the path. Without it the question is reported
unsupported, by name, and nothing else answers it.
