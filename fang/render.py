"""Rendering a positioned view to SVG.

Spec: "Views Are Deterministic Projections". Rendering stays here rather than in
the layout engine, so the engine is replaceable. The output is deterministic:
the same positioned view renders byte-identically.
"""

from __future__ import annotations

from typing import Iterable

from .layout import NODE_HEIGHT, NODE_WIDTH, PositionedView

#: Edge colours by class. Presentation only.
EDGE_STYLE = {
    "power": ("#b3261e", "2"),
    "ground": ("#1b1b1f", "2"),
    "signal": ("#1a73e8", "1.5"),
    "electrical": ("#5f6368", "1.5"),
    "mechanical": ("#8a8a8a", "1.5"),
    "control": ("#7b1fa2", "1.5"),
    "dependency": ("#9aa0a6", "1"),
    "containment": ("#9aa0a6", "1"),
}

NODE_FILL = {
    "component": "#ffffff",
    "block": "#f1f3f4",
    "interface": "#e8f0fe",
    "net": "#fef7e0",
    "domain": "#e6f4ea",
    "requirement": "#fce8e6",
    "rail": "#fef7e0",
}


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def to_svg(positioned: PositionedView, *, padding: int = 24) -> str:
    """Render a positioned view. Deterministic for identical input."""
    graph = positioned.graph
    width = positioned.width + padding * 2
    height = positioned.height + padding * 2

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="system-ui, sans-serif">',
        f"<title>{_escape(graph.spec.name)}: {_escape(graph.spec.question)}</title>",
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
    ]

    def centre(node_id: str) -> tuple[int, int]:
        position = positioned.positions[node_id]
        return (
            position.x + padding + NODE_WIDTH // 2,
            position.y + padding + NODE_HEIGHT // 2,
        )

    # Edges first, so nodes sit above them.
    for edge in sorted(graph.edges, key=lambda e: e.id):
        if edge.source not in positioned.positions or edge.target not in positioned.positions:
            continue
        colour, stroke = EDGE_STYLE.get(edge.edge_class, ("#5f6368", "1.5"))
        x1, y1 = centre(edge.source)
        x2, y2 = centre(edge.target)
        parts.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{colour}" '
            f'stroke-width="{stroke}"><title>{_escape(edge.edge_class)}</title></line>'
        )

    for node in sorted(graph.nodes, key=lambda n: n.id):
        if node.id not in positioned.positions:
            continue
        position = positioned.positions[node.id]
        x, y = position.x + padding, position.y + padding
        fill = NODE_FILL.get(node.kind, "#ffffff")
        # A node with unknowns is drawn dashed: the diagram shows its own gaps.
        dash = ' stroke-dasharray="4 3"' if node.incomplete else ""
        parts.append(
            f'<g><rect x="{x}" y="{y}" width="{NODE_WIDTH}" height="{NODE_HEIGHT}" '
            f'rx="6" fill="{fill}" stroke="#1b1b1f" stroke-width="1"{dash}/>'
            f'<text x="{x + NODE_WIDTH // 2}" y="{y + 24}" text-anchor="middle" '
            f'font-size="13" fill="#1b1b1f">{_escape(node.label)}</text>'
            f'<text x="{x + NODE_WIDTH // 2}" y="{y + 42}" text-anchor="middle" '
            f'font-size="10" fill="#5f6368">{_escape(node.kind)}</text>'
            f"<title>{_escape(node.id)}</title></g>"
        )

    if not graph.complete:
        gaps = graph.completeness()["nodes_with_unknowns"]
        parts.append(
            f'<text x="{padding}" y="{height - 8}" font-size="11" fill="#b3261e">'
            f"{gaps} node(s) carry unknown parameters; a dashed border marks them"
            "</text>"
        )

    parts.append("</svg>")
    return "\n".join(parts) + "\n"
