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

# The card's copy. The headline names the product and states the line, in the
# one string the brand uses everywhere else; `copperhead` is named twice around
# it, in the lockup above and the relationship along the foot. The accent falls
# on the name: `fang` in copper, the line after it in plain text, so the card
# says who this is first and what it does second. `fang` stays lowercase here
# as it does in running text; the colon belongs to the sentence, not the name,
# so it is not accented with it.
HEAD = (("fang", ACCENT_TEXT), (": Hardware as Code", TEXT))
HEAD_SIZE = 92        # a ceiling, not a setting — `fit` takes it down to fit
HEAD_MARK, HEAD_GAP = 0.70, 26   # the mark's span as a fraction of the size
FOOT_LABEL = "THE LANGUAGE AND KERNEL UNDER COPPERHEAD"
DOMAIN = "fang.copperhead.sh"


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


def fit(draw, text, ceiling, width, weight=600, mark=0.0, gap=0):
    """Inter at the largest whole point size at or under `ceiling` that fits.

    `mark` reserves a mark ahead of the text whose 20.5-unit span is that
    fraction of the point size, `gap` after it. Tying the mark to the size
    rather than fixing it in px means the two stay in proportion whatever
    length the line turns out to be.
    """
    for size in range(ceiling, 0, -1):
        font = sized(INTER, size * SS, weight=weight)
        reserved = (mark * size * SS + gap) if mark else 0
        if reserved + draw.textlength(text, font=font) <= width:
            return font, size
    raise SystemExit(f"{text!r} does not fit in {width / SS:.0f} px at any size")


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


def via_mark(draw, x, y, grid):
    """copperhead's own mark: a via, with four traces leaving it.

    The geometry is packages/starlight-theme/assets/mark.svg — the same 32-unit
    grid as fang's and the same 2.25 stroke, which is what makes the two read as
    one system side by side. Butt caps, not round: these traces run into the via
    rather than ending in the open, and fang's round caps are its own.
    """
    u = grid / 32

    def p(ux, uy):
        return (x + ux * u, y + uy * u)

    width = max(1, int(round(2.25 * u)))
    radius = 5.25 * u
    cx, cy = p(16, 16)
    draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius),
                 outline=COPPER, width=width)
    for a, b in (
        ((16, 5.75), (16, 10.75)),      # the four traces, from the via outward
        ((16, 21.25), (16, 26.25)),
        ((5.75, 16), (10.75, 16)),
        ((21.25, 16), (26.25, 16)),
    ):
        draw.line([p(*a), p(*b)], fill=COPPER, width=width)


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
    """The social card: the lockup, the line, and the foot that places it.

    Three registers, top to bottom — who this is, what it is, and where it
    lives. The headline is one line rather than the two it used to be, so it is
    set larger and centred in the band the pair filled, which keeps the card's
    proportions without leaving a hole where the second line was.
    """
    canvas = Image.new("RGB", (W * SS, H * SS), GROUND)
    draw = ImageDraw.Draw(canvas)

    def px(*values):
        return tuple(v * SS for v in values) if len(values) > 1 else values[0] * SS

    # The rail the mark hangs from, run across the top of the card.
    draw.rectangle((0, 0, W * SS, 3 * SS), fill=COPPER)

    # ── Lockup ───────────────────────────────────────────────────────────
    # The parent brand, on its own: copperhead's via with four traces leaving
    # it, and its name. fang is not named up here any more — it leads the line
    # below, where the mark that belongs to it goes too.
    plex_light = sized(PLEX_400, 40 * SS)
    lockup_baseline = (MARGIN + 40) * SS
    cap = -draw.textbbox((0, 0), "copperhead", font=plex_light, anchor="ls")[1]

    grid = 64 * SS
    u = grid / 32
    via_mark(draw, MARGIN * SS - 5.75 * u, lockup_baseline - cap / 2 - 16 * u, grid)
    tracked(
        draw,
        (MARGIN * SS + 20.5 * u + 12 * SS, lockup_baseline),
        "copperhead",
        plex_light,
        DIM,
    )

    # ── Headline ─────────────────────────────────────────────────────────
    # Set as large as the margins allow, up to the ceiling: the line is one
    # string and the card is a fixed size, so the type fits the line rather
    # than the line being cut to fit the type. Centred on its cap band and
    # not its text box — the descender and the leading are not ink, and
    # centring on those would ride the whole line high.
    whole = "".join(word for word, _ in HEAD)
    rule = px(H - MARGIN - 74)
    head, size = fit(
        draw, whole, HEAD_SIZE, (W - 2 * MARGIN) * SS, mark=HEAD_MARK, gap=HEAD_GAP * SS
    )
    head_cap = -draw.textbbox((0, 0), whole, font=head, anchor="ls")[1]
    baseline = (lockup_baseline + 46 * SS + rule + head_cap) / 2

    # fang's mark leads its own line, set to the cap height beside it and
    # centred on the same band, so it reads as the first word rather than as a
    # bullet sitting next to one.
    head_grid = HEAD_MARK * size * SS / 20.5 * 32
    hu = head_grid / 32
    x = MARGIN * SS
    mark(draw, x - 5.75 * hu, baseline - head_cap / 2 - 16 * hu, head_grid)
    x += 20.5 * hu + HEAD_GAP * SS
    for word, colour in HEAD:
        draw.text((x, baseline), word, font=head, fill=colour, anchor="ls")
        x += draw.textlength(word, font=head)

    # ── Foot ─────────────────────────────────────────────────────────────
    draw.rectangle((px(MARGIN), rule, px(W - MARGIN), rule + SS), fill=HAIRLINE)

    label = sized(PLEX_400, 21 * SS)
    foot = px(H - MARGIN)
    tracked(draw, (px(MARGIN), foot), FOOT_LABEL, label, DIM, tracking=0.08 * 21 * SS)

    site = sized(PLEX_500, 21 * SS)
    width = sum(draw.textlength(c, font=site) for c in DOMAIN)
    tracked(draw, (px(W - MARGIN) - width, foot), DOMAIN, site, ACCENT)

    image = canvas.resize((W, H), Image.LANCZOS)

    # Written twice, because `/brand/` is served from two document roots: this
    # folder for the landing page, and docs/public/ for the docs site, whose
    # pages point at the same absolute URL. The hand-drawn assets are copied
    # across by hand; this one is generated, so a copy left behind would go
    # stale without anyone seeing it.
    for out in (HERE, HERE.parent / "docs" / "public" / "brand"):
        out = out / "og.png"
        image.save(out, optimize=True)
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
