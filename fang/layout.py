"""The layout boundary.

Spec: "The Layout Boundary". Input to layout carries only layout information —
identity, dimensions, ports, edges, hierarchy, and hints — and no engineering
meaning. Output becomes a positioned view graph; rendering stays ours, which is
what keeps the layout engine replaceable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from .views import ViewEdge, ViewGraph, ViewNode

#: Default geometry. Presentation only; no engineering decision depends on it.
NODE_WIDTH = 168
NODE_HEIGHT = 60
LAYER_GAP = 104
ROW_GAP = 28

#: A box grows with its label rather than clipping it, between these bounds.
MIN_NODE_WIDTH = 132
MAX_NODE_WIDTH = 272
LABEL_CHAR_WIDTH = 8

#: How many barycentre sweeps to run. Four is where the crossing count stops
#: improving on the shipped examples, and the pass is cheap.
SWEEPS = 4

#: The gap above the nodes this view connects to nothing.
ISOLATED_GAP = 64


@dataclass(frozen=True)
class LayoutNode:
    """A node as layout sees it: an identity and a box. No meaning."""

    id: str
    width: int = NODE_WIDTH
    height: int = NODE_HEIGHT
    ports: tuple[str, ...] = ()
    parent: str | None = None

    def as_dict(self) -> dict:
        out: dict = {"id": self.id, "width": self.width, "height": self.height}
        if self.ports:
            out["ports"] = list(self.ports)
        if self.parent:
            out["parent"] = self.parent
        return out


@dataclass(frozen=True)
class LayoutEdge:
    id: str
    source: str
    target: str

    def as_dict(self) -> dict:
        return {"id": self.id, "source": self.source, "target": self.target}


@dataclass(frozen=True)
class LayoutRequest:
    """Everything layout is given, and nothing else.

    There is deliberately no label, no kind, no annotation, and no parameter
    here: an engine that could see engineering meaning could come to depend on
    it, and then it would not be replaceable.
    """

    nodes: tuple[LayoutNode, ...]
    edges: tuple[LayoutEdge, ...]
    hints: Mapping[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "nodes": [node.as_dict() for node in self.nodes],
            "edges": [edge.as_dict() for edge in self.edges],
            "hints": dict(self.hints),
        }


@dataclass(frozen=True)
class Position:
    x: int
    y: int

    def as_dict(self) -> dict:
        return {"x": self.x, "y": self.y}


@dataclass(frozen=True)
class PositionedView:
    """A view graph with geometry attached. Rendering reads this."""

    graph: ViewGraph
    positions: Mapping[str, Position]
    width: int
    height: int

    def as_dict(self) -> dict:
        return {
            "graph": self.graph.as_dict(),
            "positions": {k: v.as_dict() for k, v in sorted(self.positions.items())},
            "width": self.width,
            "height": self.height,
        }


class PlacementSeeds:
    """Preferred relative placement, so two views of the same design line up.

    Seeds are presentation state. They are stored apart from canonical identity,
    and changing one is a presentation change, never an electrical one.
    """

    def __init__(self, order: Mapping[str, int] | None = None) -> None:
        self._order: dict[str, int] = dict(order or {})

    def rank(self, node_id: str) -> int:
        """A seeded node sorts by its seed; an unseeded one sorts after, by id."""
        return self._order.get(node_id, 1_000_000)

    def set(self, node_id: str, rank: int) -> None:
        self._order[node_id] = rank

    def learn(self, positioned: PositionedView) -> "PlacementSeeds":
        """Remember this layout's ordering so a sibling view can reuse it."""
        ordered = sorted(positioned.positions.items(), key=lambda kv: (kv[1].x, kv[1].y))
        for rank, (node_id, _) in enumerate(ordered):
            self._order[node_id] = rank
        return self

    def as_dict(self) -> dict:
        return dict(sorted(self._order.items()))

    def __len__(self) -> int:
        return len(self._order)


def box_size(label: str, detail: str = "") -> tuple[int, int]:
    """How big a box has to be to hold what is written in it.

    A dimension is layout information, so this is on the near side of the
    boundary: the engine is told how wide the box is, never what the words in
    it say.
    """
    longest = max(len(label), len(detail) + 2, 1)
    width = min(MAX_NODE_WIDTH, max(MIN_NODE_WIDTH, longest * LABEL_CHAR_WIDTH + 32))
    return width, NODE_HEIGHT


def to_request(graph: ViewGraph, hints: Mapping[str, str] | None = None) -> LayoutRequest:
    """Strip a view graph down to what layout may see."""
    return LayoutRequest(
        tuple(
            LayoutNode(
                node.id,
                *box_size(node.label, node.detail),
                ports=node.ports,
                parent=node.parent,
            )
            for node in graph.nodes
        ),
        tuple(LayoutEdge(edge.id, edge.source, edge.target) for edge in graph.edges),
        dict(hints or {}),
    )


def _adjacency(request: LayoutRequest) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Successors and predecessors, self-loops and dangling ends dropped."""
    ids = {node.id for node in request.nodes}
    successors: dict[str, list[str]] = {node_id: [] for node_id in sorted(ids)}
    predecessors: dict[str, list[str]] = {node_id: [] for node_id in sorted(ids)}
    for edge in request.edges:
        if edge.source in ids and edge.target in ids and edge.source != edge.target:
            successors[edge.source].append(edge.target)
            predecessors[edge.target].append(edge.source)
    return successors, predecessors


def _layers(
    node_ids: Sequence[str],
    successors: Mapping[str, Sequence[str]],
    indegree: Mapping[str, int],
    seeds: "PlacementSeeds",
) -> dict[str, int]:
    """Longest path from a source, over the acyclic part.

    A node inside a cycle keeps the layer it was first reached at, which is
    stable because every traversal here is sorted.
    """
    layer = {node_id: 0 for node_id in node_ids}
    remaining = dict(indegree)
    queue = sorted(node_id for node_id in node_ids if remaining[node_id] == 0)
    seen = set(queue)
    while queue:
        current = queue.pop(0)
        for target in sorted(successors[current]):
            layer[target] = max(layer[target], layer[current] + 1)
            if target not in seen:
                seen.add(target)
                queue.append(target)
        queue.sort(key=lambda n: (layer[n], seeds.rank(n), n))
    return layer


def _order_rows(
    rows: dict[int, list[str]],
    successors: Mapping[str, Sequence[str]],
    predecessors: Mapping[str, Sequence[str]],
    seeds: "PlacementSeeds",
) -> None:
    """Reduce crossings by barycentre sweeps, in place.

    A node moves to the average position of the neighbours it is drawn against,
    which is the standard way to untangle a layered drawing. A node with no
    neighbour in the row being swept against keeps where it is, so the pass
    never shuffles anything for no reason, and every tie breaks on the seed and
    then the identifier — so the result is the same on every run.
    """
    for depth in rows:
        rows[depth].sort(key=lambda n: (seeds.rank(n), n))

    depths = sorted(rows)
    for sweep in range(SWEEPS):
        forward = sweep % 2 == 0
        order = depths[1:] if forward else list(reversed(depths[:-1]))
        against = predecessors if forward else successors
        for depth in order:
            neighbour_row = depth - 1 if forward else depth + 1
            index = {n: i for i, n in enumerate(rows.get(neighbour_row, ()))}
            here = {n: i for i, n in enumerate(rows[depth])}
            span = max(len(index) - 1, 1)
            scale = max(len(here) - 1, 1) / span

            def barycentre(node_id: str) -> float:
                positions = [index[n] for n in against[node_id] if n in index]
                if not positions:
                    return float(here[node_id])
                return sum(positions) / len(positions) * scale

            rows[depth].sort(key=lambda n: (barycentre(n), seeds.rank(n), n))


def _stack(
    members: Sequence[str], sizes: Mapping[str, tuple[int, int]]
) -> tuple[dict[str, int], int]:
    """Stack a column top to bottom; return each y and the column height."""
    offsets: dict[str, int] = {}
    y = 0
    for node_id in members:
        offsets[node_id] = y
        y += sizes[node_id][1] + ROW_GAP
    return offsets, max(y - ROW_GAP, 0)


def _grid(
    members: Sequence[str], sizes: Mapping[str, tuple[int, int]], width: int
) -> tuple[dict[str, Position], int, int]:
    """Pack nodes nothing connects to into a grid rather than one long column.

    An unconnected node carries no information about where it belongs, so a
    layered layout has nothing to say about it. Stacking them all in the first
    column, which is what a layering does by default, buries the part of the
    diagram that does carry information.
    """
    if not members:
        return {}, 0, 0
    cell = max(sizes[node_id][0] for node_id in members) + ROW_GAP
    square = int(len(members) ** 0.5 + 0.999)          # keep the block compact
    fits = (width + ROW_GAP) // cell                   # but fill the width it has
    columns = max(1, min(len(members), max(square, fits)))

    positions: dict[str, Position] = {}
    row_height = max(sizes[node_id][1] for node_id in members) + ROW_GAP
    for index, node_id in enumerate(members):
        column, row = index % columns, index // columns
        positions[node_id] = Position(column * cell, row * row_height)
    rows = (len(members) + columns - 1) // columns
    return positions, columns * cell - ROW_GAP, rows * row_height - ROW_GAP


def layered(request: LayoutRequest, seeds: PlacementSeeds | None = None) -> dict[str, Position]:
    """A deterministic layered layout.

    Layers come from the longest path from a source, rows within a layer are
    ordered to reduce crossings, columns are centred against the tallest one,
    and a node this view connects to nothing is packed into a grid below rather
    than left to lengthen the first column. This is a replaceable
    implementation behind the boundary, not a claim to be a good graph-layout
    algorithm.
    """
    seeds = seeds or PlacementSeeds()
    sizes = {node.id: (node.width, node.height) for node in request.nodes}
    successors, predecessors = _adjacency(request)

    connected = sorted(
        node_id for node_id in sizes if successors[node_id] or predecessors[node_id]
    )
    isolated = sorted(node_id for node_id in sizes if node_id not in set(connected))

    indegree = {node_id: len(predecessors[node_id]) for node_id in connected}
    layer = _layers(connected, successors, indegree, seeds)

    rows: dict[int, list[str]] = {}
    for node_id in connected:
        rows.setdefault(layer[node_id], []).append(node_id)
    _order_rows(rows, successors, predecessors, seeds)

    columns = {
        depth: (max(sizes[n][0] for n in members), _stack(members, sizes))
        for depth, members in sorted(rows.items())
    }
    tallest = max((height for _, (_, height) in columns.values()), default=0)

    positions: dict[str, Position] = {}
    x = 0
    for depth, (column_width, (offsets, height)) in sorted(columns.items()):
        top = (tallest - height) // 2
        for node_id, offset in offsets.items():
            # Centre a narrow box in its column, so a column reads as a column.
            indent = (column_width - sizes[node_id][0]) // 2
            positions[node_id] = Position(x + indent, top + offset)
        x += column_width + LAYER_GAP

    width = max(x - LAYER_GAP, 0)
    grid, grid_width, grid_height = _grid(isolated, sizes, width)
    offset = tallest + ISOLATED_GAP if positions else 0
    for node_id, position in grid.items():
        positions[node_id] = Position(position.x, position.y + offset)

    return positions


def content_size(
    positions: Mapping[str, Position], sizes: Mapping[str, tuple[int, int]]
) -> tuple[int, int]:
    """The box the drawing occupies."""
    if not positions:
        return 0, 0
    width = max(position.x + sizes[node_id][0] for node_id, position in positions.items())
    height = max(position.y + sizes[node_id][1] for node_id, position in positions.items())
    return width, height


def place(
    graph: ViewGraph,
    *,
    seeds: PlacementSeeds | None = None,
    hints: Mapping[str, str] | None = None,
) -> PositionedView:
    """Lay a view out and bring the geometry back as a positioned view graph."""
    request = to_request(graph, hints)
    positions = layered(request, seeds)
    sizes = {node.id: (node.width, node.height) for node in request.nodes}
    width, height = content_size(positions, sizes)
    return PositionedView(graph, positions, width, height)
