"""The TI op amp handbook's circuits: every claim a bench makes, holding.

Spec: "Simulation Is A Compiler Target" and "SPICE Lowering".

`tests/test_examples.py` already rebuilds each circuit's out/ and compares, so
a committed `simulation.txt` is what ngspice measures today. What that test
cannot say is whether the measurement *agreed* with the program: a claim that
fails is written down as faithfully as one that holds. This one reads the
verdicts, so a circuit whose simulation stops agreeing with its own claims is a
failure rather than a line in a file nobody opened.
"""

import re
import shutil
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from examples.regenerate import (
    PROJECT,
    _program,
    bench_of,
    examples as example_names,
    simulated,
)
from fang.elaborate import elaborate
from fang.cli import load_system

ROOT = Path(__file__).resolve().parent.parent / "examples"
HANDBOOK = [name for name in example_names() if name.startswith("ti_opamp_handbook/")]
VERDICT = re.compile(r"^(\d+) of (\d+) claims hold\.$", re.MULTILINE)


def test_the_handbook_is_not_empty():
    """A prefix that matched nothing would make the test below vacuous."""
    assert len(HANDBOOK) >= 70


@pytest.mark.parametrize("name", HANDBOOK, ids=HANDBOOK)
def test_every_claim_a_handbook_circuit_makes_holds_in_simulation(name):
    assert simulated(name), f"{name} declares no bench"
    report = (ROOT / name / "out" / "simulation.txt").read_text(encoding="utf-8")
    held, total = map(int, VERDICT.search(report).groups())
    assert total >= 1, "a bench that claims nothing checks nothing"
    assert held == total, [line for line in report.splitlines() if "FAILS" in line]


# -- the bench itself ---------------------------------------------------------

sys.path.insert(0, str(ROOT / "ti_opamp_handbook"))
from handbook import _MEASURED  # noqa: E402


def _read(line: str):
    match = _MEASURED.match(line)
    return None if not match or match.group(3) else match.group(2)


def test_a_measurement_is_read_up_to_where_ngspice_says_it_was_taken():
    assert _read("gain = -9.99e+01") == "-9.99e+01"
    assert _read("peak = 2.5e+00 at= 5.0e-03") == "2.5e+00"


def test_a_complex_result_is_not_read_as_its_real_part():
    """ngspice prints a complex scalar as `re,im`. Half of it is not the value,
    and a claim checked against it could hold by accident."""
    assert _read("w = 0.000000e+00,1.000000e+00") is None


@pytest.mark.skipif(shutil.which("ngspice") is None, reason="ngspice is not installed")
def test_a_setting_its_part_never_reads_is_refused():
    """A misspelt parameter would otherwise leave the default in place, and a
    claim that happens to match the default would hold without testing it."""
    name = "ti_opamp_handbook/buffers/inverting_buffer_adjustable_gain"
    system = load_system(_program(name))
    bench = bench_of(system)
    run = next(run for run in bench.runs if run.settings)
    part = next(iter(run.settings))
    typo = replace(run, settings={part: {"setings": 0}})
    result = elaborate(system, project_id=PROJECT)
    with pytest.raises(ValueError, match="setings"):
        replace(bench, runs=[typo]).render(result, system, Path(name).name)


# -- the drawings -------------------------------------------------------------

import json  # noqa: E402
import importlib.util  # noqa: E402

from examples.regenerate import FIGURES  # noqa: E402

_spec = importlib.util.spec_from_file_location("draw_figures", ROOT / "draw_figures.py")
draw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(draw)

DRAWN = [name for name in example_names() if name.startswith(FIGURES)]


@pytest.mark.parametrize("name", DRAWN, ids=DRAWN)
def test_a_circuit_is_drawn_from_the_program_it_ships_beside(name):
    """copperhead draws the schematic outside the suite, so nothing else
    notices when a program changes and its drawing does not. The intent a
    drawing was made from has to be the one the program gives today; when it
    is not, `python examples/draw_figures.py` redraws it."""
    figure = ROOT / name / "figure"
    stem = Path(name).name
    for file in ("schematic.intent.json", f"{stem}.kicad_sch", "schematic.svg"):
        assert (figure / file).is_file(), f"{name} has no figure/{file}"
    drawn = json.loads((figure / "schematic.intent.json").read_text(encoding="utf-8"))
    assert drawn == draw.intent(name)
