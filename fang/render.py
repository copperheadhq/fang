"""Rendering a positioned view to SVG.

Spec: "Views Are Deterministic Projections". Rendering stays here rather than in
the layout engine, so the engine is replaceable. The output is deterministic:
the same positioned view renders byte-identically.

The drawing is meant to be read, not admired. Every choice here serves that: a
box carries the instance name a reader can search the program for, an edge
leaves the side of the box it is going towards rather than cutting through it,
parallel edges fan out so three connections do not look like one, and the
diagram says at the bottom what it does not know.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from .layout import PositionedView, box_size

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
DEFAULT_EDGE = ("#5f6368", "1.5")

NODE_FILL = {
    "component": "#ffffff",
    "block": "#f1f3f4",
    "interface": "#e8f0fe",
    "net": "#fef7e0",
    "domain": "#e6f4ea",
    "requirement": "#fce8e6",
    "rail": "#fef7e0",
}
DEFAULT_FILL = "#ffffff"

INK = "#1b1b1f"
MUTED = "#5f6368"
LINE = "#c4c7cc"
ALARM = "#b3261e"

#: Bands above and below the drawing: the question it answers, and what it
#: does not know. Both are part of the view, not decoration.
HEADER = 54
LEGEND_ROW = 18
FOOTER_LINE = 16

#: How far apart parallel edges between the same pair of boxes are fanned.
FAN = 7


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _pair(source: str, target: str) -> tuple[str, str]:
    return (source, target) if source <= target else (target, source)


def _fan(index: int, total: int) -> float:
    """Where the n-th of several edges between one pair of boxes attaches."""
    return (index - (total - 1) / 2) * FAN


def _path(
    source: tuple[int, int, int, int],
    target: tuple[int, int, int, int],
    offset: float,
) -> tuple[str, float]:
    """A curve from one box to another, and how far right it reaches.

    An edge leaves the side of the box it is heading for, so it arrives at a
    box rather than crossing it. Left to right where the layering put the
    target to the right, and around the outside when the two boxes share a
    column. The reach comes back with the path because a curve that bulges
    past the drawing has to be paid for in canvas width.
    """
    sx, sy, sw, sh = source
    tx, ty, tw, th = target
    sy_mid = sy + sh / 2 + offset
    ty_mid = ty + th / 2 + offset

    if tx >= sx + sw:                      # the ordinary case: forward
        x1, x2 = sx + sw, tx
        bend = max(28.0, (x2 - x1) * 0.45)
        control = (x1 + bend, x2 - bend)
    elif sx >= tx + tw:                    # backwards
        x1, x2 = sx, tx + tw
        bend = max(28.0, (x1 - x2) * 0.45)
        control = (x1 - bend, x2 + bend)
    else:                                  # same column: around the outside
        x1, x2 = sx + sw, tx + tw
        bend = 40.0 + abs(offset) * 2 + abs(sy_mid - ty_mid) * 0.25
        control = (x1 + bend, x2 + bend)

    path = (
        f"M{x1:.1f},{sy_mid:.1f} C{control[0]:.1f},{sy_mid:.1f} "
        f"{control[1]:.1f},{ty_mid:.1f} {x2:.1f},{ty_mid:.1f}"
    )
    # A cubic reaches at most three quarters of the way to its control points.
    return path, max(x1, x2, x1 + (control[0] - x1) * 0.75, x2 + (control[1] - x2) * 0.75)


def _legend(classes: Iterable[str], x: int, y: int, width: int) -> tuple[list[str], int]:
    """A key for the edge colours actually used, wrapped to the width."""
    parts: list[str] = []
    cursor, rows = x, 0
    for edge_class in classes:
        colour, stroke = EDGE_STYLE.get(edge_class, DEFAULT_EDGE)
        span = 26 + len(edge_class) * 6 + 18
        if cursor > x and cursor + span > x + width:
            cursor, rows = x, rows + 1
        top = y + rows * LEGEND_ROW
        parts.append(
            f'<line x1="{cursor}" y1="{top}" x2="{cursor + 20}" y2="{top}" '
            f'stroke="{colour}" stroke-width="{stroke}" stroke-linecap="round"/>'
        )
        parts.append(
            f'<text x="{cursor + 26}" y="{top + 4}" font-size="11" fill="{MUTED}">'
            f"{_escape(edge_class)}</text>"
        )
        cursor += span
    return parts, rows + 1 if parts else 0


def to_svg(positioned: PositionedView, *, padding: int = 28) -> str:
    """Render a positioned view. Deterministic for identical input."""
    graph = positioned.graph
    sizes: Mapping[str, tuple[int, int]] = {
        node.id: box_size(node.label, node.detail) for node in graph.nodes
    }
    top = HEADER

    def box(node_id: str) -> tuple[int, int, int, int]:
        position = positioned.positions[node_id]
        node_width, node_height = sizes[node_id]
        return position.x + padding, position.y + top, node_width, node_height

    # Edges are drawn first, so the nodes sit above them. Edges between the same
    # two boxes are counted so they can be fanned apart rather than drawn on top
    # of one another: three gate drives are three lines or they are not the truth.
    drawn = [
        edge
        for edge in sorted(graph.edges, key=lambda e: (e.source, e.target, e.id))
        if edge.source != edge.target
        and edge.source in positioned.positions
        and edge.target in positioned.positions
    ]
    counts: dict[tuple[str, str], int] = {}
    for edge in drawn:
        key = _pair(edge.source, edge.target)
        counts[key] = counts.get(key, 0) + 1

    wires: list[str] = []
    reach = 0.0
    seen: dict[tuple[str, str], int] = {}
    for edge in drawn:
        key = _pair(edge.source, edge.target)
        index = seen.get(key, 0)
        seen[key] = index + 1
        colour, stroke = EDGE_STYLE.get(edge.edge_class, DEFAULT_EDGE)
        path, extent = _path(box(edge.source), box(edge.target), _fan(index, counts[key]))
        reach = max(reach, extent)
        wires.append(
            f'<path d="{path}" fill="none" stroke="{colour}" stroke-width="{stroke}" '
            f'stroke-linecap="round" opacity="0.85">'
            f"<title>{_escape(edge.edge_class)}: {_escape(edge.id)}</title></path>"
        )

    classes = sorted({edge.edge_class for edge in graph.edges})
    footer_lines = list(graph.notes)
    if not graph.complete:
        gaps = graph.completeness()["nodes_with_unknowns"]
        footer_lines.append(
            f"{gaps} node(s) carry unknown parameters; a dashed border marks them"
        )

    width = max(positioned.width + padding * 2, int(reach) + padding, 460)
    base = top + positioned.height + padding
    legend, legend_rows = _legend(classes, padding, base, width - padding * 2)
    notes_top = base + legend_rows * LEGEND_ROW
    height = notes_top + len(footer_lines) * FOOTER_LINE + padding

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="system-ui, sans-serif">',
        f"<title>{_escape(graph.spec.name)}: {_escape(graph.spec.question)}</title>",
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{padding}" y="26" font-size="15" font-weight="600" fill="{INK}">'
        f"{_escape(graph.spec.name)}</text>",
        f'<text x="{padding}" y="43" font-size="11.5" fill="{MUTED}">'
        f"{_escape(graph.spec.question)}</text>",
    ]

    # The rule over the nodes this view joins to nothing. Their being there is a
    # fact about the view — an interface nothing connects on the diagram that
    # answers what connects to what is worth seeing, not worth hiding.
    joined = {node for edge in drawn for node in (edge.source, edge.target)}
    loose = [node.id for node in graph.nodes if node.id not in joined]
    if loose and joined:
        rule = min(box(node_id)[1] for node_id in loose) - 26
        parts.append(
            f'<line x1="{padding}" y1="{rule}" x2="{width - padding}" y2="{rule}" '
            f'stroke="{LINE}" stroke-width="1" stroke-dasharray="3 4"/>'
        )
        parts.append(
            f'<text x="{padding}" y="{rule - 8}" font-size="11" fill="{MUTED}">'
            "nothing in this view connects to these</text>"
        )

    parts.extend(wires)

    for node in sorted(graph.nodes, key=lambda n: n.id):
        if node.id not in positioned.positions:
            continue
        x, y, node_width, node_height = box(node.id)
        fill = NODE_FILL.get(node.kind, DEFAULT_FILL)
        # A node with unknowns is drawn dashed: the diagram shows its own gaps.
        outline = (
            f'stroke="{ALARM}" stroke-dasharray="4 3"'
            if node.incomplete
            else f'stroke="{LINE}"'
        )
        tooltip = _escape(node.id)
        if node.incomplete:
            tooltip += " — unknown: " + _escape(", ".join(node.incomplete))
        centre = x + node_width // 2
        parts.append(
            f'<g><rect x="{x}" y="{y}" width="{node_width}" height="{node_height}" '
            f'rx="8" fill="{fill}" {outline} stroke-width="1"/>'
            f'<text x="{centre}" y="{y + 26}" text-anchor="middle" '
            f'font-size="13" font-weight="500" fill="{INK}">{_escape(node.label)}</text>'
            f'<text x="{centre}" y="{y + 43}" text-anchor="middle" '
            f'font-size="10.5" fill="{MUTED}">{_escape(node.detail or node.kind)}</text>'
            f"<title>{tooltip}</title></g>"
        )

    parts.extend(legend)
    for index, line in enumerate(footer_lines):
        colour = ALARM if "unknown parameters" in line else MUTED
        parts.append(
            f'<text x="{padding}" y="{notes_top + index * FOOTER_LINE + 10}" '
            f'font-size="11" fill="{colour}">{_escape(line)}</text>'
        )

    parts.append("</svg>")
    return "\n".join(parts) + "\n"
