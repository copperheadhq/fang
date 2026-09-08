"""Spec: The Elaboration Result; Deterministic Sandboxed Elaboration."""

from datetime import datetime, timezone

import pytest

from fang.constraints import CheckStatus
from fang.elaborate import EPOCH, elaborate
from fang.entities import Component, Connection, ConnectionKind, Interface, Port
from fang.graph import AddEntity, KernelGraph, Transaction
from fang.lang import (
    Electrical,
    Ground,
    Parameter,
    Part,
    Power,
    System,
    V,
    kOhm,
    require,
    tools,
)
from fang.sandbox import Inputs
from fang.serialization import canonical_bytes
from fang.traits import Footprint
from fang.values import ValueStatus

PROJECT = "PRJ-ELAB"


class Regulator(Part):
    vin = Power()
    vout = Power()
    gnd = Ground()
    vin_max = Parameter("V")

    def constraints(self):
        require(self.vin_max <= 36 * V)


class Load(Part):
    vin = Power()
    gnd = Ground()


class Board(System):
    regulator = Regulator(vin_max=17 * V)
    load = Load()

    def architecture(self):
        self.regulator.vout >> self.load.vin
        self.regulator.gnd >> self.load.gnd


def test_elaboration_returns_a_snapshot_a_plan_and_diagnostics():
    result = elaborate(Board, project_id=PROJECT)
    assert result.ok
    assert result.snapshot is not None
    assert result.plan is not None
    assert result.diagnostics == ()


def test_the_python_object_graph_is_not_the_persisted_state():
    result = elaborate(Board, project_id=PROJECT)
    rendered = canonical_bytes(result.snapshot.as_dict())
    # Nothing in the snapshot is a live Python object; it round-trips as bytes.
    assert isinstance(rendered, bytes)
    for entity in result.snapshot.entities.values():
        assert not hasattr(entity, "_instance_children")


def test_re_elaborating_unchanged_source_is_byte_identical():
    first = elaborate(Board, project_id=PROJECT)
    second = elaborate(Board, project_id=PROJECT)
    assert canonical_bytes(first.snapshot.as_dict()) == canonical_bytes(
        second.snapshot.as_dict()
    )
    assert first.snapshot.hash == second.snapshot.hash


def test_every_entity_carries_the_source_location_that_produced_it():
    result = elaborate(Board, project_id=PROJECT)
    for entity in result.snapshot.entities.values():
        assert entity.source_location is not None, entity.id
        assert entity.source_location.file.endswith("test_elaborate.py")
        assert entity.source_location.line > 0


def test_modules_become_blocks_and_parts_become_components():
    result = elaborate(Board, project_id=PROJECT)
    kinds = {}
    for entity in result.snapshot.entities.values():
        kinds.setdefault(entity.kind, []).append(entity)
    assert len(kinds["block"]) == 1              # the system
    assert len(kinds["component"]) == 2          # two parts
    assert len(kinds["port"]) == 5               # 3 + 2 surfaces
    assert len(kinds["connection"]) == 2
    assert len(kinds["constraint"]) == 1


def test_surfaces_become_ports_owned_by_their_module():
    result = elaborate(Board, project_id=PROJECT)
    ports = [e for e in result.snapshot.entities.values() if isinstance(e, Port)]
    interfaces = {e.id for e in result.snapshot.entities.values() if isinstance(e, Interface)}
    for port in ports:
        assert port.owner in result.snapshot.entities
        assert port.interface in interfaces


def test_connections_are_typed_by_their_surfaces():
    result = elaborate(Board, project_id=PROJECT)
    connections = [
        e for e in result.snapshot.entities.values() if isinstance(e, Connection)
    ]
    kinds = {c.connection_kind for c in connections}
    assert kinds == {ConnectionKind.POWER, ConnectionKind.GROUND}


def test_declared_parameters_are_recorded_with_their_status():
    result = elaborate(Board, project_id=PROJECT)
    regulator = next(
        e
        for e in result.snapshot.entities.values()
        if isinstance(e, Component) and e.identity.display_name == "Regulator"
    )
    assert regulator.parameters["vin_max"].status is ValueStatus.EXPLICIT
    assert str(regulator.parameters["vin_max"].quantity) == "17 V"


def test_an_unassigned_parameter_elaborates_as_unknown():
    class Vague(System):
        part = Regulator()

    result = elaborate(Vague, project_id=PROJECT)
    regulator = next(
        e for e in result.snapshot.entities.values() if isinstance(e, Component)
    )
    assert regulator.parameters["vin_max"].status is ValueStatus.UNKNOWN


def test_a_declared_constraint_evaluates_against_the_snapshot():
    result = elaborate(Board, project_id=PROJECT)
    from fang.constraints import Constraint

    constraint = next(
        e for e in result.snapshot.entities.values() if isinstance(e, Constraint)
    )
    assert constraint.evaluate(result.snapshot.resolver()) is CheckStatus.PASS


def test_a_constraint_over_an_unknown_parameter_is_undecided():
    class Vague(System):
        part = Regulator()

    result = elaborate(Vague, project_id=PROJECT)
    from fang.constraints import Constraint

    constraint = next(
        e for e in result.snapshot.entities.values() if isinstance(e, Constraint)
    )
    assert constraint.evaluate(result.snapshot.resolver()) is CheckStatus.UNKNOWN


def test_a_failed_elaboration_returns_no_partial_graph():
    class Broken(System):
        regulator = Regulator()

        def architecture(self):
            # A power surface does not connect to a mechanical one.
            from fang.lang import Mechanical

            self.regulator.vin >> Mechanical()

    result = elaborate(Broken, project_id=PROJECT)
    assert not result.ok
    assert result.snapshot is None
    assert result.diagnostics


def test_elaboration_emits_the_tool_plan():
    class Planned(System):
        regulator = Regulator(vin_max=17 * V)

        def architecture(self):
            layout = tools.layout(placers=["pyplacer"], routers=["freerouting"])
            report = tools.check(layout=layout, profile="jlcpcb-2layer")
            tools.export(layout=layout, format="kicad", require=report.passed)

    result = elaborate(Planned, project_id=PROJECT)
    assert result.ok
    assert [call.tool for call in result.plan] == ["layout", "check", "export"]
    # The plan names the snapshot it applies to.
    assert result.plan.snapshot == result.snapshot.hash


def test_a_declared_input_is_hashed_into_the_provenance(tmp_path):
    datasheet = tmp_path / "ds.txt"
    datasheet.write_text("VIN max 17 V")

    result = elaborate(
        Board, project_id=PROJECT, inputs=Inputs.declare({"DS-1": datasheet})
    )
    assert result.ok
    component = next(
        e for e in result.snapshot.entities.values() if isinstance(e, Component)
    )
    recorded = component.provenance.records[0]
    assert [i.id for i in recorded.inputs] == ["DS-1"]
    assert recorded.inputs[0].hash.startswith("sha256:")


def test_a_network_call_during_elaboration_fails_the_build():
    class Networked(System):
        regulator = Regulator(vin_max=17 * V)

        def architecture(self):
            import socket

            socket.socket()

    result = elaborate(Networked, project_id=PROJECT)
    assert not result.ok
    assert result.snapshot is None
    assert "network" in result.diagnostics[0].message


def test_traits_declared_on_a_module_reach_the_registry():
    class WithFootprint(Part):
        vin = Power()

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            self.add_trait(Footprint(library="Package_DFN", name="VQFN-16"))

    class Tiny(System):
        part = WithFootprint()

    result = elaborate(Tiny, project_id=PROJECT)
    assert result.traits.entities_with("footprint")


def test_the_elaboration_result_feeds_the_transaction_gate_unchanged():
    """The language gets no privileged path into canonical state."""
    result = elaborate(Board, project_id=PROJECT)
    graph = KernelGraph(result.snapshot.with_entities({}, "REV-000000"))

    operations = tuple(
        AddEntity(entity=entity, reason="elaborated")
        for entity in sorted(result.snapshot.entities.values(), key=lambda e: e.id)
    )
    proposal = graph.apply(Transaction(graph.head.hash, operations))
    assert proposal.accepted
    assert len(graph.head) == len(result.snapshot)


def test_the_build_time_is_a_declared_input_not_a_wall_clock_read():
    default = elaborate(Board, project_id=PROJECT)
    assert default.snapshot.entities[
        next(iter(sorted(default.snapshot.entities)))
    ].provenance.records[0].created_at == EPOCH

    stamped = elaborate(
        Board, project_id=PROJECT, built_at=datetime(2026, 9, 8, tzinfo=timezone.utc)
    )
    # A different declared build time is a different build record, as it should be.
    assert stamped.snapshot.hash != default.snapshot.hash


def test_the_example_program_elaborates():
    from examples.divider import Divider

    result = elaborate(Divider, project_id="PRJ-DIVIDER")
    assert result.ok
    # Three parts, their surfaces and pins, the connections, and the lowering.
    kinds = {e.kind for e in result.snapshot.entities.values()}
    assert {"component", "pin", "port", "connection", "constraint"} <= kinds
