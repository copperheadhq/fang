"""Spec: Physical Intent Is Authored In The Program.

Section 3 of the fang-physical change: a program states its board and its
routing rules, and what it states is recorded rather than evaluated.
"""

from __future__ import annotations

import pytest

from conftest import PROJECT
from fang.constraints import ConstraintClass
from fang.diagnostics import FangError
from fang.elaborate import elaborate
from fang.lang import (
    Electrical,
    System,
    declare_board,
    kOhm,
    layer,
    mm,
    ozcu,
    require,
)
from fang.parts import Resistor
from fang.units import Quantity


class Plain(System):
    """A program that says nothing physical: the defaults have to hold for it."""

    supply = Electrical()
    ground = Electrical()
    r = Resistor(resistance=10 * kOhm, package="R_0603_1608Metric")

    def constraints(self):
        require(self.r.resistance >= 1 * kOhm)


class Boarded(Plain):
    """The same design, with a board and a routing rule on top."""

    def constraints(self):
        require(self.r.resistance >= 1 * kOhm)
        require(
            self.r.resistance >= 1 * kOhm,
            constraint_class="routing",
            constraint_kind="min_trace_width",
        )

    def board(self):
        declare_board(
            outline=[(0, 0), (50, 0), (50, 40), (0, 40)],
            thickness=1.6 * mm,
            layers=[
                layer("F.Cu", copper_weight=1 * ozcu),
                layer("core1", function="dielectric", thickness=0.5 * mm),
                layer("In1.Cu", copper_weight=1 * ozcu),
                layer("B.Cu", copper_weight=1 * ozcu),
            ],
        )


def built(program):
    result = elaborate(program, project_id=PROJECT)
    assert result.snapshot is not None, result.diagnostics
    return result


def of_kind(result, kind):
    return [e for e in result.snapshot.entities.values() if e.kind == kind]


# -- 3.1 require() learns a class ------------------------------------------


def test_a_constraint_defaults_to_the_class_every_program_already_meant():
    constraint = of_kind(built(Plain), "constraint")[0]
    assert constraint.constraint_class is ConstraintClass.ELECTRICAL
    assert constraint.constraint_kind == "declared"


def test_a_declared_class_survives_into_the_record():
    kinds = {c.constraint_kind: c for c in of_kind(built(Boarded), "constraint")}
    routing = kinds["min_trace_width"]
    assert routing.constraint_class is ConstraintClass.ROUTING
    # The same schema as every other constraint, not a record of its own.
    assert routing.as_dict()["class"] == "routing"
    assert kinds["declared"].constraint_class is ConstraintClass.ELECTRICAL


def test_the_enum_and_its_spelling_are_the_same_declaration():
    assert ConstraintClass("routing") is ConstraintClass.ROUTING


def test_a_class_that_does_not_exist_is_refused_while_elaborating():
    class Bogus(Plain):
        def constraints(self):
            require(self.r.resistance >= 1 * kOhm, constraint_class="thermal-ish")

    result = elaborate(Bogus, project_id=PROJECT)
    assert result.snapshot is None
    assert "is not a constraint class" in result.diagnostics[0].message


# -- 3.2 the program declares the board ------------------------------------


def test_a_declared_stackup_becomes_an_entity_with_its_layers_in_order():
    result = built(Boarded)
    stackup = of_kind(result, "stackup")[0]
    names = [result.snapshot.entities[i].layer_name for i in stackup.layers]
    assert names == ["F.Cu", "core1", "In1.Cu", "B.Cu"]


def test_the_board_names_the_stackup_and_keeps_the_outline_it_was_given():
    result = built(Boarded)
    board = of_kind(result, "board")[0]
    assert board.stackup == of_kind(result, "stackup")[0].id
    assert [(p.x, p.y) for p in board.outline] == [(0, 0), (50, 0), (50, 40), (0, 40)]
    assert board.thickness == Quantity.scalar("1.6", "mm")


def test_the_declaration_carries_the_source_location_of_its_line():
    board = of_kind(built(Boarded), "board")[0]
    assert board.source_location is not None
    assert board.source_location.file.endswith("test_authoring.py")
    assert board.source_location.line > 0


def test_a_program_with_no_board_records_none():
    result = built(Plain)
    assert of_kind(result, "board") == []
    assert of_kind(result, "stackup") == []


def test_a_second_board_declaration_is_refused():
    class Twice(Plain):
        def board(self):
            declare_board(thickness=1.6 * mm)
            declare_board(thickness=1.0 * mm)

    result = elaborate(Twice, project_id=PROJECT)
    assert result.snapshot is None
    assert "one board" in result.diagnostics[0].message


def test_elaborating_the_same_program_twice_produces_identical_entities():
    assert built(Boarded).snapshot.hash == built(Boarded).snapshot.hash


def test_declaring_a_board_outside_an_elaboration_is_an_error():
    with pytest.raises(FangError):
        declare_board(thickness=1.6 * mm)


# -- 3.3 a magnitude is a quantity -----------------------------------------


def test_a_layer_names_its_copper_weight_as_a_quantity():
    result = built(Boarded)
    top = [e for e in of_kind(result, "layer") if e.layer_name == "F.Cu"][0]
    assert isinstance(top.copper_weight, Quantity)
    assert top.copper_weight == Quantity.scalar("1", "ozcu")


def test_a_bare_copper_weight_is_refused_at_the_declaration():
    with pytest.raises(FangError) as caught:
        layer("F.Cu", copper_weight=1)
    assert "never a bare number" in caught.value.diagnostic.message


def test_a_bare_board_thickness_is_refused_at_the_declaration():
    class Bare(Plain):
        def board(self):
            declare_board(thickness=1.6)

    result = elaborate(Bare, project_id=PROJECT)
    assert result.snapshot is None
    assert "never a bare number" in result.diagnostics[0].message


def test_a_stackup_is_built_from_layer_calls():
    class Wrong(Plain):
        def board(self):
            declare_board(layers=[{"layer_name": "F.Cu"}])

    result = elaborate(Wrong, project_id=PROJECT)
    assert result.snapshot is None
    assert "layer() calls" in result.diagnostics[0].message


def test_copper_weight_is_a_length_because_that_is_what_a_stackup_composes_with():
    """1 oz copper is an areal density by trade convention; what a width rule
    reasons about is the thickness it produces."""
    thickness = Quantity.scalar("1", "ozcu")
    assert thickness.dimension == Quantity.scalar("0", "mm").dimension


# -- 3.4 nothing is run -----------------------------------------------------


def test_declaring_a_board_constructs_no_placer_router_or_field_solver():
    result = built(Boarded)
    # Every tool a program reaches is recorded as a call and never executed;
    # a board declaration reaches none at all.
    assert result.plan.calls == ()


def test_no_width_is_evaluated_at_declaration_time():
    routing = [
        c
        for c in of_kind(built(Boarded), "constraint")
        if c.constraint_kind == "min_trace_width"
    ][0]
    # Recorded undecided: the board has no copper, and elaboration did not go
    # looking for any.
    from fang.constraints import CheckStatus

    assert routing.verification_status is CheckStatus.UNKNOWN
