---
title: Views
description: Six required views, each answering one engineering question.
sidebar:
  order: 5
  attrs:
    data-icon: window
---

A view is a deterministic projection of graph state. It is generated rather than
authored, and it holds no facts of its own. That is the
[governing invariant](/concepts/one-canonical-model/) applied to drawings.

```bash
fang view --list
fang view board.py ground -o ground.svg
```

## The six

| View | Answers |
| --- | --- |
| `system` | What blocks and parts does this design contain, and how do they nest? |
| `interconnect` | What is connected to what? |
| `power` | Where does power come from and where does it go? |
| `ground` | How do returns get home, and is the intended topology held? |
| `interfaces` | Which typed interfaces exist and what do they join? |
| `safety` | Which requirements and hard constraints govern this design? |

Each is required in the sense that the implementation must be able to produce
all six from any valid graph. `interconnect` is the default when a command names
no view.

## What each one includes

| View | Nodes | Edges | Annotations |
| --- | --- | --- | --- |
| `system` | blocks, components | every kind | hard constraints |
| `interconnect` | blocks, components | electrical, power, ground, signal | none |
| `power` | blocks, components, rails | power | domain |
| `ground` | blocks, components, nets, domains | ground | star point, topology intent, domain |
| `interfaces` | blocks, components, interfaces | signal | none |
| `safety` | blocks, components, requirements | every kind | requirements, hard constraints |

A view that names no edge kind does not filter: `system` and `safety` draw every
connection in the snapshot between the nodes they include.

## How a diagram reads

A view is drawn as a block diagram, the way a datasheet or a paper draws one:
black ink on a transparent page, square boxes, and straight wires that turn
square. A box carries the name the part has in the program in capitals, such as
`FB_TOP`, or `BRIDGE_U.HIGH` where one block declaration was instantiated three
times. Its class goes underneath in brackets, because four boxes all saying
`Resistor` tell you nothing about which one is which. Its tooltip is the
identifier. A box is tall enough to give every wire it carries a point of its
own.

A wire leaves the side of the box it is heading for and ends in an arrow at the
box it reaches. It turns in a lane of its own, and where its straight run would
cross another box it drops into the clear channel between two rows instead. It
is labelled with the ports it joins, where their names say something (`OUTPUT`,
`FB`, `VIN`) rather than only numbering a pin. With no colour to tell the
connection kinds apart, a line's weight and dash do it, and the key under the
drawing lists the kinds actually present. Several connections between the same
two parts are drawn as several wires, so three gate drives read as three. The
view's name and its question sit under the drawing as its title.

Nodes are laid out in layers, ordered within a layer to reduce crossings. A node
that the view connects to nothing is packed into a grid below a rule that says
so, rather than lengthening the first column. It is still a fact about the
design, and it is still shown.

## A view reports its own incompleteness

A node carrying unknown parameters is drawn with a dashed border. The drawing
does not resolve the unknown, hide it or fill it in with a plausible number. It
shows that the graph does not know, in the same place you would look for the
value.

This is the same rule as everywhere else, applied to pixels: a view is only ever
as complete as the graph behind it, and it says so.

## Layout is a boundary

The view compiler produces a graph and placement **seeds**. It does not place,
route or own geometry. Placers and routers are reached in the
[operation phase](/concepts/three-phases/) across a process boundary. What they
return is a candidate realization that has to pass the gate like anything
else.

## Rendering

With `-o`, the view is rendered to SVG. Without it, the command summarizes what
the view contains.

```bash
fang view board.py power             # summarize
fang view board.py power -o power.svg
```

Rendering is deterministic: the same graph gives the same SVG, byte for byte.
