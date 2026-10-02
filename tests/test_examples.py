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

import functools
import re
from pathlib import Path

import pytest

from examples.regenerate import (
    DRAFTED,
    PROJECT,
    answerable,
    examples as example_names,
    render as regenerate,
    schematic_of,
    simulated,
    verification_tools,
)
from fang.checks import DEFAULT_CHECKS
from fang.cli import load_system
from fang.constraints import CheckStatus
from fang.copperhead import CopperheadDrafter
from fang.elaborate import elaborate
from fang.kicad import emit_netlist
from fang.netlist import compile_netlist
from fang.schematic import KicadRenderer
from fang.simulation import NgspiceBackend
from fang.verification import TOOLS, questions

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


#: An example's outputs, rendered once per run: writing verification.txt runs
#: a simulator, and three tests read the same set.
render = functools.lru_cache(maxsize=None)(regenerate)

#: The one output that depends on a tool being installed rather than on the
#: design alone: what `fang verify` finds. It is compared where the tool its
#: questions route to is installed, and skipped by name where it is not.
VERIFICATION = "verification.txt"


def build(path: Path):
    result = elaborate(load_system(path), project_id=PROJECT)
    assert result.ok, [d.message for d in result.diagnostics]
    return result


@pytest.fixture(params=NAMES, ids=NAMES)
def name(request):
    """The example under test, named by its path relative to examples/."""
    return request.param


#: KiCad's render of a schematic, which only `kicad-cli` can make.
RENDER = "schematic.svg"
#: copperhead's draft and KiCad's render of it, which need both tools. The
#: intent beside them needs neither, and is compared everywhere.
DRAFT = ("copperhead/schematic.svg",)


def _drafted(relative: str) -> bool:
    return relative in DRAFT or (
        relative.startswith("copperhead/") and relative.endswith(".kicad_sch")
    )


@pytest.fixture
def tools(name):
    """Which tool-made outputs can be made here, as (render, draft). One that
    ships a schematic ships KiCad's render of it, which needs `kicad-cli`;
    one in DRAFTED ships copperhead's draft, which needs `copperhead` and
    `kicad-cli`. Without them those files are left out and every other output
    is still checked. One that carries a bench ships what ngspice measured,
    and nothing of that can be checked without `ngspice`."""
    if simulated(name) and not NgspiceBackend().available():
        pytest.skip("ngspice is not installed here")
    return KicadRenderer().available(), CopperheadDrafter().available()


def _expected(name, tools):
    render_here, draft_here = tools
    return render(name, with_render=render_here, with_draft=draft_here)


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


def test_an_example_ships_the_outputs_it_documents(example, name, tools):
    """A folder with no out/ is a folder that documents nothing."""
    out = example.parent / "out"
    committed = {
        path.relative_to(out).as_posix() for path in out.rglob("*") if path.is_file()
    }
    render_here, draft_here = tools
    if not render_here:
        committed.discard(RENDER)
    if not draft_here:
        committed = {relative for relative in committed if not _drafted(relative)}
    assert committed == set(_expected(name, tools))


def test_a_committed_output_still_matches_the_program(example, name, tools):
    """Regenerate every output and compare; `python examples/regenerate.py`
    is the fix when this fails."""
    out = example.parent / "out"
    for relative, text in sorted(_expected(name, tools).items()):
        if relative == VERIFICATION:
            continue
        assert stable((out / relative).read_text(encoding="utf-8")) == stable(text), relative


def test_the_sensor_node_names_its_controllers_routes_its_pins_and_decides_its_address():
    """What `sensor_node/README.md` says the graph holds, it holds."""
    from fang.compatibility import compatibility_check
    from fang.entities import Connection, Evidence, Port

    snapshot = build(ROOT / "sensor_node" / "sensor_node.py").snapshot
    entities = snapshot.entities
    ports = {str(e.identity.path): e for e in entities.values() if isinstance(e, Port)}
    assert ports["system.mcu.i2c1"].peripheral == "I2C1"
    assert ports["system.mcu.usart2"].peripheral == "USART2"

    def pin(entity_id):
        return entities[entity_id].vendor_name

    routed = {}
    for connection in entities.values():
        if isinstance(connection, Connection):
            for pin_id, entry in connection.selectors.items():
                assert isinstance(entities[entry["evidence"]], Evidence)
                routed[pin(pin_id)] = entry["selector"]
    assert routed == {"PB8": "AF4", "PB9": "AF4", "PA2": "AF7", "PA3": "AF7"}

    addressing = [r for r in compatibility_check(snapshot) if "address" in r.message]
    assert [r.status for r in addressing] == [CheckStatus.PASS]
    assert "0x44" in addressing[0].message
    assert ports["system.env.i2c"].id in addressing[0].message
    assert ports["system.mcu.i2c1"].id not in addressing[0].message


def test_the_buck_controllers_enable_is_driven_as_its_datasheet_says():
    """EN must be set high or low, never left open (TPS62130 section 8.3.1):
    the always-on rail ties it to the controller's input, as the datasheet's
    typical application does, with the claim cited in the graph."""
    from fang.entities import Evidence

    result = build(ROOT / "buck_regulator" / "buck_regulator.py")
    netlist = compile_netlist(result.snapshot, traits=result.traits)
    nets = {
        (node.designator, node.pin): {(n.designator, n.pin) for n in net.nodes}
        for net in netlist.nets
        for node in net.nodes
    }
    assert ("U1", "VIN") in nets[("U1", "EN")]
    cited = [
        e for e in result.snapshot.entities.values()
        if isinstance(e, Evidence) and str(e.identity.path) == "system.enable_input"
    ]
    assert len(cited) == 1 and cited[0].locator.startswith("section 8.3.1")


#: The examples that declare a verification question, and so ship a listing.
QUESTIONED = [name for name, path in zip(NAMES, EXAMPLES) if questions(build(path).snapshot)]


@pytest.mark.parametrize("name", QUESTIONED, ids=QUESTIONED)
def test_a_committed_verification_still_matches_the_program(name):
    """What `fang verify` finds, compared where its tool is installed."""
    result = build(ROOT / name / f"{Path(name).name}.py")
    missing = sorted(
        tool for tool in verification_tools(result) if not answerable(TOOLS.get(tool))
    )
    if missing:
        pytest.skip(
            f"{', '.join(missing)} is not installed here at a version it accepts, "
            f"so {VERIFICATION} is not compared"
        )
    committed = (ROOT / name / "out" / VERIFICATION).read_text(encoding="utf-8")
    assert stable(committed) == stable(render(name)[VERIFICATION])
