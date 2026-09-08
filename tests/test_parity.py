"""The same board, built by both toolchains, compared.

`examples/parity/` holds an atopile project whose boards mirror two Fang
examples instance for instance. Both toolchains are given the same design, and
what they produce is reduced to the claim they both make — which instances
become components, and which pads are joined — and asserted equal.

The atopile artifact is its `.kicad_pcb`, checked in beside the source it was
built from, so this suite needs no atopile installation and no network. To
refresh it, install atopile and run `ato build` in `examples/parity/`; the
`is_atomic_part` components there keep that build offline and account-free.
"""

from pathlib import Path

import pytest

from conftest import PROJECT
from fang.cli import load_system

from parity import from_fang, from_kicad_pcb

ROOT = Path(__file__).resolve().parent.parent
PARITY = ROOT / "examples" / "parity"

#: Each Fang example and the atopile build that mirrors it.
BOARDS = ("divider", "blinky")


def fang_board(name: str):
    return from_fang(load_system(ROOT / "examples" / name / f"{name}.py"), project_id=PROJECT)


def atopile_board(name: str):
    return from_kicad_pcb(PARITY / "elec" / "layout" / name / f"{name}.kicad_pcb")


@pytest.fixture(params=BOARDS)
def board(request):
    return request.param


def test_the_parity_project_is_present():
    """A missing artifact would make every comparison below vacuous."""
    for name in BOARDS:
        assert (PARITY / "elec" / "src" / f"{name}.ato").is_file()
        assert (PARITY / "elec" / "layout" / name / f"{name}.kicad_pcb").is_file()


def test_both_toolchains_build_the_same_components(board):
    assert set(fang_board(board).components) == set(atopile_board(board).components)


def test_both_toolchains_join_the_same_pads(board):
    """The net partition, which is what a board is once names are set aside."""
    fang, atopile = fang_board(board), atopile_board(board)
    assert fang.difference(atopile) == []
    assert fang.nets == atopile.nets
    assert fang.nets, "a board with no nets would compare equal to anything"


def test_every_pin_fang_declares_is_a_pad_on_the_part(board):
    """Fang models the pins a design uses; the footprint carries all of them."""
    fang, atopile = fang_board(board), atopile_board(board)
    for instance, pads in fang.components.items():
        assert pads <= atopile.components[instance], instance


def test_a_difference_in_connectivity_is_reported(board):
    """The comparison would notice. Without this, equality proves nothing."""
    from parity import Board

    fang = fang_board(board)
    dropped = sorted(sorted(fang.nets, key=sorted)[0])
    without = Board(
        components=fang.components,
        nets=frozenset(net for net in fang.nets if sorted(net) != dropped),
    )
    problems = fang.difference(without)
    assert problems and "net only in the first" in problems[0]
