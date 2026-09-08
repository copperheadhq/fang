"""Every shipped example elaborates, checks, and projects.

Spec: "The Command Surface" and "The Netlist Is A Projection".

An example is a promise the README makes, so the suite builds each one rather
than trusting it: it elaborates without diagnostics, validates, fails no check,
projects to a netlist with no component left out of it, emits a KiCad netlist,
and does all of that identically twice.
"""

from pathlib import Path

import pytest

from fang.checks import DEFAULT_CHECKS
from fang.cli import load_system
from fang.constraints import CheckStatus
from fang.elaborate import elaborate
from fang.kicad import emit_netlist
from fang.netlist import compile_netlist

EXAMPLES = sorted((Path(__file__).resolve().parent.parent / "examples").glob("*.py"))

PROJECT = "PRJ-EXAMPLES"


def build(path: Path):
    result = elaborate(load_system(path), project_id=PROJECT)
    assert result.ok, [d.message for d in result.diagnostics]
    return result


@pytest.fixture(params=EXAMPLES, ids=[path.stem for path in EXAMPLES])
def example(request):
    return request.param


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
    assert emit_netlist(netlist).startswith('(export "version" "E"')


def test_an_example_builds_identically_twice(example):
    """The same source gives the same snapshot, down to the identifier."""
    first, second = build(example).snapshot, build(example).snapshot
    assert first.hash == second.hash
