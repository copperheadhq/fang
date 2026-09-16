# copper_rules

A 2 A rail that states how wide its copper has to be, and two boards that answer
differently. The circuit is as small as a power path gets: a terminal block, a
header, a bulk capacitor. The circuit is not what this one is about.

## The program

[`copper_rules.py`](copper_rules.py) declares its board in a `board()` method
beside `constraints()`. The declaration is recorded, never measured: no outline
is computed and nothing is placed.

```python
def board(self):
    declare_board(
        outline=[(0, 0), (40, 0), (40, 30), (0, 30)],
        thickness=1.6 * mm,
        layers=[
            layer("F.Cu", copper_weight=1 * ozcu),
            layer("core", function="dielectric", thickness=1.5 * mm),
            layer("B.Cu", copper_weight=1 * ozcu),
        ],
    )
```

`ozcu` is a length, not a mass. "1 oz copper" names an areal density by trade
convention, but what a stackup adds up and what a width rule compares are both
thicknesses, so the unit converts to the 34.8 um the weight produces.

Two of the three constraints are about copper rather than about values, and say
so by naming their class:

```python
require(
    self.supply.physical.trace_width >= 0.5 * mm,
    constraint_class="routing",
    constraint_kind="min_trace_width",
)
```

`self.supply.physical.trace_width` is a reference through the reserved
`physical.` namespace. It resolves over whatever realizes the rail (every
segment, via and zone at once, as the interval they span), so the rule holds
over the whole realization rather than over a segment someone picked.

There is no fourth kind of thing here. A routing rule is a record in the same
constraint registry as the electrical one above it, evaluated by the same
evaluator, and the only difference is which check class selects it.

## Undecided until there is copper

3 parts, 2 nets, 35 entities, 7 checks, none failed and three undecided.

Two of those three are the routing rules, and they are undecided because nothing
realizes the rail yet:

```
UNDECIDED routing: min_trace_width on PORT-4cc256e8351c
UNDECIDED routing: min_clearance on PORT-4cc256e8351c
```

That is the whole point of the third truth value. A rule about copper that does
not exist has not passed, and reporting it as a pass would be the one answer
that is certainly wrong.

## The rules reach the router

`fang export --rules` projects them into a KiCad design-rule file:

```
(rule "RULE-bb986433e3df"
  (severity error)
  (constraint track_width
    (min 0.5mm)
  )
  (condition "A.NetClass == 'fang_min_clearance_min_trace_width_563357'")
)
```

Each rule is named by the identifier of the constraint it projects, and adds
only fields the constraint record does not already define. Here that is the net
class, which is a grouping of the rules themselves, so a conductor belongs to
exactly one class by construction. The file is a projection and nothing else: an edit
made to it in the layout tool is reported as a difference from the registry and
never adopted as the engineering fact.

## Two boards, one rule

[`narrow.kicad_pcb`](narrow.kicad_pcb) routes the rail at 0.3 mm and
[`wide.kicad_pcb`](wide.kicad_pcb) at 0.8 mm. Both are read back through the
same reader, and the same rule decides:

```
## narrow.kicad_pcb
  PASS           min_clearance on PORT-4cc256e8351c
  FAIL           min_trace_width on PORT-4cc256e8351c; realized by TRC-…, VIA-…, ZONE-…

## wide.kicad_pcb
  PASS           min_clearance on PORT-4cc256e8351c
  PASS           min_trace_width on PORT-4cc256e8351c
```

The failing result names the copper that failed, not only the rail it belongs
to. Neither board is a place the width is *recorded*: the width is a fact about
copper, and the rule about it lives in the registry.

A board names its net after the rail the program named, which is the one place
the two vocabularies meet. Everything else the reader recognizes (outline,
stackup, footprints, pads, segments, vias, zones) becomes physical entities
with derived identity, and every external identifier in the file is recorded in
the mapping table against it rather than becoming one.

## What comes out

- [`out/copper_rules.net`](out/copper_rules.net): the KiCad netlist
- [`out/rules.kicad_dru`](out/rules.kicad_dru): the design rules, projected
- [`out/net_classes.json`](out/net_classes.json): the net class assignments
- [`out/boards.txt`](out/boards.txt): each board against the rules
- [`out/netlist.txt`](out/netlist.txt): the netlist as text
- [`out/checks.txt`](out/checks.txt): seven checks, three undecided
- [`out/graph.txt`](out/graph.txt): 35 entities, by kind

## Running it

```bash
fang check  examples/copper_rules/copper_rules.py
fang export examples/copper_rules/copper_rules.py --rules -o copper_rules.kicad_dru
fang export examples/copper_rules/copper_rules.py --net-classes
```
