"""Spec: The View Specification; The Required Views; A View Contains Nothing
Absent From Its Snapshot; The Layout Boundary."""

import pytest

from fang.elaborate import elaborate
from fang.entities import ConnectionKind
from fang.identity import authored
from fang.interfaces import I2CPort, Pin, PinMap, PowerIn, PowerOut
from fang.lang import System, V, kOhm, mA
from fang.layout import (
    LayoutRequest,
    PlacementSeeds,
    layered,
    place,
    to_request,
)
from fang.parts import Capacitor, Regulator, Resistor
from fang.render import to_svg
from fang.topology import TopologyConstraint, TopologyMode
from fang.views import REGISTRY, REQUIRED_VIEWS, ViewSpec, compile_view, view

PROJECT = "PRJ-VIEWS"


class Board(System):
    regulator = Regulator(output_voltage=3.3 * V, package="SOT-23-5")
    load = Resistor(resistance=10 * kOhm, package="R_0603")
    bulk = Capacitor(package="C_0805")

    def architecture(self):
        self.regulator.vout.vcc >> self.load.p1
        self.load.p2 >> self.bulk.p1
        self.regulator.vout.gnd >> self.bulk.p2


@pytest.fixture
def snapshot():
    result = elaborate(Board, project_id=PROJECT)
    assert result.ok, [d.message for d in result.diagnostics]
    return result.snapshot


# -- the specification -----------------------------------------------------


def test_every_required_view_is_available_by_name():
    assert set(REQUIRED_VIEWS) <= set(REGISTRY)
    assert len(REQUIRED_VIEWS) == 6


def test_a_view_records_the_specification_that_produced_it(snapshot):
    graph = view(snapshot, "power")
    recorded = graph.as_dict()["spec"]
    assert recorded["name"] == "power"
    assert recorded["question"]
    assert recorded["edge_kinds"] == ["power"]


def test_a_view_names_the_snapshot_it_projects(snapshot):
    assert view(snapshot, "system").snapshot == snapshot.hash


def test_an_unknown_view_name_is_refused(snapshot):
    with pytest.raises(KeyError, match="no view named"):
        view(snapshot, "nonsense")


# -- membership ------------------------------------------------------------


def test_the_power_view_shows_only_power_connectivity(snapshot):
    graph = view(snapshot, "power")
    assert graph.edges
    assert {edge.edge_class for edge in graph.edges} == {"power"}


def test_the_interconnect_view_shows_more_than_the_power_view(snapshot):
    assert len(view(snapshot, "interconnect").edges) >= len(view(snapshot, "power").edges)


def test_the_ground_view_distinguishes_intent_from_net_equivalence():
    """A topology constraint appears as an annotation, not as membership."""
    result = elaborate(Board, project_id=PROJECT)
    entities = dict(result.snapshot.entities)
    constraint = TopologyConstraint(
        authored("TOPO-GND"),
        net="NET-GND",
        mode=TopologyMode.STAR,
        center="NET-STAR",
        branches=("DOM-A", "DOM-B"),
    )
    entities[constraint.id] = constraint
    from fang.graph import Snapshot

    snapshot = Snapshot(PROJECT, "REV-1", entities)
    graph = view(snapshot, "ground")
    assert any("topology" in note for note in graph.notes)


def test_a_view_without_topology_intent_says_so(snapshot):
    graph = view(snapshot, "ground")
    assert any("no topology intent" in note for note in graph.notes)


# -- fidelity --------------------------------------------------------------


def test_every_node_and_edge_traces_to_an_entity(snapshot):
    for name in REQUIRED_VIEWS:
        graph = view(snapshot, name)
        for node in graph.nodes:
            assert node.id in snapshot.entities, (name, node.id)
        for edge in graph.edges:
            assert edge.id in snapshot.entities, (name, edge.id)
            assert edge.source in snapshot.entities
            assert edge.target in snapshot.entities


def test_a_view_reports_what_is_unknown_in_it(snapshot):
    graph = view(snapshot, "system")
    completeness = graph.completeness()
    # The capacitor's capacitance was never declared.
    assert not completeness["complete"]
    assert completeness["nodes_with_unknowns"] >= 1
    assert any(node.incomplete for node in graph.nodes)


def test_repeated_generation_is_identical(snapshot):
    for name in REQUIRED_VIEWS:
        assert view(snapshot, name).as_dict() == view(snapshot, name).as_dict()


def test_a_view_invents_no_annotation(snapshot):
    """Annotations come from graph facts; a view with no such facts has none."""
    graph = compile_view(
        snapshot, ViewSpec("bare", "nothing", include_kinds=("component",))
    )
    assert all(not node.annotations for node in graph.nodes)


# -- the layout boundary ---------------------------------------------------


def test_the_layout_request_carries_no_engineering_meaning(snapshot):
    graph = view(snapshot, "interconnect")
    request = to_request(graph)
    rendered = request.as_dict()

    permitted_node_keys = {"id", "width", "height", "ports", "parent"}
    for node in rendered["nodes"]:
        assert set(node) <= permitted_node_keys
    for edge in rendered["edges"]:
        assert set(edge) <= {"id", "source", "target"}
    # Nothing that carries meaning got through.
    text = str(rendered)
    assert "label" not in text and "annotations" not in text and "incomplete" not in text


def test_layout_output_becomes_a_positioned_view_graph(snapshot):
    graph = view(snapshot, "interconnect")
    positioned = place(graph)
    assert set(positioned.positions) == {node.id for node in graph.nodes}
    assert positioned.width > 0 and positioned.height > 0
    assert positioned.graph is graph


def test_layout_is_deterministic(snapshot):
    graph = view(snapshot, "interconnect")
    assert place(graph).as_dict() == place(graph).as_dict()


def test_placement_seeds_are_presentation_state(snapshot):
    power = place(view(snapshot, "power"))
    seeds = PlacementSeeds().learn(power)
    assert len(seeds) == len(power.positions)

    # Seeds live in their own table, keyed by node, apart from canonical identity.
    assert set(seeds.as_dict()) <= set(snapshot.entities)
    for entity in snapshot.entities.values():
        assert "placement_seed" not in entity.as_dict()


def test_seeds_carry_relative_placement_between_views(snapshot):
    power = place(view(snapshot, "power"))
    seeds = PlacementSeeds().learn(power)
    ground = place(view(snapshot, "ground"), seeds=seeds)
    assert set(ground.positions)


def test_a_seed_change_does_not_touch_the_graph(snapshot):
    before = snapshot.hash
    seeds = PlacementSeeds()
    seeds.set(next(iter(snapshot.entities)), 0)
    place(view(snapshot, "power"), seeds=seeds)
    assert snapshot.hash == before


# -- rendering -------------------------------------------------------------


def test_rendering_is_deterministic(snapshot):
    positioned = place(view(snapshot, "interconnect"))
    assert to_svg(positioned) == to_svg(positioned)


def test_the_svg_carries_the_views_question_and_its_nodes(snapshot):
    graph = view(snapshot, "power")
    svg = to_svg(place(graph))
    assert svg.startswith("<svg")
    assert graph.spec.question in svg
    for node in graph.nodes:
        assert node.id in svg


def test_the_diagram_shows_its_own_gaps(snapshot):
    svg = to_svg(place(view(snapshot, "system")))
    assert "stroke-dasharray" in svg
    assert "unknown parameters" in svg
