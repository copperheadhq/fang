---
title: Workspace
description: What `.copperhead/` holds and what may be deleted.
sidebar:
  order: 7
  attrs:
    data-icon: laptop
---

`fang init` creates a workspace beside your sources; `fang build` fills it.

```
.copperhead/
  manifest.json       what produced this state
  design.jsonl        the design, as a canonical record stream
  plan.json           the tool plan
  mapping.json        the CAD mapping table, after an import
  import-report.json  what an import could not represent
  sources/            declared, hashed inputs
  evidence/           external results, before they are ingested
  simulations/        decks and raw backend output
  views/              rendered views
  cache/              reconstructible; safe to delete
```

**Only `cache/` may be deleted.** Everything else is either canonical state or
the record of where canonical state came from. Deleting the cache loses no
engineering fact; deleting anything else does.

## The manifest

```json
{
  "schema_version": "1.1",
  "revision_id": "...",
  "compiler_version": "0.1.0",
  "snapshot": "...",
  "project_id": "PRJ-LOCAL",
  "lock_id": "unlocked",
  "entity_count": 42
}
```

The manifest exists so a snapshot's producer is reconstructible. `snapshot` is
the content hash; `schema_version` is the serialized-EIR version, which moves
independently of the compiler version.

An artifact declaring an unimplemented major schema version is
[`ELAB-0009`](/reference/diagnostics/). It is refused, not read on a guess.

## The design stream

`design.jsonl` is the canonical record stream: one record per line, written in
canonical form. Two properties follow from that and are what the format is for:

- **Byte-identical for identical inputs**, across processes with differing hash
  seeds. A diff between two builds shows engineering change and nothing else.
- **Diffable by ordinary tools**, because it is line-oriented text whose line
  order is deterministic.

Magnitudes are decimal strings, never binary floats. Keys sort by Unicode code
point, except for the collections whose order is semantic.

## Options

Every command that reads a program takes:

| Option | Does |
| --- | --- |
| `-C`, `--directory` | The project directory. Defaults to `.` |
| `--project` | The project identifier. Defaults to `PRJ-LOCAL` |
| `--system` | Which system to build, when a file defines several |

The project identifier is the namespace identifiers are derived in, so changing
it changes every identifier in the design. It is not a label.

## Importing CAD

An import writes two files beside the design:

- `mapping.json`, the mapping table, saying which kernel entity each CAD
  construct became
- `import-report.json`, the loss report

A construct the adapter cannot represent is named in the report as
[`IMPORT-0001`](/reference/diagnostics/) rather than dropped. The import is
lossy in the open, which is what makes one safe round trip possible. What
survived is stated, and so is what did not.
