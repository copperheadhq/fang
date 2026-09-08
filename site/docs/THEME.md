# Where the theme comes from

The visual identity is copperhead's. It is not vendored here. This site takes
it from a package:

```js
plugins: [copperheadTheme()]
```

| | |
| --- | --- |
| Package | [`@copperhead/starlight-theme`](../../packages/starlight-theme/) |
| Lifted from | `copperheadhq/copperhead`, `docs/src/styles/custom.css` and `docs/src/components/*.astro` |
| At commit | `c62f540`, *docs(site): address the pr-review findings on #286*, 2026-09-08 |

The package lives in this repository for now because fang is the first consumer.
It belongs in the copperhead repo, published once and depended on by both sites;
its README covers that move. Nothing about it is fang-specific.

## Checking for drift

`styles/theme.css` in the package is byte-identical to upstream except for one
token, so drift is a diff:

```bash
gh api repos/copperheadhq/copperhead/contents/docs/src/styles/custom.css \
  --jq .content | base64 -d \
  | diff - ../../packages/starlight-theme/styles/theme.css
```

The only expected difference is light `--sl-color-gray-3`: upstream ships
`#6d747f`, which fails WCAG AA on the sidebar (4.44:1) and the inline-code
background (4.20:1). The package ships `#686f7a`, which clears every surface.
**That fix belongs upstream.** When it lands there, the diff goes silent.

The same check works for each component under `docs/src/components/`.

## What fang supplies itself

Only what is its own: the title, the description, the logo, the social links, the edit link and the sidebar. There is no local stylesheet and no local
component override. If something needs to look different here, prefer changing
it upstream. Fang is a sub-brand, and a difference that is only fang's is
usually a difference that should not exist.

## Version parity

`docs.copperhead.sh` currently serves Astro 7.1.1 / Starlight 0.41.3. This site
resolves whatever the committed lockfile pins, which may be newer; Starlight
regenerates its scoped class hashes between minors, so exact parity with the
deployed site means matching the lockfile, not just the ranges.
