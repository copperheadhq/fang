"""Draw the schematics of the textbook examples with copperhead's drafting engine.

    python examples/draw_figures.py [example ...]

Every example in a group named in `regenerate.FIGURES` (the op amp handbook's
and the JEE Advanced questions) has its schematic drawn here rather than by
fang. Copperhead is not a dependency of fang, so this is not part of
`examples/regenerate.py` and the test suite does not run it. It needs a
copperhead checkout (`COPPERHEAD_DIR`, default `~/copperhead`) with its
dependencies installed, `npx`, and `kicad-cli`.

For each example it writes `figure/` beside the example's `out/`:

    figure/schematic.intent.json   what copperhead was asked to draw
    figure/<name>.kicad_sch        the sheet it drew
    figure/schematic.svg           KiCad's render of the sheet, cut to the circuit

The intent is the kernel's: `fang.copperhead.compile_intent`, the lowering
`fang schematic --drafter copperhead` runs, called with the labelling a figure
asks for (`OPTIONS` below). Which KiCad symbol draws each part, and which of
its pins each of the part's lands on, is the lowering's and not this script's.
A sheet is written only if KiCad reads back from it exactly the connections
the intent has: a drawing that joined two nets, or dropped a pin, is refused
rather than shipped.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

EXAMPLES = Path(__file__).resolve().parent
sys.path.insert(0, str(EXAMPLES))
sys.path.insert(0, str(EXAMPLES.parent))

from regenerate import FIGURES, PROJECT, _program, examples  # noqa: E402

from fang.cli import load_system  # noqa: E402
from fang.copperhead import (  # noqa: E402
    Intent,
    compile_intent,
    drawn_connections,
    intended_connections,
    powered_names,
)
from fang.elaborate import elaborate  # noqa: E402

COPPERHEAD = Path(os.environ.get("COPPERHEAD_DIR", Path.home() / "copperhead"))

#: How a figure is labelled, passed to the kernel's own lowering: every part
#: in one group, the ground net named GND, each terminal labelled with its name
#: in the program and its net named after it, values as a schematic prints
#: them, and a fixed date, so the same circuit draws the same bytes on any day.
#: Which symbol draws which part, and on which of its pins, is the lowering's
#: (`fang.copperhead.symbol_of`), the same for a figure as for
#: `fang schematic --drafter copperhead`.
OPTIONS = {
    "group": "Circuit",
    "ground": "GND",
    "terminal_names": True,
    "short_values": True,
    "date": "2026-01-01",
}


def intent(name: str) -> Intent:
    """The circuit as copperhead's schematic intent."""
    result = elaborate(load_system(_program(name)), project_id=PROJECT)
    return compile_intent(result.snapshot, traits=result.traits, **OPTIONS)


#: Room left around the drawing when the render is cut to it, in millimetres.
MARGIN = 2.54
#: How wide a character of KiCad's 1.27 mm stroke font is, near enough.
TEXT_WIDTH = 1.1


def _top_level(text: str) -> list[str]:
    """The sheet's top-level items, as text, each starting on its own line."""
    items, depth, start = [], 0, None
    for index, char in enumerate(text):
        if char == "(":
            depth += 1
            if depth == 2:
                start = index
        elif char == ")":
            if depth == 2 and start is not None:
                items.append(text[start : index + 1])
            depth -= 1
    return items


def _render(sheet: Path, work: Path) -> str:
    """KiCad's render of the sheet with nothing but the circuit on it.

    The drawing sheet's frame and title block, the page colour, and the box
    copperhead draws around a group are left out: there is one group, so the
    box encloses everything and says nothing. The page is then cut down to the
    drawing, since KiCad renders the whole sheet it chose."""
    text = sheet.read_text()
    kept = [
        item for item in _top_level(text)
        if not item.startswith(("(rectangle", '(text "Circuit"'))
    ]
    bare = work / "bare" / sheet.name
    bare.parent.mkdir()
    bare.write_text("(kicad_sch\n\t" + "\n\t".join(kept) + "\n)\n")
    subprocess.run(
        ["kicad-cli", "sch", "export", "svg", "--exclude-drawing-sheet",
         "--no-background-color", "-o", str(work / "svg"), str(bare)],
        capture_output=True, check=True,
    )
    svg = (work / "svg" / f"{sheet.stem}.svg").read_text()

    # Every point placed on the page, outside the symbol library, bounds it,
    # and so does every piece of text, which runs on from the point it is
    # anchored at. Its length is estimated, generously, in both directions
    # along its axis: a little too much room costs less than a clipped label.
    points = []
    for item in kept:
        if item.startswith("(lib_symbols"):
            continue
        for x, y in re.findall(r"\((?:at|xy|start|end) (-?[\d.]+) (-?[\d.]+)", item):
            points.append((float(x), float(y)))
        for words, x, y, angle, rest in re.findall(
            r'\((?:label|global_label|hierarchical_label|property "[^"]*"|text) '
            r'"([^"]*)"[^()]*(?:\([^()]*\)[^()]*)*?\(at (-?[\d.]+) (-?[\d.]+) (\d+)\)'
            r"([^\n]*)",
            item,
        ):
            if "(hide yes)" in rest:
                continue
            reach = len(words) * TEXT_WIDTH + TEXT_WIDTH * 3
            x, y = float(x), float(y)
            if int(angle) % 180:
                points += [(x, y - reach), (x, y + reach)]
            else:
                points += [(x - reach, y), (x + reach, y)]
    left = min(x for x, _ in points) - MARGIN
    top = min(y for _, y in points) - MARGIN
    width = max(x for x, _ in points) + MARGIN - left
    height = max(y for _, y in points) + MARGIN - top
    return re.sub(
        r'width="[^"]*" height="[^"]*" viewBox="[^"]*"',
        f'width="{width:.4f}mm" height="{height:.4f}mm" '
        f'viewBox="{left:.4f} {top:.4f} {width:.4f} {height:.4f}"',
        svg,
        count=1,
    )


def draw(name: str) -> str:
    stem = Path(name).name
    figure = EXAMPLES / name / "figure"
    drawn = intent(name)
    # A figure shows the whole circuit; one that would lose a part or a net
    # is not drawn with the gap.
    if drawn.losses:
        return f"{name}: the intent loses " + "; ".join(drawn.losses)
    with tempfile.TemporaryDirectory() as scratch:
        work = Path(scratch)
        (work / "schematic.intent.json").write_text(drawn.text(), encoding="utf-8")
        drafted = subprocess.run(
            ["npx", "tsx", str(EXAMPLES / "draft_figure.mts"), str(COPPERHEAD), str(work), stem],
            cwd=COPPERHEAD, capture_output=True, text=True,
        )
        if drafted.returncode:
            return f"{name}: copperhead refused\n  " + drafted.stderr.strip().replace("\n", "\n  ")
        sheet = work / f"{stem}.kicad_sch"
        subprocess.run(
            ["kicad-cli", "sch", "export", "netlist", "-o", str(work / "back.net"), str(sheet)],
            capture_output=True, check=True,
        )
        back = drawn_connections((work / "back.net").read_text(), powered_names(drawn))
        if back != intended_connections(drawn):
            return f"{name}: the drawing does not have the circuit's connections; not written"
        render = _render(sheet, work)
        figure.mkdir(exist_ok=True)
        (figure / "schematic.intent.json").write_text(drawn.text(), encoding="utf-8")
        (figure / f"{stem}.kicad_sch").write_text(sheet.read_text())
        (figure / "schematic.svg").write_text(render)
    return f"{name}: drawn"


def main(argv: list[str]) -> int:
    names = [n for n in examples() if n.startswith(FIGURES)]
    if argv:
        names = [n for n in names if Path(n).name in argv or n in argv]
    failed = 0
    for name in names:
        line = draw(name)
        failed += not line.endswith(": drawn")
        print(line)
    print(f"{len(names) - failed} of {len(names)} drawn")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
