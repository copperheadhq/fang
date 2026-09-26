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
from pathlib import Path

import pytest

from examples.regenerate import examples as example_names, simulated

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
