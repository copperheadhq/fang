# fang — brand

Fang is a sub-brand of **copperhead**, not a separate identity. It inherits
copperhead's palette, typefaces, and restraint. What it gets of its own is a
mark and a voice suited to a language rather than an agent.

The name is literal: copperhead is the snake, fang is the fang. Say it that way
when the relationship needs explaining — it is the shortest true description of
how the two products relate.

## The mark

A trace, and a fang descending from it.

```
────────────────
   ╲        ╱
    ╲      ╱
     ╲    ╱
      ╲  ╱
       ╲╱
```

It is drawn on the same 32-unit grid as the copperhead via mark, with the same
`2.25` stroke weight, the same round caps and joins, and the same copper. Set
side by side the two read as one system: copperhead's is a via with four traces
leaving it; fang's is a single trace with one thing hanging from it.

| Asset | Use |
| --- | --- |
| [`brand/mark.svg`](brand/mark.svg) | The mark in copper. Default. |
| [`brand/mark-currentcolor.svg`](brand/mark-currentcolor.svg) | Inherits `currentColor`. For inline use where the mark must take the surrounding text colour. |
| [`brand/favicon.svg`](brand/favicon.svg) | 32×32 on the dark chip, matching copperhead's favicon construction. |
| [`brand/lockup.svg`](brand/lockup.svg) | Horizontal mark plus wordmark, the wordmark still live text. For anywhere the webfont loads. |

The card is the one place both marks appear together — copperhead's above,
fang's on the line below it. Both are drawn on the same 32-unit grid at the same
2.25 stroke in the same copper, which is what makes the pair one system rather
than two logos. copperhead's is not duplicated into this folder: `make.py` draws
it from the geometry in
[`packages/starlight-theme/assets/mark.svg`](../packages/starlight-theme/assets/mark.svg),
which is upstream's copy and stays the only one.

| [`brand/lockup-outlined.svg`](brand/lockup-outlined.svg) | The same lockup with the wordmark outlined, ink `#e3e5e8`. For the dark ground where the webfont does not load — a README, chiefly. |
| [`brand/lockup-outlined-light.svg`](brand/lockup-outlined-light.svg) | The outlined lockup again, ink `#2b2d32`, for the light ground. Pair the two in a `<picture>` so the README follows the reader's theme. |
| [`brand/og.png`](brand/og.png) | 1200×630 social card. What a shared link to the site renders as. Copied to `docs/public/brand/` too, by `make.py`. |
| [`brand/apple-touch-icon.png`](brand/apple-touch-icon.png) | 180×180 raster of the favicon chip, for an iOS home screen. |

The last four are generated rather than drawn, because each is read somewhere
the webfont does not load: the outlined lockups carry the wordmark as paths, the
card carries it as pixels, and the touch icon is the chip a home screen cannot
take as SVG. [`brand/make.py`](brand/make.py) draws all four from the geometry
below and from the real faces, which it reads out of the docs build rather than
substituting anything. Rerun it when the wordmark, the line, or the palette
moves:

```bash
pip install pillow "fonttools[woff]"
python site/brand/make.py
```

**Geometry.** Rail `M5.75 7.5 h20.5`. Fang `M10.5 7.5 L16 24.5 L21.5 7.5`.
Stroke `2.25`, `round` caps and joins, `fill: none`. The glyph spans 20.5 units
horizontally — the same span as the copperhead mark — and is centred on the
32-unit grid.

**Clear space.** One stroke-width (2.25 units at the drawn scale) on every side.
**Minimum size.** 16 px. Below that the fang's apex closes up; use the favicon.

**Do not:** fill the fang, add a taper, rotate it, put it in a circle, or pair it
with a second accent colour.

## Wordmark

Lowercase `fang`, always. Set in **IBM Plex Mono Medium** — monospace because it
names a language, where copperhead's own wordmark sits in Inter because it names
a product you talk to.

In running text the product is *fang*, lowercase, not *Fang* and not *FANG*. At
the start of a sentence, rewrite the sentence. The README and the landing page
both open on a rewritten sentence.

When the parent brand needs to be present, the lockup is
`copperhead / fang`, with `copperhead /` in the muted text colour and `fang` at
full strength. Never `Copperhead Fang` and never `fang by copperhead`.

## Colour

Copperhead's palette, with two values nudged for contrast (noted below). The
accent is copper because the subject is copper.

| Token | Dark | Light |
| --- | --- | --- |
| Accent | `#c47a3a` | `#a35d1f` |
| Accent, text | `#e6a366` | `#9a5619` |
| Accent, high | `#f2b57e` | `#5d3411` |
| Accent, low | `#3b2614` | `#f8e9db` |
| Accent, hover | `#d48a48` | `#8f4f18` |
| Ground | `#1b1b1c` | `#ffffff` |
| Raised | `#232425` | `#f7f8fa` |
| Hairline | `#343638` | `#e3e7ed` |
| Text | `#e3e5e8` | `#2b2d32` |
| Text, muted | `#b3b8be` | `#545962` |
| Text, dim | `#8a9098` | `#686f7a` |

The mark asset uses `#b87333` — true copper, and the same value copperhead's own
mark is drawn in. The interface accent is `#c47a3a`, a step brighter, because it
has to hold contrast against the dark ground.

Dark is the ground state. Light is a deliberate swap, not an afterthought: every
token has a light value, and nothing is defined only inside a media query.

Semantic colour is separate from the accent and never stands in for it:
pass `#6fbf73`, undecided `#d9a441`, blocked `#d56b62` (dark theme values).

Two values are nudged a step from copperhead's own and it is worth knowing why.
Light `--text-dim` is `#686f7a` rather than copperhead's gray-3 `#6d747f`, which
lands at 4.44 against the raised surface — just under 4.5. Dark `--stop` is
`#d56b62` rather than `#d2685f` for the same reason on the raised panel. Both
shifts are along the original hue and are invisible side by side; every text
token now clears its threshold on every surface it can sit on, in both themes.

## Type

| Role | Face |
| --- | --- |
| Headings, body, UI | Inter |
| Code, wordmark, labels, data | IBM Plex Mono |

Both are copperhead's. Labels and eyebrows are uppercase IBM Plex Mono at
`0.75rem` with `0.08em` tracking. Figures that line up in columns get
`font-variant-numeric: tabular-nums`.

## Voice

The product refuses to overclaim, so the writing does too.

- **Say what it will not do.** "A missing simulator reports unsupported rather
  than substituting a model" is a better sentence than any list of features.
- **Undecided is a value, not a hedge.** Never soften it into "may" or
  "possibly". The kernel is precise about uncertainty; the copy should be too.
- **Use the domain's real terms** — lowering, elaboration, the gate, undecided,
  a decision entity. The audience is engineers who already have these words.
- **No superlatives, no "revolutionary", no "seamless".** The claim is that the
  thing is *correct*, which is a claim you can check.

Copperhead's own line is "Cursor for circuit boards." Fang's is
**Hardware as Code** — the phrase infrastructure-as-code already taught this
audience, pointed at the board. It is the line the card carries and the line
the landing page and the README open on.

Under it sits the relationship, which is a description rather than a line:
*the language and kernel under copperhead*. Use it where fang has to be
placed against the parent brand — a README's second sentence, an about page —
not as the thing a reader meets first.

## The site

[`index.html`](index.html) is the landing page for `fang.copperhead.sh`. It is a
single self-contained file: no build step, no framework, one stylesheet inline,
one small script for the theme toggle. Fonts come from Google Fonts; everything
else ships with the page. `make.py` is not part of it — the page has no build
step and gets none.

Its head carries the brand for everything that renders the page without opening
it: `og:image` is the card, `theme-color` is the ground colour in each theme, and
the icons are the favicon and the touch icon. The docs site carries the same
card — Starlight gives each page its own `og:title` and `og:description` but no
image, so `astro.config.mjs` supplies one for the whole site.

The card is three registers, top to bottom: who this is, what it is, and where
it lives. copperhead's mark and name alone at the top, then **fang: Hardware as
Code** set as large as the margins allow with fang's own mark leading it, then
the relationship and the domain along the foot. Each brand is named once, each
behind its own mark, and fang's sits on the line that is fang's.
It carries no second sentence — at thumbnail width one idea is the most that
survives.

The accent falls on the name and nothing else: `fang` in copper, the line after
it in plain text, so the card says who this is first and what it does second.
The colon belongs to the sentence rather than the name, and is not accented with
it.

The headline is fitted, not sized: `make.py` takes the largest whole point size
at or under its ceiling that clears the margins, so the type follows the line
rather than the line being cut to fit the type. Re-run it when the line moves.

To deploy, serve `site/` as the document root so `/brand/favicon.svg` resolves.
