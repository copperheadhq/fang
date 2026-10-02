"""Draw the social renders for firmware emulation, from runs made as they are drawn.

Every number on these images comes from running `examples/sensor_node/` in
Renode when the script runs, through `fang.verification.answer` — the path
`fang verify` takes — and every requirement beside a number is read from the
constraints the program declares. Nothing is typed in by hand, so an image
cannot claim a result the board and its firmware do not produce. The runs are
the good build's two questions and the three deliberately broken builds beside
it in `firmware/elf/`; Renode's runs are deterministic, so the images are too.

It needs what the brand assets need, plus Renode 1.17.0 on the path:

    pip install pillow "fonttools[woff]"
    python site/social/make.py

The type, the mark and the palette are `site/brand/make.py`'s, imported rather
than restated, and pass and fail are the brand's semantic colours, never the
accent.
"""

from __future__ import annotations

import importlib.util
import re
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
EXAMPLE = ROOT / "examples" / "sensor_node"
ELF = EXAMPLE / "firmware" / "elf"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


brand = _load("fang_brand", HERE.parent / "brand" / "make.py")
SS = brand.SS
GROUND, RAISED, HAIRLINE = brand.GROUND, "#232425", brand.HAIRLINE
TEXT, MUTED, DIM = brand.TEXT, "#b3b8be", brand.DIM
ACCENT, ACCENT_TEXT, COPPER = brand.ACCENT, brand.ACCENT_TEXT, brand.COPPER
PASS, FAIL = "#6fbf73", "#d56b62"
DOMAIN = brand.DOMAIN


# --------------------------------------------------------------------------
# The runs
# --------------------------------------------------------------------------

#: The builds, in the order the images list them: the one that ships, then
#: each broken one with the question it fails and what is wrong with it.
BUILDS = (
    ("sensor_node.elf", None, "the build that ships"),
    ("wrong_address.elf", "startup", "addresses the sensor at the wrong I2C address"),
    ("push_pull.elf", "startup", "drives the I2C pins push-pull, not open drain"),
    ("no_timeout.elf", "sensor_missing", "waits forever on a sensor that is not there"),
)


@dataclass(frozen=True)
class Measure:
    name: str
    shown: str              # the measured value as a person reads it
    required: str           # the program's requirement over it
    met: bool | None        # None: the run left it undecided


@dataclass(frozen=True)
class Run:
    build: str
    question: str
    result: str
    lines: tuple[str, ...]  # fang verify's listing, without machine details
    measures: dict[str, Measure]
    version: str


def _program():
    return _load("sensor_node_for_social", EXAMPLE / "sensor_node.py")


def _variant(program, question: str, firmware: Path):
    """The board with one question's firmware replaced, as the tests build it."""
    from fang.emulation import Emulates

    original = getattr(program.SensorNode, question)
    fields = dict(
        run_until=original.run_until, measures=original.measures,
        abstracted=original.abstracted, firmware=str(firmware),
    )
    if original.stimuli:
        fields["stimuli"] = original.stimuli
    if original.faults:
        fields["faults"] = original.faults
    return type("Variant", (program.SensorNode,), {
        question: Emulates(original.verifies, **fields),
    })


def _requirements(snapshot) -> dict[str, list[tuple[str, object]]]:
    """Each measured parameter's bounds, read from the hard constraints over it."""
    from fang.constraints import Comparison, Constraint, Literal, Ref

    bounds: dict[str, list[tuple[str, object]]] = {}
    for entity in snapshot.entities.values():
        if not isinstance(entity, Constraint) or not isinstance(entity.expression, Comparison):
            continue
        left, right = entity.expression.args
        if isinstance(left, Ref) and isinstance(right, Literal) and right.quantity is not None:
            bounds.setdefault(left.attr, []).append((entity.expression.op, right.quantity))
    for items in bounds.values():
        items.sort(key=lambda item: ("ge", "gt", "eq", "le", "lt", "ne").index(item[0]))
    return bounds


def _number(value: Decimal, counted: bool) -> str:
    from fang.verification import significant

    if counted and value.is_finite() and value == value.to_integral_value():
        return str(int(value))
    return significant(value, 3)


def _unit(quantity) -> str:
    symbol = str(quantity.unit)
    return {"1": "", "": "", "degC": " °C"}.get(symbol, f" {symbol}")


#: Comparison operators as a fang program writes them. The faces' latin subsets
#: have no mathematical operators, and these are the program's own spelling.
OPS = {"le": "<=", "lt": "<", "ge": ">=", "gt": ">", "eq": "=", "ne": "!="}


def _exact(value: Decimal) -> str:
    """A requirement's bound as the program states it, never rounded."""
    return format(value.normalize(), "f")


def _requirement_text(bounds) -> str:
    if len(bounds) == 2 and [op for op, _ in bounds] == ["ge", "le"]:
        low, high = bounds[0][1], bounds[1][1]
        return f"{_exact(low.value)}–{_exact(high.value)}{_unit(high)}"
    return ", ".join(f"{OPS[op]} {_exact(q.value)}{_unit(q)}" for op, q in bounds)


def _measure(measurement, bounds) -> Measure:
    """A measurement in its requirement's unit, and whether it meets it."""
    if not measurement.measured:
        return Measure(measurement.name, "not measured", _requirement_text(bounds), False)
    unit = bounds[0][1].unit
    quantity, _ = measurement.quantity.converted_to(unit)
    counted = _unit(quantity) == ""
    if quantity.kind == "range":
        low, high = quantity.minimum, quantity.maximum
        # An event observed not to occur is the half-open range after the run's
        # end; it is shown in the unit the run was measured in, where it reads
        # as the run's length.
        if not high.is_finite():
            shown = f">= {_number(measurement.quantity.minimum, counted)}{_unit(measurement.quantity)}"
        else:
            shown = f"{_number(low, counted)}–{_number(high, counted)}{_unit(quantity)}"
    else:
        low = high = quantity.value
        shown = f"{_number(low, counted)}{_unit(quantity)}"

    met: bool | None = True
    for op, bound in bounds:
        b = bound.converted_to(unit)[0].value
        holds = {
            "le": (high <= b, low > b), "lt": (high < b, low >= b),
            "ge": (low >= b, high < b), "gt": (low > b, high <= b),
            "eq": (low == high == b, b < low or b > high),
            "ne": (b < low or b > high, low == high == b),
        }[op]
        if holds[1]:
            met = False
            break
        if not holds[0]:
            met = None
    return Measure(measurement.name, shown, _requirement_text(bounds), met)


def runs() -> list[Run]:
    """The good build's two questions, then each broken build's failing one."""
    from fang.checks import DEFAULT_CHECKS
    from fang.elaborate import elaborate
    from fang.graph import KernelGraph
    from fang.verification import answer, questions, report

    program = _program()
    cases = [("sensor_node.elf", program.SensorNode, "startup"),
             ("sensor_node.elf", program.SensorNode, "sensor_missing")]
    cases += [(build, _variant(program, question, ELF / build), question)
              for build, question, _ in BUILDS if question]

    out = []
    for build, system, attribute in cases:
        result = elaborate(system, project_id="PRJ-EXAMPLES")
        if not result.ok:
            raise SystemExit([d.message for d in result.diagnostics])
        bounds = _requirements(result.snapshot)
        graph = KernelGraph(result.snapshot, checks=DEFAULT_CHECKS)
        question = next(q for q in questions(graph.head) if q.label.endswith(f".{attribute}"))
        with tempfile.TemporaryDirectory() as workspace:
            outcome = answer(graph, question, traits=result.traits, workspace=Path(workspace))
        if outcome.raw is None:
            raise SystemExit(f"{build} {attribute}: {outcome.status}: {outcome.message}")
        measures = {m.name: _measure(m, bounds[m.name]) for m in outcome.measurements}
        out.append(Run(
            build, attribute, outcome.result, tuple(report([outcome], versions=False)),
            measures, re.search(r"\d+\.\d+\.\d+", str(outcome.raw.version)).group(0),
        ))
        print(f"  {build:18} {attribute:15} {outcome.result}")
    return out


# --------------------------------------------------------------------------
# Drawing
# --------------------------------------------------------------------------

class Canvas:
    """A supersampled image that takes coordinates in output pixels."""

    def __init__(self, width: int, height: int) -> None:
        self.width, self.height = width, height
        self.image = Image.new("RGB", (width * SS, height * SS), GROUND)
        self.draw = ImageDraw.Draw(self.image)

    def mono(self, size: float, medium: bool = False):
        return brand.sized(brand.PLEX_500 if medium else brand.PLEX_400, round(size * SS))

    def sans(self, size: float, weight: int = 400):
        return brand.sized(brand.INTER, round(size * SS), weight=weight)

    def text(self, x, y, text, font, fill, anchor="ls", tracking=0.0) -> float:
        """Draw at a baseline; returns the x the text ends at, in output px."""
        if tracking:
            if anchor[0] == "r":
                x -= self.width_of(text, font, tracking)
            end = brand.tracked(self.draw, (x * SS, y * SS), text, font, fill, tracking * SS)
            return end / SS - tracking
        self.draw.text((x * SS, y * SS), text, font=font, fill=fill, anchor=anchor)
        width = self.width_of(text, font)
        return x + width if anchor[0] == "l" else x

    def width_of(self, text, font, tracking=0.0) -> float:
        if tracking:
            return sum(self.draw.textlength(c, font=font) / SS + tracking for c in text) - tracking
        return self.draw.textlength(text, font=font) / SS

    def rect(self, box, fill=None, outline=None, radius=0, width=1) -> None:
        box = tuple(v * SS for v in box)
        self.draw.rounded_rectangle(box, radius=radius * SS, fill=fill, outline=outline,
                                    width=width * SS)

    def rail(self) -> None:
        self.rect((0, 0, self.width, 3), fill=COPPER)

    def lockup(self, x, baseline, size) -> None:
        """`copperhead / fang`, with the mark, in the proportion the card sets."""
        grid = size * 1.8
        u = grid / 32
        brand.mark(self.draw, (x - 4) * SS, (baseline - 0.35 * size - 9.5 * u - 7.5 * u) * SS,
                   grid * SS)
        pen = x + 26 * u - 4 + size / 4
        pen = self.text(pen, baseline, "copperhead / ", self.mono(size), DIM)
        self.text(pen, baseline, "fang", self.mono(size, medium=True), TEXT)

    def label(self, x, baseline, text, size=15, fill=DIM, anchor="ls") -> float:
        """An uppercase Plex label at the brand's 0.08em tracking."""
        return self.text(x, baseline, text.upper(), self.mono(size), fill, anchor=anchor,
                         tracking=0.08 * size)

    def foot(self, margin, label) -> None:
        rule = self.height - margin - 44
        self.rect((margin, rule, self.width - margin, rule + 1), fill=HAIRLINE)
        baseline = self.height - margin
        self.label(margin, baseline, label, size=17)
        site = self.mono(17, medium=True)
        self.text(self.width - margin - self.width_of(DOMAIN, site), baseline, DOMAIN, site, ACCENT)

    def verdict(self, x, baseline, result, size=15, anchor="ls") -> float:
        """PASS or FAIL as a pill in its semantic colour; returns its width."""
        font = self.mono(size, medium=True)
        colour = PASS if result == "PASS" else FAIL if result == "FAIL" else MUTED
        pad = size * 0.6
        width = self.width_of(result, font, 0.06 * size) + 2 * pad
        left = x - width if anchor[0] == "r" else x
        top = baseline - size * 1.05
        self.rect((left, top, left + width, baseline + size * 0.42), outline=colour,
                  radius=size * 0.35, width=1)
        self.text(left + pad, baseline, result, font, colour, tracking=0.06 * size)
        return width

    def save(self, name: str) -> None:
        image = self.image.resize((self.width, self.height), Image.LANCZOS)
        out = HERE / name
        image.save(out, optimize=True)
        print(f"{out.relative_to(ROOT)}  {self.width}x{self.height}  {out.stat().st_size / 1024:.0f} KB")


def _headline(canvas: Canvas, x, baseline, parts, ceiling, width, weight=600) -> None:
    whole = "".join(text for text, _ in parts)
    font = brand.fit(canvas.draw, whole, ceiling, width * SS, weight=weight)
    for text, colour in parts:
        x = canvas.text(x, baseline, text, font, colour)


def _by(runs_: list[Run], build: str, question: str) -> Run:
    return next(r for r in runs_ if r.build == build and r.question == question)


def _caught_by(run: Run) -> list[Measure]:
    """The measures a broken build failed, in the question's order."""
    return [m for m in run.measures.values() if m.met is False]


HEAD = (("fang", ACCENT_TEXT), (": Firmware against the board", TEXT))


def card(runs_: list[Run]) -> None:
    """The link card: the line, three numbers that carry it, and the foot."""
    c = Canvas(1200, 630)
    margin = brand.MARGIN
    c.rail()
    c.lockup(margin, margin + 40, 40)
    _headline(c, margin, 266, HEAD, 80, c.width - 2 * margin)

    startup = _by(runs_, "sensor_node.elf", "startup")
    broken = [_by(runs_, b, q) for b, q, _ in BUILDS if q]
    failed = sum(r.result == "FAIL" for r in broken)
    first, reported = startup.measures["first_read"], startup.measures["reported"]
    stats = (
        (first.shown, "first sensor read", f"required {first.required}"),
        (reported.shown, "temperature printed", f"required {reported.required}"),
        (f"{failed} of {len(broken)}", "broken builds fail", "each through the gate"),
    )
    value, note = c.sans(46, 600), c.mono(16)
    column = (c.width - 2 * margin) / 3
    for index, (shown, label, detail) in enumerate(stats):
        x = margin + index * column
        c.text(x, 360, shown, value, TEXT)
        c.label(x, 394, label, size=14)
        c.text(x, 420, detail, note, MUTED)
    c.foot(margin, f"Its own firmware, run in Renode {startup.version}")
    c.save("emulation-card.png")


def _count(n: int, noun: str) -> str:
    return f"{n} {noun}" + ("" if n == 1 else "s")


def _listing(run: Run) -> list[tuple[str, str]]:
    """fang verify's lines for one question, with the long assumption and gap
    lines folded into one, marked as folded, so the rest reads at a size."""
    lines: list[tuple[str, str]] = []
    assumptions = sum(1 for line in run.lines if line.startswith("  assumption:"))
    gaps = sum(1 for line in run.lines if line.startswith("  coverage gap:"))
    folded = False
    for line in run.lines:
        if line.startswith(("  assumption:", "  coverage gap:")):
            if not folded:
                lines.append((f"  … {_count(assumptions, 'assumption')}, "
                              f"{_count(gaps, 'coverage gap')}", "fold"))
                folded = True
            continue
        if line.strip() in ("PASS", "FAIL"):
            lines.append((line, line.strip()))
        elif line.startswith("system."):
            lines.append((line, "name"))
        elif " = " in line:
            lines.append((line, "measure"))
        else:
            lines.append((line, "plain"))
    return lines


def run_listing(runs_: list[Run]) -> None:
    """`fang verify` on the board, as it prints, both questions side by side."""
    c = Canvas(1200, 675)
    margin = 56
    c.rail()
    c.lockup(margin, 70, 26)
    startup = _by(runs_, "sensor_node.elf", "startup")
    c.label(c.width - margin, 70, f"Renode {startup.version} · firmware emulation", size=14,
            anchor="rs")

    top, bottom = 104, c.height - 48 - 44 - 24
    c.rect((margin, top, c.width - margin, bottom), fill=RAISED, outline=HAIRLINE, radius=12)
    pad, size, leading = 34, 20, 36
    mono, medium = c.mono(size), c.mono(size, medium=True)
    x, y = margin + pad, top + pad + size
    pen = c.text(x, y, "$ ", mono, DIM)
    c.text(pen, y, "fang verify examples/sensor_node/sensor_node.py", mono, TEXT)

    colours = {"name": TEXT, "measure": TEXT, "plain": MUTED, "fold": DIM}
    column = (c.width - 2 * margin - 2 * pad) / 2
    for index, question in enumerate(("startup", "sensor_missing")):
        run = _by(runs_, "sensor_node.elf", question)
        cx, cy = x + index * column, y + leading * 1.6
        for text, kind in _listing(run):
            if kind in ("PASS", "FAIL"):
                c.text(cx, cy, text, medium, PASS if kind == "PASS" else FAIL)
            elif kind == "measure":
                name, value = text.split(" = ", 1)
                pen = c.text(cx, cy, f"{name} = ", mono, MUTED)
                c.text(pen, cy, value, medium, TEXT)
            else:
                c.text(cx, cy, text, medium if kind == "name" else mono, colours[kind])
            cy += leading
    c.foot(margin - 8, "The board's firmware, run against the board")
    c.save("emulation-run.png")


def caught(runs_: list[Run]) -> None:
    """The good build and each broken one: what is wrong, what caught it."""
    c = Canvas(1200, 675)
    margin = 56
    c.rail()
    c.lockup(margin, 70, 26)
    c.label(c.width - margin, 70, "One board, four firmware builds", size=14, anchor="rs")
    broken = [_by(runs_, b, q) for b, q, _ in BUILDS if q]
    _headline(c, margin, 150, (
        (f"{len(broken)} broken builds. ", TEXT),
        ("Each fails through the gate.", ACCENT_TEXT),
    ), 44, c.width - 2 * margin)

    cols = {"build": margin, "measure": 486, "measured": 716, "required": 868}
    head = 206
    for key, title in (("build", "build"), ("measure", "caught by"), ("measured", "measured"),
                       ("required", "required")):
        c.label(cols[key], head, title, size=13)
    c.label(c.width - margin, head, "result", size=13, anchor="rs")
    c.rect((margin, head + 14, c.width - margin, head + 15), fill=HAIRLINE)

    name_font, note_font = c.mono(19, medium=True), c.sans(17)
    value_font, required_font = c.mono(19, medium=True), c.mono(19)
    good = [_by(runs_, "sensor_node.elf", q) for q in ("startup", "sensor_missing")]
    rows = [("sensor_node.elf", BUILDS[0][2], good)]
    rows += [(b, why, [_by(runs_, b, q)]) for b, q, why in BUILDS if q]
    y, step = head + 58, 86
    for build, why, its_runs in rows:
        result = "FAIL" if any(r.result == "FAIL" for r in its_runs) else "PASS"
        c.text(cols["build"], y, build, name_font, TEXT)
        c.text(cols["build"], y + 28, why, note_font, MUTED)
        if result == "PASS":
            measures = [m for r in its_runs for m in r.measures.values()]
            met = sum(m.met is True for m in measures)
            c.text(cols["measure"], y, "every measure", c.mono(19), MUTED)
            c.text(cols["measured"], y, f"{met} of {len(measures)}", value_font, TEXT)
            c.text(cols["required"], y, "met", required_font, MUTED)
        else:
            first, *rest = _caught_by(its_runs[0])
            c.text(cols["measure"], y, first.name, c.mono(19), TEXT)
            c.text(cols["measured"], y, first.shown, value_font, FAIL)
            c.text(cols["required"], y, first.required, required_font, MUTED)
            # Measured failures first, then those the run left without a value.
            also = [f"{m.name} = {m.shown}" for m in rest if m.shown != "not measured"]
            also += [f"{m.name} (not measured)" for m in rest if m.shown == "not measured"]
            notes = {
                "push_pull.elf": "every I2C transaction still succeeds",
                "no_timeout.elf": "the LED never shows the fault",
            }
            note = " and ".join(also) if also else notes.get(build, "")
            if note:
                c.text(cols["measure"], y + 28, ("also fails " if also else "") + note, note_font, DIM)
        c.verdict(c.width - margin, y, result, size=16, anchor="rs")
        if build != rows[-1][0]:
            c.rect((margin, y + 50, c.width - margin, y + 51), fill=HAIRLINE)
        y += step
    c.foot(margin - 8, "Each build run in Renode against the same board")
    c.save("emulation-caught.png")


def square(runs_: list[Run]) -> None:
    """The square: the line, the two questions' measures, the broken builds."""
    c = Canvas(1080, 1080)
    margin = 80
    c.rail()
    c.lockup(margin, margin + 34, 34)
    width = c.width - 2 * margin
    font = brand.fit(c.draw, "fang: Firmware against", 76, width * SS)
    pen = c.text(margin, 238, "fang", font, ACCENT_TEXT)
    c.text(pen, 238, ": Firmware against", font, TEXT)
    c.text(margin, 238 + font.size / SS * 1.12, "the board", font, TEXT)

    startup = _by(runs_, "sensor_node.elf", "startup")
    y = 412
    c.label(margin, y, f"The firmware that ships · Renode {startup.version}", size=15)
    c.rect((margin, y + 14, c.width - margin, y + 15), fill=HAIRLINE)
    y += 48
    name_font, value_font, req_font = c.mono(21), c.mono(21, medium=True), c.mono(21)
    for question in ("startup", "sensor_missing"):
        run = _by(runs_, "sensor_node.elf", question)
        c.label(margin, y, question.replace("_", " "), size=13, fill=ACCENT)
        y += 36
        for measure in run.measures.values():
            c.text(margin, y, measure.name, name_font, MUTED)
            c.text(margin + 330, y, measure.shown, value_font, TEXT)
            c.text(margin + 560, y, measure.required, req_font, DIM)
            colour = PASS if measure.met else FAIL if measure.met is False else MUTED
            dot = 5
            cx, cy = c.width - margin - dot, y - 7
            c.rect((cx - dot, cy - dot, cx + dot, cy + dot), fill=colour, radius=dot)
            y += 36
        y += 8

    y += 22
    broken = [(b, _by(runs_, b, q)) for b, q, _ in BUILDS if q]
    failed = sum(r.result == "FAIL" for _, r in broken)
    c.label(margin, y, f"Broken builds · {failed} of {len(broken)} fail", size=15)
    c.rect((margin, y + 14, c.width - margin, y + 15), fill=HAIRLINE)
    y += 50
    for build, run in broken:
        first = _caught_by(run)[0]
        c.text(margin, y, build, c.mono(21, medium=True), TEXT)
        pen = c.text(margin + 330, y, f"{first.name} ", name_font, MUTED)
        c.text(pen, y, first.shown, value_font, FAIL)
        c.verdict(c.width - margin, y, run.result, size=15, anchor="rs")
        y += 40
    c.foot(margin, "Its own firmware, run against the board")
    c.save("emulation-square.png")


if __name__ == "__main__":
    print("running the builds in Renode")
    results = runs()
    card(results)
    run_listing(results)
    caught(results)
    square(results)
