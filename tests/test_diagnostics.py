"""Spec: The Diagnostic Code Registry.

Codes are allocated, never reused, and retired rather than deleted, because a
waiver references a code by value and has to keep meaning what it meant.
"""

from __future__ import annotations

import pytest

from fang import diagnostics
from fang.diagnostics import AREAS, REGISTRY, Diagnostic, Severity


def allocated() -> dict[str, str]:
    """Every code the module allocates, by value."""
    return {
        value: name
        for name, value in vars(diagnostics).items()
        if isinstance(value, str) and name.isupper() and value in REGISTRY
    }


def test_no_code_is_allocated_twice():
    codes = [
        value
        for name, value in vars(diagnostics).items()
        if isinstance(value, str) and name.isupper() and value in REGISTRY
    ]
    assert len(codes) == len(set(codes))


def test_every_code_is_in_an_allocated_area():
    for code in allocated():
        assert code.partition("-")[0] in AREAS


def test_reallocating_a_code_for_another_condition_is_refused():
    with pytest.raises(ValueError):
        REGISTRY.allocate("TOPO-0001", "something else entirely")


def test_reallocating_a_code_for_the_same_condition_is_the_same_code():
    existing = REGISTRY.allocate(
        "TOPO-0001", "a physical reference resolves to no realization"
    )
    assert existing.code == "TOPO-0001"


def test_a_diagnostic_carrying_an_unallocated_code_is_refused():
    with pytest.raises(ValueError):
        Diagnostic("TOPO-9999", Severity.ERROR, "never allocated")


# -- 6.1 the physical intent codes ----------------------------------------


def test_the_topo_area_carries_the_physical_intent_codes():
    assert set(allocated()) >= {
        "TOPO-0001", "TOPO-0002", "TOPO-0003", "TOPO-0004"
    }


def test_the_topo_codes_are_numbered_without_a_gap():
    numbers = sorted(
        int(code.partition("-")[2]) for code in allocated() if code.startswith("TOPO-")
    )
    assert numbers == list(range(1, len(numbers) + 1))


def test_an_unrepresentable_board_construct_stays_under_the_import_code():
    """`IMPORT-0001` already means what it needs to mean, so no fifth code was
    allocated for it: loss at the boundary is not a disagreement about intent."""
    assert "IMPORT-0001" in REGISTRY
    assert allocated()["IMPORT-0001"] == "IMPORT_LOSSY"


# -- 6.2 a module says which requirement it implements ---------------------

#: Each module of the physical layer, and a requirement its docstring names.
#: The link is what keeps a behaviour change and its contract in step; a module
#: that stops quoting the requirement it implements has lost the thread.
SPEC_LINKS = {
    "fang/physical.py": "The Physical Entity Model",
    "fang/routing.py": "Emitted Design Rules Are Projections",
    "fang/kicad.py": "Board Import Reports What It Could Not Represent",
}


def flattened(path) -> str:
    """A file's text with runs of whitespace collapsed.

    A docstring wraps at the column the rest of the file wraps at, so a quoted
    requirement name can be split across two lines and still be the name.
    """
    return " ".join(path.read_text(encoding="utf-8").split())


@pytest.mark.parametrize("module, requirement", sorted(SPEC_LINKS.items()))
def test_a_module_quotes_the_requirement_it_implements(module, requirement):
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    text = flattened(root / module)
    assert "Spec:" in text
    assert f'"{requirement}"' in text


@pytest.mark.parametrize("module, requirement", sorted(SPEC_LINKS.items()))
def test_the_requirement_a_module_quotes_is_in_the_spec(module, requirement):
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    spec = (root / "openspec" / "specs" / "fang-kernel" / "spec.md").read_text(
        encoding="utf-8"
    )
    assert f"### Requirement: {requirement}" in spec
