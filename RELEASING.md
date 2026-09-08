# Releasing

The distribution is **`copperhead-fang`** on PyPI; the import name is `fang`.
(`fang` itself is taken on PyPI by an unrelated 2015 package.)

The version has one source of truth: `__version__` in
[fang/__init__.py](fang/__init__.py). `pyproject.toml` reads it via
`[tool.setuptools.dynamic]`, the CLI reports it, and the release workflow
refuses a tag that disagrees with it.

`SCHEMA_VERSION` in the same module is separate: it is the version of the
serialized EIR, and it moves only when the on-disk form changes.

## One-time setup

1. Create the project on PyPI by publishing once, or reserve the name.
2. On PyPI, add a **trusted publisher** for the project:
   owner `copperheadhq`, repository `fang`, workflow `release.yml`,
   environment `pypi`.
3. In the GitHub repository settings, create an environment named `pypi`.
   Nothing needs to be stored in it — trusted publishing mints a short-lived
   token, so there is no API token to keep.

## Cutting a release

1. Bump `__version__` in `fang/__init__.py`.
2. Move the `## [Unreleased]` entries in [CHANGELOG.md](CHANGELOG.md) under a
   new `## [x.y.z] - YYYY-MM-DD` heading and update the link definitions at the
   bottom.
3. Commit, and confirm CI is green on `main`.
4. Tag and push:

   ```bash
   git tag -a vX.Y.Z -m "vX.Y.Z"
   git push origin vX.Y.Z
   ```

   The `Release` workflow runs the suite, checks the tag against
   `fang.__version__`, builds the sdist and the wheel, and publishes them.

## Building and checking by hand

```bash
pip install -e ".[dev]"
python -m build                       # dist/*.whl and dist/*.tar.gz
python -m twine check --strict dist/*
```

To verify the sdist is self-contained, unpack it and run the suite from inside
it — the tests, the examples they read, and the spec all ship in the sdist:

```bash
tar xzf dist/copperhead_fang-*.tar.gz -C /tmp
cd /tmp/copperhead_fang-*/ && python -m pytest -rs
```

Determinism is asserted across processes, so run at least once with
`PYTHONHASHSEED=random`, as CI does.
