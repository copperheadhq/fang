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
NODE_WIDTH = 160
NODE_HEIGHT = 56
LAYER_GAP = 96
ROW_GAP = 32


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


def to_request(graph: ViewGraph, hints: Mapping[str, str] | None = None) -> LayoutRequest:
    """Strip a view graph down to what layout may see."""
    return LayoutRequest(
        tuple(
            LayoutNode(node.id, ports=node.ports, parent=node.parent)
            for node in graph.nodes
        ),
        tuple(LayoutEdge(edge.id, edge.source, edge.target) for edge in graph.edges),
        dict(hints or {}),
    )


def layered(request: LayoutRequest, seeds: PlacementSeeds | None = None) -> dict[str, Position]:
    """A deterministic layered layout.

    Layers come from the longest path from a source; ordering within a layer is
    by placement seed and then by identifier, so the same graph always lays out
    the same way. This is a replaceable implementation behind the boundary, not
    a claim to be a good graph-layout algorithm.
    """
    seeds = seeds or PlacementSeeds()
    node_ids = [node.id for node in request.nodes]
    successors: dict[str, list[str]] = {node_id: [] for node_id in node_ids}
    indegree: dict[str, int] = {node_id: 0 for node_id in node_ids}

    for edge in request.edges:
        if edge.source in successors and edge.target in indegree and edge.source != edge.target:
            successors[edge.source].append(edge.target)
            indegree[edge.target] += 1

    # Longest-path layering over the acyclic part; a node in a cycle keeps the
    # layer it first reached, which is stable because the traversal is sorted.
    layer: dict[str, int] = {node_id: 0 for node_id in node_ids}
    queue = sorted(node_id for node_id in node_ids if indegree[node_id] == 0)
    seen: set[str] = set(queue)
    while queue:
        current = queue.pop(0)
        for target in sorted(successors[current]):
            layer[target] = max(layer[target], layer[current] + 1)
            if target not in seen:
                seen.add(target)
                queue.append(target)
        queue.sort(key=lambda n: (layer[n], seeds.rank(n), n))

    rows: dict[int, list[str]] = {}
    for node_id in node_ids:
        rows.setdefault(layer[node_id], []).append(node_id)

    positions: dict[str, Position] = {}
    for depth, members in sorted(rows.items()):
        members.sort(key=lambda n: (seeds.rank(n), n))
        for index, node_id in enumerate(members):
            positions[node_id] = Position(
                x=depth * (NODE_WIDTH + LAYER_GAP),
                y=index * (NODE_HEIGHT + ROW_GAP),
            )
    return positions


def place(
    graph: ViewGraph,
    *,
    seeds: PlacementSeeds | None = None,
    hints: Mapping[str, str] | None = None,
) -> PositionedView:
    """Lay a view out and bring the geometry back as a positioned view graph."""
    request = to_request(graph, hints)
    positions = layered(request, seeds)
    width = max((p.x for p in positions.values()), default=0) + NODE_WIDTH + LAYER_GAP
    height = max((p.y for p in positions.values()), default=0) + NODE_HEIGHT + ROW_GAP
    return PositionedView(graph, positions, width, height)
