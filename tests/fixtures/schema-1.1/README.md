# schema-1.1

This directory holds a workspace's `design.jsonl` and `manifest.json`, written by
Fang at commit `62a6de3`, when the schema version was 1.1. It lets a test check
that a design written before schema 1.2 still loads.

The workspace has five records:

- A requirement and two components. These decode typed.
- Two constraints whose expressions reference an entity attribute. Schema 1.1
  wrote a reference's dimension vector sorted, because `dimension` was not yet an
  ordered collection. The order of those exponents was never written, so these
  records cannot be decoded. They load verbatim, and the load report names them.

The entities are built directly rather than elaborated from a program, so no
absolute path of the machine that wrote them appears in the files.

To regenerate the files you need that commit's code, not the current code,
because the point of the fixture is the bytes the earlier serializer wrote:

```bash
git archive 62a6de3 fang | tar -x -C /tmp/fang-1.1
```

Then build the same five entities against `/tmp/fang-1.1` and call
`Workspace.write_snapshot`.
