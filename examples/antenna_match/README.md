# antenna_match

A 2.4 GHz chip antenna behind an L match, and the question of whether it is
matched. It is the example of a part carrying its behaviour as data: a
Touchstone file, read in-tree and composed in closed form. There is nothing to
simulate, so the question is answered at the equation level.

## The program

[`antenna_match.py`](antenna_match.py) puts a 1.5 pF shunt capacitor at the
connector and a 1.8 nH series inductor toward the antenna, and requires at
least 10 dB of return loss at 2.44 GHz. The values come from the L-match
formulas over the antenna's impedance there, recorded as a calculation.

The antenna carries its model as a trait, with a provenance that says what the
numbers are:

```python
self.antenna.add_trait(
    Touchstone(
        source="chip_antenna.s1p",
        ports=("FEED",),
        provenance=assumed_provenance("a synthetic series RLC resonator, ..."),
    )
)
```

[`chip_antenna.s1p`](chip_antenna.s1p) is **synthetic**, and says so in its
header: a series RLC resonator (22 Ohm, 4 nH, about 1.01 pF) written by hand to
stand in for the file an antenna vendor publishes. A real design would cite the
vendor's file, or a network analyser's measurement of the board, and its
provenance would say which.

The question names the measure, the frequency, and the matching parts in order
from the connector toward the antenna:

```python
matched = Evaluates(
    "match_spec",
    measures={"return_loss": ReturnLoss("antenna.rf", at=2.44 * GHz,
                                        through=("shunt_c", "series_l"))},
)
```

Which of the two parts is a shunt and which is in series is read from the
graph (the capacitor has a terminal on ground) and each value is the one
the graph holds.

## What comes out

4 parts, 3 nets, 36 entities, 1 check, undecided until the question is
answered.

[`out/verification.txt`](out/verification.txt) is the file to read: the
touchstone tool reads the model, interpolates it at 2.44 GHz, composes the two
parts, and finds 38.5 dB, so the verification passes at confidence 0.5: half,
because the model it rests on is an assumption. The number enters the graph
through the commit gate as an inferred value whose source is the run's
evidence, and the evidence records the model file's digest, because the
snapshot does not hold the file.

- [`out/antenna_match.net`](out/antenna_match.net), [`out/netlist.txt`](out/netlist.txt)
- [`out/checks.txt`](out/checks.txt), [`out/graph.txt`](out/graph.txt), [`out/rationale.md`](out/rationale.md)

![the interconnect view](out/views/interconnect.svg)

A frequency outside the file's 2.30 to 2.60 GHz is refused, naming the range;
nothing is extrapolated. A matching part with no value leaves the question
unanswered, naming the part.

## Running it

```bash
fang verify examples/antenna_match/antenna_match.py
```

The reader is fang itself, so this needs no tool on the path.
