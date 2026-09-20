"""Every shipped example elaborates, checks, projects, and ships its outputs.

Spec: "The Command Surface" and "The Netlist Is A Projection".

An example is a promise the README makes, so the suite builds each one rather
than trusting it: it elaborates without diagnostics, validates, fails no check,
projects to a netlist with no component left out of it, emits a KiCad netlist,
and does all of that identically twice.

An example also ships the files `fang` produces from it, under `out/`, so the
folder can be read without running anything. Those are regenerated here and
compared, because an output nobody checks is an output that quietly stops
being true.
"""

import re
from pathlib import Path

import pytest

from examples.regenerate import PROJECT, examples as example_names, render
from fang.checks import DEFAULT_CHECKS
from fang.cli import load_system
from fang.constraints import CheckStatus
from fang.elaborate import elaborate
from fang.kicad import emit_netlist
from fang.netlist import compile_netlist

ROOT = Path(__file__).resolve().parent.parent / "examples"

#: An example is named by its path relative to examples/, so a grouped one
#: is `jee_advanced/problem_1` and its program is named after the leaf.
NAMES = example_names()
EXAMPLES = [ROOT / name / f"{Path(name).name}.py" for name in NAMES]

#: Two things in an output follow the machine rather than the design, and are
#: normalized away before comparing. The compiler version moves on release; the
#: snapshot hash covers provenance, which records the absolute path the program
#: was read from, so it differs between checkouts. Everything else is the
#: design, and has to match byte for byte.
VOLATILE = (
    re.compile(r'\(tool "fang [^"]+"\)'),
    re.compile(r"sha256:[0-9a-f]{64}"),
)


def stable(text: str) -> str:
    for pattern in VOLATILE:
        text = pattern.sub("<varies by machine>", text)
    return text


def build(path: Path):
    result = elaborate(load_system(path), project_id=PROJECT)
    assert result.ok, [d.message for d in result.diagnostics]
    return result


@pytest.fixture(params=NAMES, ids=NAMES)
def name(request):
    """The example under test, named by its path relative to examples/."""
    return request.param


@pytest.fixture
def example(name):
    return ROOT / name / f"{Path(name).name}.py"


def test_the_examples_directory_is_not_empty():
    """A glob that matched nothing would make every test below vacuous."""
    assert len(EXAMPLES) >= 8


def test_an_example_elaborates_and_validates(example):
    result = build(example)
    assert result.validation is not None and result.validation.ok


def test_an_example_fails_no_check(example):
    """Undecided is allowed and expected; failing is not."""
    snapshot = build(example).snapshot
    failures = [
        outcome.message
        for check in DEFAULT_CHECKS
        for outcome in check.run(snapshot)
        if outcome.status is CheckStatus.FAIL
    ]
    assert failures == []


def test_an_example_projects_to_a_netlist_with_no_component_left_out(example):
    """A part in the BOM and in no net is a part nobody connected."""
    result = build(example)
    netlist = compile_netlist(result.snapshot, traits=result.traits)
    assert netlist.components

    connected = {node.designator for net in netlist.nets for node in net.nodes}
    orphans = sorted({c.designator for c in netlist.components} - connected)
    assert orphans == []


def test_an_example_emits_a_kicad_netlist(example):
    result = build(example)
    netlist = compile_netlist(result.snapshot, traits=result.traits)
    assert emit_netlist(netlist).startswith('(export\n  (version "E")')


def test_an_example_builds_identically_twice(example):
    """The same source gives the same snapshot, down to the identifier."""
    first, second = build(example).snapshot, build(example).snapshot
    assert first.hash == second.hash


def test_an_example_ships_the_outputs_it_documents(example, name):
    """A folder with no out/ is a folder that documents nothing."""
    out = example.parent / "out"
    committed = {
        path.relative_to(out).as_posix() for path in out.rglob("*") if path.is_file()
    }
    assert committed == set(render(name))


def test_a_committed_output_still_matches_the_program(example, name):
    """Regenerate every output and compare; `python examples/regenerate.py`
    is the fix when this fails."""
    out = example.parent / "out"
    for relative, text in sorted(render(name).items()):
        assert stable((out / relative).read_text(encoding="utf-8")) == stable(text), relative
