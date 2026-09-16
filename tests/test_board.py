"""Spec: Board Import Reports What It Could Not Represent; The Physical Layer Is
Compiled, Never Authoritative."""

from __future__ import annotations

from pathlib import Path

import pytest

from fang.elaborate import elaborate
from fang.entities import Net
from fang.graph import KernelGraph, materialize
from fang.diagnostics import FangError
from fang.identity import Origin
from fang.kicad import (
    board_connectivity,
    board_realization,
    compare_board_to_netlist,
    implied_pin_swaps,
    read_board,
)
from fang.lang import System, V, kOhm, uF
from fang.netlist import compile_netlist
from fang.parts import Capacitor, Resistor
from fang.physical import Board, Layer, Pad, Placement, Stackup, Trace, Via, Zone
from fang.sexpr import SExprError

PROJECT = "PRJ-BOARD"
DATA = Path(__file__).resolve().parent / "data"
TWO_LAYER = (DATA / "two_layer.kicad_pcb").read_text(encoding="utf-8")

#: The two nets the divider below compiles to, named as the netlist names them.
TOP = "Net-(C1-Pad1)"
BOTTOM = "Net-(C1-Pad2)"


class Divider(System):
    top = Resistor(resistance=10 * kOhm, package="R_0603")
    bottom = Resistor(resistance=4.7 * kOhm, package="R_0603")
    cap = Capacitor(capacitance=100 * uF, voltage_rating=16 * V, package="C_0805")

    def architecture(self):
        self.top.p2 >> self.bottom.p1
        self.bottom.p1 >> self.cap.p1
        self.bottom.p2 >> self.cap.p2


@pytest.fixture
def divider():
    result = elaborate(Divider, project_id=PROJECT)
    assert result.ok, [d.message for d in result.diagnostics]
    return result


@pytest.fixture
def netlist(divider):
    return compile_netlist(divider.snapshot, traits=divider.traits)


def board(*, pads: dict[str, list[tuple[str, str]]] | None = None) -> str:
    """A board joining the divider's pads onto the nets it is given.

    The default is the connectivity the netlist states; a test that wants a
    disagreement passes a different one.
    """
    joins = pads or {
        TOP: [("C1", "1"), ("R1", "1"), ("R2", "2")],
        BOTTOM: [("C1", "2"), ("R1", "2")],
    }
    codes = {name: index + 1 for index, name in enumerate(sorted(joins))}
    by_reference: dict[str, list[tuple[str, str]]] = {}
    for name, members in joins.items():
        for reference, pad in members:
            by_reference.setdefault(reference, []).append((pad, name))

    lines = ['(kicad_pcb', '  (version 20221018)', '  (general (thickness 1.6))']
    lines.append('  (layers (0 "F.Cu" signal) (31 "B.Cu" signal) (44 "Edge.Cuts" user))')
    lines.append('  (net 0 "")')
    for name, code in sorted(codes.items(), key=lambda item: item[1]):
        lines.append(f'  (net {code} "{name}")')
    for reference in sorted(by_reference):
        lines.append(f'  (footprint "lib:{reference}" (layer "F.Cu") (uuid "fp-{reference}")')
        lines.append("    (at 10 10)")
        lines.append(f'    (property "Reference" "{reference}")')
        for pad, name in sorted(by_reference[reference]):
            lines.append(
                f'    (pad "{pad}" smd rect (at 0 0) (layers "F.Cu") '
                f'(net {codes[name]} "{name}") (uuid "pad-{reference}-{pad}"))'
            )
        lines.append("  )")
    lines.append(")")
    return "\n".join(lines) + "\n"


# -- 5.1 what the reader recovers -----------------------------------------


def test_a_board_file_parses_into_physical_entities():
    result = read_board(TWO_LAYER, project_id=PROJECT, source="two_layer.kicad_pcb")
    kinds = {type(entity) for entity in result.entities.values()}
    assert {Board, Layer, Stackup, Placement, Pad, Trace, Via, Zone} <= kinds


def test_the_stackup_keeps_the_order_the_board_states():
    result = read_board(TWO_LAYER, project_id=PROJECT)
    stackup = next(e for e in result.entities.values() if isinstance(e, Stackup))
    names = [result.entities[id].layer_name for id in stackup.layers]
    assert names == ["F.Cu", "B.Cu", "Edge.Cuts"]


def test_the_outline_comes_off_the_edge_layer():
    result = read_board(TWO_LAYER, project_id=PROJECT)
    outline = next(e for e in result.entities.values() if isinstance(e, Board)).outline
    assert [(str(p.x), str(p.y)) for p in outline] == [
        ("0", "0"), ("40", "0"), ("40", "30"), ("0", "30")
    ]


def test_a_segment_carries_its_width_as_a_quantity():
    result = read_board(TWO_LAYER, project_id=PROJECT)
    widths = sorted(
        str(e.width) for e in result.entities.values() if isinstance(e, Trace)
    )
    assert widths == ["0.4 mm", "0.6 mm"]


def test_a_segment_carries_the_length_the_board_already_fixed():
    result = read_board(TWO_LAYER, project_id=PROJECT)
    lengths = sorted(
        str(e.length) for e in result.entities.values() if isinstance(e, Trace)
    )
    assert lengths == ["10 mm", "10 mm"]


def test_a_via_names_the_layers_it_runs_between():
    result = read_board(TWO_LAYER, project_id=PROJECT)
    via = next(e for e in result.entities.values() if isinstance(e, Via))
    assert len(via.layers) == 2
    assert str(via.drill) == "0.4 mm" and str(via.diameter) == "0.8 mm"


def test_a_zone_keeps_its_polygon():
    result = read_board(TWO_LAYER, project_id=PROJECT)
    zone = next(e for e in result.entities.values() if isinstance(e, Zone))
    assert len(zone.outline) == 4


def test_a_placement_carries_its_rotation_as_an_angle_not_a_length():
    result = read_board(TWO_LAYER, project_id=PROJECT)
    placement = next(e for e in result.entities.values() if isinstance(e, Placement))
    assert placement.rotation.unit.symbol == "deg"
    assert str(placement.x) == "10 mm"


def test_a_board_read_twice_lands_on_the_same_identifiers():
    first = read_board(TWO_LAYER, project_id=PROJECT)
    second = read_board(TWO_LAYER, project_id=PROJECT)
    assert sorted(first.entities) == sorted(second.entities)


def test_a_file_that_is_not_a_board_is_refused():
    with pytest.raises(SExprError):
        read_board('(export "version" "E")', project_id=PROJECT)


# -- 5.2 loss is reported, never approximated ------------------------------


def test_an_unrepresented_board_construct_is_reported_with_its_location():
    result = read_board(TWO_LAYER, project_id=PROJECT, source="two_layer.kicad_pcb")
    reported = {item.construct for item in result.report.unrepresented}
    assert {"dimension", "gr_text"} <= reported
    assert all(
        item.where.startswith("two_layer.kicad_pcb")
        for item in result.report.unrepresented
    )
    assert [d.code for d in result.report.diagnostics()][0] == "IMPORT-0001"


def test_an_unknown_construct_is_not_approximated_by_another_entity_kind():
    """The file's `dimension` and `gr_text` become no entity at all — not a
    region that happens to have an outline, and not a zone."""
    result = read_board(TWO_LAYER, project_id=PROJECT)
    counts: dict[str, int] = {}
    for entity in result.entities.values():
        counts[entity.kind] = counts.get(entity.kind, 0) + 1
    assert counts == {
        "board": 1, "stackup": 1, "layer": 3, "net": 2,
        "placement": 1, "pad": 2, "trace": 2, "via": 1, "zone": 1,
    }
    assert "region" not in counts


def test_the_layout_tools_own_rule_defaults_are_not_adopted():
    result = read_board(TWO_LAYER, project_id=PROJECT)
    # `setup` is recognized structure the kernel deliberately takes nothing from.
    assert not any(
        getattr(entity, "constraint_kind", None) for entity in result.entities.values()
    )


# -- 5.3 external identifiers are mapped, never adopted --------------------


def test_every_external_identifier_is_recorded_in_the_mapping_table():
    result = read_board(TWO_LAYER, project_id=PROJECT)
    external = set(result.mapping.as_dict())
    assert {"fp-r1", "pad-r1-1", "seg-1", "via-1", "layer:F.Cu"} <= external


def test_no_external_identifier_becomes_a_canonical_identity():
    result = read_board(TWO_LAYER, project_id=PROJECT)
    for external, canonical in result.mapping.as_dict().items():
        assert canonical != external
        assert canonical in result.entities


def test_an_imported_entity_carries_imported_origin():
    result = read_board(TWO_LAYER, project_id=PROJECT)
    assert all(
        entity.identity.origin is Origin.IMPORTED for entity in result.entities.values()
    )


def test_a_bound_net_gets_no_second_net_entity(divider, netlist):
    rail = netlist.nets[0]
    result = read_board(
        board(), project_id=PROJECT, realizes={rail.name: "RAIL-BOUND"}
    )
    assert not [
        e for e in result.entities.values() if isinstance(e, Net) and rail.name in e.aliases
    ]
    assert result.mapping.canonical(rail.name) == "RAIL-BOUND"


# -- 5.4 a board that disagrees with the netlist ---------------------------


def test_a_board_matching_the_netlist_reports_nothing(netlist):
    assert compare_board_to_netlist(board(), netlist) == []


def test_a_board_joining_two_pins_the_netlist_does_not_is_reported(netlist):
    shorted = board(
        pads={
            TOP: [("C1", "1"), ("R1", "1"), ("R2", "2"), ("R1", "2")],
            BOTTOM: [("C1", "2")],
        }
    )
    findings = compare_board_to_netlist(shorted, netlist, source="shorted.kicad_pcb")
    assert [f.code for f in findings] == ["TOPO-0002"]
    assert "R1.2" in findings[0].message


def test_the_netlist_is_not_rewritten_to_match_the_copper(netlist):
    shorted = board(
        pads={
            TOP: [("C1", "1"), ("R1", "1"), ("R2", "2"), ("R1", "2")],
            BOTTOM: [("C1", "2")],
        }
    )
    before = netlist.as_dict()
    compare_board_to_netlist(shorted, netlist)
    assert netlist.as_dict() == before


def test_board_connectivity_is_read_and_not_stored(netlist):
    joins = board_connectivity(board())
    assert joins[TOP] == (("C1", "1"), ("R1", "1"), ("R2", "2"))
    result = read_board(board(), project_id=PROJECT)
    # No entity records which net a pad sits on: the netlist already holds it.
    assert all("net" not in e.as_dict() for e in result.entities.values() if isinstance(e, Pad))


# -- 5.5 a pin swap returns through the gate -------------------------------


def swapped_board() -> str:
    """R1's two pins exchanged between the divider's two nets."""
    return board(
        pads={
            TOP: [("C1", "1"), ("R1", "2"), ("R2", "2")],
            BOTTOM: [("C1", "2"), ("R1", "1")],
        }
    )


def test_a_layout_chosen_pin_swap_is_offered_as_implied_changes(divider, netlist):
    realization = board_realization(swapped_board(), netlist, divider.snapshot)
    assert realization.implied_changes
    assert {op.op for op in realization.implied_changes} == {"remove_entity", "connect"}


def test_the_ingest_itself_changed_no_semantic_state(divider, netlist):
    before = divider.snapshot.hash
    board_realization(swapped_board(), netlist, divider.snapshot)
    read_board(swapped_board(), project_id=PROJECT)
    assert divider.snapshot.hash == before


def test_the_swap_returns_through_to_transaction_and_the_gate(divider, netlist):
    graph = KernelGraph(divider.snapshot)
    realization = board_realization(
        swapped_board(), netlist, divider.snapshot, parent_snapshot=graph.head.hash
    )
    transaction = realization.to_transaction(graph.head.hash)
    assert transaction.base == graph.head.hash
    proposal = graph.propose(transaction)
    # Whatever the gate decides, it decided it: the change went through it.
    assert proposal.diff is not None
    assert transaction.operations == realization.implied_changes


def test_a_board_that_matches_implies_no_change(divider, netlist):
    assert implied_pin_swaps(board(), netlist, divider.snapshot) == ()


def test_a_pin_that_merely_moved_is_not_offered_as_a_swap(divider, netlist):
    moved = board(
        pads={TOP: [("C1", "1"), ("R2", "2")], BOTTOM: [("C1", "2"), ("R1", "1"), ("R1", "2")]}
    )
    assert implied_pin_swaps(moved, netlist, divider.snapshot) == ()


# -- 5.6 the ordering rules hold -------------------------------------------


def test_materialize_refuses_a_board_whose_parent_is_not_the_committed_snapshot(
    divider, netlist
):
    graph = KernelGraph(divider.snapshot)
    realization = board_realization(
        board(), netlist, divider.snapshot, parent_snapshot="sha256:not-the-head"
    )
    with pytest.raises(FangError) as caught:
        materialize(realization, graph.head)
    assert caught.value.diagnostic.code == "TXN-0002"


def test_materialize_accepts_a_board_whose_parent_is_the_committed_snapshot(
    divider, netlist
):
    graph = KernelGraph(divider.snapshot)
    realization = board_realization(
        board(), netlist, divider.snapshot, parent_snapshot=graph.head.hash
    )
    assert materialize(realization, graph.head)


def test_external_results_are_refused_against_anything_but_the_committed_head(
    divider,
):
    from fang.constraints import CheckStatus
    from fang.graph import CheckResult, ingest_external_results

    graph = KernelGraph(divider.snapshot)
    with pytest.raises(FangError) as caught:
        ingest_external_results(
            graph,
            [CheckResult("drc", CheckStatus.PASS, "CMP-1")],
            snapshot_hash="sha256:not-the-head",
        )
    assert caught.value.diagnostic.code == "TXN-0002"
