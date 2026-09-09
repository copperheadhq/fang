"""Draw the two brand assets that carry type: the outlined lockups and the card.

Everything else in this folder is hand-drawn geometry and stays that way. These
two cannot be, because both are read where the webfont does not load — a README
on GitHub and on PyPI, and the crawler that renders a shared link — so the
wordmark has to be outlines in the one case and pixels in the other. Rerun it
when the wordmark, the line, or the palette moves. Nothing on the site runs it:
`index.html` still has no build step. It needs `pillow` and `fonttools[woff]`,
neither of which fang itself depends on:

    pip install pillow "fonttools[woff]"
    python site/brand/make.py

Geometry comes from BRAND.md and is not re-derived here: the mark is the same
two paths on the same 32-unit grid, stroked 2.25 with round caps and joins, and
the type is IBM Plex Mono and Inter at the sizes the page sets them. The
webfonts are read out of the docs build, which already carries them, so both
assets are set in the real faces rather than a substitute.
"""

from __future__ import annotations

import io
import math
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
FONTS = HERE.parent / "docs" / "dist" / "_astro"

W, H = 1200, 630
SS = 3  # supersample, so the mark's round caps and joins stay round

GROUND = "#1b1b1c"
COPPER = "#b87333"        # the mark's own copper, for the mark and the rail
ACCENT = "#c47a3a"        # the interface accent, a step brighter on the ground
ACCENT_TEXT = "#e6a366"   # accent as type, which is what the page's h1 em uses
TEXT = "#e3e5e8"
DIM = "#8a9098"
HAIRLINE = "#343638"

MARGIN = 88


def face(pattern: str) -> ImageFont.FreeTypeFont:
    """The one woff2 in the docs build matching `pattern`, as a TrueType face."""
    matches = sorted(FONTS.glob(pattern))
    if not matches:
        raise SystemExit(f"no font matching {pattern} under {FONTS}")
    font = TTFont(matches[0])
    font.flavor = None
    buffer = io.BytesIO()
    font.save(buffer)
    return buffer


PLEX_500 = face("ibm-plex-mono-latin-500-normal.*.woff2")
PLEX_400 = face("ibm-plex-mono-latin-400-normal.*.woff2")
INTER = face("inter-latin-wght-normal.*.woff2")


def sized(buffer: io.BytesIO, size: int, weight: float | None = None):
    buffer.seek(0)
    font = ImageFont.truetype(io.BytesIO(buffer.read()), size)
    if weight is not None:
        font.set_variation_by_axes([weight])
    return font


def tracked(draw, xy, text, font, fill, tracking=0.0):
    """Draw `text` letter by letter so the tracking is real. Returns the pen x."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill, anchor="ls")
        x += draw.textlength(ch, font=font) + tracking
    return x


def stroke(draw, points, width, colour):
    """A polyline with round caps and round joins, which PIL has no flag for."""
    draw.line(points, fill=colour, width=int(round(width)))
    radius = width / 2
    for x, y in points:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=colour)


def mark(draw, x, y, grid):
    """The mark, its 32-unit grid scaled to `grid` px, top-left at (x, y)."""
    u = grid / 32

    def p(ux, uy):
        return (x + ux * u, y + uy * u)

    width = 2.25 * u
    stroke(draw, [p(5.75, 7.5), p(26.25, 7.5)], width, COPPER)
    stroke(draw, [p(10.5, 7.5), p(16, 24.5), p(21.5, 7.5)], width, COPPER)


# The mark, exactly as `mark.svg` draws it.
RAIL = "M5.75 7.5h20.5"
FANG = "M10.5 7.5 16 24.5l5.5-17"

# The wordmark's setting, exactly as `lockup.svg` sets it.
WORDMARK, WORD_SIZE, WORD_X, WORD_BASELINE, WORD_TRACKING = "fang", 20, 38, 22.5, 0.5


def wordmark() -> tuple[str, float]:
    """`fang` as one filled path, and the x the glyphs end at."""
    PLEX_500.seek(0)
    font = TTFont(io.BytesIO(PLEX_500.read()))
    glyphs, cmap, hmtx = font.getGlyphSet(), font.getBestCmap(), font["hmtx"]
    scale = WORD_SIZE / font["head"].unitsPerEm

    def number(value: float) -> str:
        return f"{value:.3f}".rstrip("0").rstrip(".")

    commands, x = [], float(WORD_X)
    for index, character in enumerate(WORDMARK):
        name = cmap[ord(character)]
        pen = SVGPathPen(glyphs, ntos=number)
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, x, WORD_BASELINE)))
        commands.append(pen.getCommands())
        x += hmtx[name][0] * scale
        if index < len(WORDMARK) - 1:      # tracking sits between the glyphs
            x += WORD_TRACKING
    return "".join(commands), x


def lockups() -> None:
    """The lockup with the wordmark outlined, one per theme.

    `lockup.svg` keeps the wordmark as live text, which is right for anywhere
    the webfont loads and wrong everywhere else — a README is set in whatever
    monospace the reader happens to have. These two carry the outlines instead,
    trimmed to the glyphs and given one stroke-width of clear space.
    """
    path, right = wordmark()
    width = math.ceil(right + 2.25)
    for suffix, ink, where in (
        ("", TEXT, "on the dark ground"),
        ("-light", "#2b2d32", "on the light ground"),
    ):
        out = HERE / f"lockup-outlined{suffix}.svg"
        out.write_text(
            f"<!-- Generated by make.py. The wordmark is outlined, so this is the\n"
            f"     lockup to use where the webfont does not load. Ink is the text\n"
            f"     token {where}; the mark is copper in both. -->\n"
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} 32"'
            f' width="{width * 2}" height="64" role="img" aria-label="fang">\n'
            f'  <g fill="none" stroke="{COPPER}" stroke-width="2.25"'
            f' stroke-linecap="round" stroke-linejoin="round">\n'
            f'    <path d="{RAIL}"/>\n'
            f'    <path d="{FANG}"/>\n'
            f"  </g>\n"
            f'  <path fill="{ink}" d="{path}"/>\n'
            f"</svg>\n",
            encoding="utf-8",
        )
        print(f"{out.relative_to(HERE.parent.parent)}  {out.stat().st_size / 1024:.1f} KB")


def card() -> None:
    canvas = Image.new("RGB", (W * SS, H * SS), GROUND)
    draw = ImageDraw.Draw(canvas)

    def px(*values):
        return tuple(v * SS for v in values) if len(values) > 1 else values[0] * SS

    # The rail the mark hangs from, run across the top of the card.
    draw.rectangle((0, 0, W * SS, 3 * SS), fill=COPPER)

    # ── Lockup ───────────────────────────────────────────────────────────
    # The mark stands 1.37 cap-heights tall beside the wordmark, the same
    # proportion the page header sets it at, and is centred on the cap band.
    grid, lockup_y = 72, MARGIN + 40
    u = grid / 32
    mark(draw, px(MARGIN - 4), px(lockup_y - 14 - 9.5 * u - 7.5 * u), px(grid))
    plex_lockup = sized(PLEX_500, 40 * SS)
    plex_lockup_light = sized(PLEX_400, 40 * SS)
    x = px(MARGIN + 26 * u - 4 + 10)
    x = tracked(draw, (x, px(lockup_y)), "copperhead / ", plex_lockup_light, DIM)
    tracked(draw, (x, px(lockup_y)), "fang", plex_lockup, TEXT)

    # ── Headline ─────────────────────────────────────────────────────────
    head = sized(INTER, 62 * SS, weight=600)
    draw.text(px(MARGIN, 300), "Write the hardware.", font=head, fill=TEXT, anchor="ls")
    x = px(MARGIN)
    y = px(384)
    for word, colour in (
        ("Let the kernel decide ", TEXT),
        ("what is true", ACCENT_TEXT),
        (".", TEXT),
    ):
        draw.text((x, y), word, font=head, fill=colour, anchor="ls")
        x += draw.textlength(word, font=head)

    # ── Foot ─────────────────────────────────────────────────────────────
    rule = px(H - MARGIN - 74)
    draw.rectangle((px(MARGIN), rule, px(W - MARGIN), rule + SS), fill=HAIRLINE)

    label = sized(PLEX_400, 21 * SS)
    baseline = px(H - MARGIN)
    tracked(
        draw,
        (px(MARGIN), baseline),
        "THE LANGUAGE AND KERNEL UNDER COPPERHEAD",
        label,
        DIM,
        tracking=0.08 * 21 * SS,
    )

    site = sized(PLEX_500, 21 * SS)
    width = sum(draw.textlength(c, font=site) for c in "fang.copperhead.sh")
    tracked(draw, (px(W - MARGIN) - width, baseline), "fang.copperhead.sh", site, ACCENT)

    out = HERE / "og.png"
    canvas.resize((W, H), Image.LANCZOS).save(out, optimize=True)
    print(f"{out.relative_to(HERE.parent.parent)}  {out.stat().st_size / 1024:.0f} KB")


def touch_icon() -> None:
    """`favicon.svg` as a 180 px raster, for the one place that cannot take SVG.

    iOS uses this for a home-screen bookmark. Same chip, same corner radius,
    same mark — it is the favicon's construction, at a size a phone asks for.
    """
    side = 180
    canvas = Image.new("RGB", (side * SS, side * SS), "#15181c")
    draw = ImageDraw.Draw(canvas)
    chip = Image.new("L", (side * SS, side * SS), 0)
    ImageDraw.Draw(chip).rounded_rectangle(
        (0, 0, side * SS - 1, side * SS - 1), radius=6 / 32 * side * SS, fill=255
    )
    mark(draw, 0, 0, side * SS)

    out = HERE / "apple-touch-icon.png"
    icon = canvas.resize((side, side), Image.LANCZOS)
    icon.putalpha(chip.resize((side, side), Image.LANCZOS))
    icon.save(out, optimize=True)
    print(f"{out.relative_to(HERE.parent.parent)}  {out.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    lockups()
    card()
    touch_icon()
