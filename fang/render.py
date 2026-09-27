"""Rendering a positioned view to SVG.

Spec: "Views Are Deterministic Projections". Rendering stays here rather than in
the layout engine, so the engine is replaceable. The output is deterministic:
the same positioned view renders byte-identically.

The drawing is a block diagram in the manner of a datasheet or a paper: black
ink on a transparent page, square boxes named in capitals, and wires that run
straight and turn square, each ending in an arrow at the box it reaches and
labelled with what it joins. It is meant to be read, not admired. A box carries
the instance name a reader can search the program for; every wire meets a box
at a point of its own and turns in a lane of its own, so two nets never read as
one; a line's weight and dash say its class, since there is no colour to say
it; and the diagram says at the bottom what it does not know.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from .layout import PositionedView, node_sizes

#: How each class of edge is drawn: stroke width and dash. Presentation only.
EDGE_STYLE = {
    "power": ("2.2", ""),
    "ground": ("1.4", "6 3"),
    "signal": ("1.2", ""),
    "electrical": ("1", ""),
    "mechanical": ("1", "1 3"),
    "control": ("1", "7 2 1.5 2"),
    "dependency": ("0.8", "2 3"),
    "containment": ("0.8", "2 3"),
}
DEFAULT_EDGE = ("1", "")

INK = "#000000"
FONT = "Helvetica, Arial, sans-serif"

#: The band under the drawing: the key, what the diagram does not know, and
#: the title with the question the view answers. All of it is part of the
#: view, not decoration.
LEGEND_ROW = 16
FOOTER_LINE = 14
TITLE = 42

#: Where a wire turns: its lane in the gap before the box it reaches, the
#: first this far out and each next one a step further.
LANE_START = 18
LANE_STEP = 7

#: How far from a box a wire crossing between two rows of them runs.
ROW_CLEAR = 14


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _legend(classes: Iterable[str], x: int, y: int, width: int) -> tuple[list[str], int]:
    """A key to the line styles actually used, wrapped to the width."""
    parts: list[str] = []
    cursor, rows = x, 0
    for edge_class in classes:
        stroke, dash = EDGE_STYLE.get(edge_class, DEFAULT_EDGE)
        name = edge_class.upper()
        span = 34 + len(name) * 6 + 18
        if cursor > x and cursor + span > x + width:
            cursor, rows = x, rows + 1
        top = y + rows * LEGEND_ROW
        dashed = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(
            f'<line x1="{cursor}" y1="{top}" x2="{cursor + 26}" y2="{top}" '
            f'stroke="{INK}" stroke-width="{stroke}"{dashed}/>'
        )
        parts.append(
            f'<text x="{cursor + 32}" y="{top + 3.5}" font-size="9.5" fill="{INK}">'
            f"{_escape(name)}</text>"
        )
        cursor += span
    return parts, rows + 1 if parts else 0


def to_svg(positioned: PositionedView, *, padding: int = 28) -> str:
    """Render a positioned view. Deterministic for identical input."""
    graph = positioned.graph
    sizes: Mapping[str, tuple[int, int]] = node_sizes(graph)
    top = padding

    def box(node_id: str) -> tuple[int, int, int, int]:
        position = positioned.positions[node_id]
        node_width, node_height = sizes[node_id]
        return position.x + padding, position.y + top, node_width, node_height

    drawn = [
        edge
        for edge in sorted(graph.edges, key=lambda e: (e.source, e.target, e.id))
        if edge.source != edge.target
        and edge.source in positioned.positions
        and edge.target in positioned.positions
    ]

    # Which side of each box every wire meets. A wire going right leaves its
    # source on the right and reaches its target on the left; going left, the
    # other way round; between two boxes in one column it goes round the
    # outside, on the right of both.
    def sides(edge) -> tuple[str, str]:
        sx, _, sw, _ = box(edge.source)
        tx, _, tw, _ = box(edge.target)
        if tx >= sx + sw:
            return "right", "left"
        if sx >= tx + tw:
            return "left", "right"
        return "right", "right"

    # Each wire gets a point of its own on each side it meets, spread evenly
    # down that side in the order of where the wire is going, so neighbours on
    # a side do not have to cross to get there.
    meeting: dict[tuple[str, str], list[tuple[float, str, str]]] = {}
    for edge in drawn:
        source_side, target_side = sides(edge)
        for end, side, other in (
            (edge.source, source_side, edge.target),
            (edge.target, target_side, edge.source),
        ):
            _, oy, _, oh = box(other)
            meeting.setdefault((end, side), []).append((oy + oh / 2, other, edge.id))
    slot: dict[tuple[str, str, str], float] = {}
    for (node_id, side), wires in meeting.items():
        _, y, _, height = box(node_id)
        wires.sort()
        for index, (_, _, edge_id) in enumerate(wires):
            slot[(node_id, side, edge_id)] = y + height * (index + 1) / (len(wires) + 1)

    # Each wire turns in a lane of its own, in the gap beside the box it turns
    # towards, so two wires never share a vertical run.
    lanes: dict[tuple[str, int], int] = {}

    def lane(key: tuple[str, int]) -> int:
        lanes[key] = lanes.get(key, -1) + 1
        return lanes[key]

    placed = [box(node_id) for node_id in positioned.positions]

    def blocked(y: float, left: float, right: float, ends: tuple) -> bool:
        """Whether a horizontal run at `y` between two xs would cross a box."""
        for b in placed:
            if b in ends:
                continue
            bx, by, bw, bh = b
            if bx < right and bx + bw > left and by - 3 <= y <= by + bh + 3:
                return True
        return False

    def channel(y: float, left: float, right: float, ends: tuple) -> float:
        """The clear height nearest `y` to run a wire across, between boxes."""
        if not blocked(y, left, right, ends):
            return y
        candidates = []
        for bx, by, bw, bh in placed:
            if bx < right and bx + bw > left:
                candidates += [by - ROW_CLEAR, by + bh + ROW_CLEAR]
        clear = [c for c in candidates if not blocked(c, left, right, ends)]
        return min(clear, key=lambda c: (abs(c - y), c)) if clear else y

    wires_svg: list[str] = []
    labels: list[str] = []
    reach = 0.0
    for edge in drawn:
        sx, sy, sw, sh = box(edge.source)
        tx, ty, tw, th = box(edge.target)
        source_side, target_side = sides(edge)
        y1 = slot[(edge.source, source_side, edge.id)]
        y2 = slot[(edge.target, target_side, edge.id)]
        detour: tuple[float, float, float] | None = None
        if source_side == "right" and target_side == "left":
            x1, x2 = sx + sw, tx
            turn = x2 - LANE_START - lane(("before", tx)) * LANE_STEP
            label_x, anchor = x1 + 5, "start"
            # A wire that would run through a box on its way crosses in the
            # nearest clear channel instead: out of its source, down or up
            # into the channel, across, and up or down again before its target.
            ends = (box(edge.source), box(edge.target))
            if blocked(y1, x1 + LANE_START, turn, ends):
                out = x1 + LANE_START + lane(("after", sx + sw)) * LANE_STEP
                detour = (out, channel(y1, out, turn, ends), turn)
        elif source_side == "left":
            x1, x2 = sx, tx + tw
            turn = x1 - LANE_START - lane(("before", sx)) * LANE_STEP
            label_x, anchor = x1 - 5, "end"
        else:
            x1, x2 = sx + sw, tx + tw
            turn = max(x1, x2) + LANE_START + lane(("after", max(x1, x2))) * LANE_STEP
            label_x, anchor = x1 + 5, "start"
        reach = max(reach, x1, x2, turn)

        stroke, dash = EDGE_STYLE.get(edge.edge_class, DEFAULT_EDGE)
        dashed = f' stroke-dasharray="{dash}"' if dash else ""
        if detour is not None:
            out, across, turn = detour
            points = (
                f"{x1:.1f},{y1:.1f} {out:.1f},{y1:.1f} {out:.1f},{across:.1f} "
                f"{turn:.1f},{across:.1f} {turn:.1f},{y2:.1f} {x2:.1f},{y2:.1f}"
            )
        else:
            points = f"{x1:.1f},{y1:.1f} {turn:.1f},{y1:.1f} {turn:.1f},{y2:.1f} {x2:.1f},{y2:.1f}"
        wires_svg.append(
            f'<polyline points="{points}" fill="none" stroke="{INK}" '
            f'stroke-width="{stroke}"{dashed} marker-start="url(#arrow)" marker-end="url(#arrow)">'
            f"<title>{_escape(edge.edge_class)}: {_escape(edge.id)}</title></polyline>"
        )
        if edge.label:
            labels.append(
                f'<text x="{label_x:.1f}" y="{y1 - 2.5:.1f}" text-anchor="{anchor}" '
                f'font-size="8" fill="{INK}">{_escape(edge.label.upper())}</text>'
            )

    classes = sorted({edge.edge_class for edge in drawn})
    footer_lines = list(graph.notes)
    if not graph.complete:
        gaps = graph.completeness()["nodes_with_unknowns"]
        footer_lines.append(
            f"{gaps} node(s) carry unknown parameters; a dashed border marks them"
        )

    width = int(max(positioned.width + padding * 2, reach + padding, 460))
    base = top + positioned.height + padding
    legend, legend_rows = _legend(classes, padding, base, width - padding * 2)
    notes_top = base + legend_rows * LEGEND_ROW + 4
    title_top = notes_top + len(footer_lines) * FOOTER_LINE + 12
    height = title_top + TITLE

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="{FONT}">',
        f"<title>{_escape(graph.spec.name)}: {_escape(graph.spec.question)}</title>",
        # One arrowhead, turned to face along the wire at either end.
        '<defs><marker id="arrow" viewBox="0 0 8 8" refX="7.5" refY="4" '
        'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        f'<path d="M0,0.8 L8,4 L0,7.2 Z" fill="{INK}"/></marker></defs>',
    ]

    # The rule over the nodes this view joins to nothing. Their being there is a
    # fact about the view: an interface nothing connects, on the diagram that
    # answers what connects to what, is worth seeing, not worth hiding.
    joined = {node for edge in drawn for node in (edge.source, edge.target)}
    loose = [node.id for node in graph.nodes if node.id not in joined]
    if loose and joined:
        rule = min(box(node_id)[1] for node_id in loose) - 26
        parts.append(
            f'<line x1="{padding}" y1="{rule}" x2="{width - padding}" y2="{rule}" '
            f'stroke="{INK}" stroke-width="0.6" stroke-dasharray="2 4"/>'
        )
        parts.append(
            f'<text x="{padding}" y="{rule - 7}" font-size="9" fill="{INK}">'
            "NOTHING IN THIS VIEW CONNECTS TO THESE</text>"
        )

    parts.extend(wires_svg)

    for node in sorted(graph.nodes, key=lambda n: n.id):
        if node.id not in positioned.positions:
            continue
        x, y, node_width, node_height = box(node.id)
        # A node with unknowns is drawn dashed: the diagram shows its own gaps.
        dashed = ' stroke-dasharray="5 3"' if node.incomplete else ""
        tooltip = _escape(node.id)
        if node.incomplete:
            tooltip += ", unknown: " + _escape(", ".join(node.incomplete))
        centre = x + node_width // 2
        middle = y + node_height / 2
        detail = node.detail or node.kind
        parts.append(
            f'<g><rect x="{x}" y="{y}" width="{node_width}" height="{node_height}" '
            f'fill="none" stroke="{INK}" stroke-width="1.2"{dashed}/>'
            f'<text x="{centre}" y="{middle - 1:.1f}" text-anchor="middle" '
            f'font-size="12" font-weight="bold" fill="{INK}">{_escape(node.label.upper())}</text>'
            f'<text x="{centre}" y="{middle + 12:.1f}" text-anchor="middle" '
            f'font-size="9" fill="{INK}">({_escape(detail.upper())})</text>'
            f"<title>{tooltip}</title></g>"
        )

    parts.extend(labels)
    parts.extend(legend)
    for index, line in enumerate(footer_lines):
        parts.append(
            f'<text x="{padding}" y="{notes_top + index * FOOTER_LINE + 10}" '
            f'font-size="9.5" fill="{INK}">{_escape(line)}</text>'
        )
    parts.append(
        f'<text x="{width / 2:.1f}" y="{title_top + 14}" text-anchor="middle" '
        f'font-size="13" font-weight="bold" letter-spacing="0.08em" fill="{INK}">'
        f"{_escape(graph.spec.name.upper())}</text>"
    )
    parts.append(
        f'<text x="{width / 2:.1f}" y="{title_top + 30}" text-anchor="middle" '
        f'font-size="10" font-style="italic" fill="{INK}">{_escape(graph.spec.question)}</text>'
    )

    parts.append("</svg>")
    return "\n".join(parts) + "\n"
