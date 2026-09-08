"""Shared fixtures: one small design that exercises the kernel end to end."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from fang.constraints import (
    Constraint,
    ConstraintRegistry,
    Enforcement,
    Literal,
    Ref,
    le,
)
from fang.entities import (
    Component,
    Connection,
    ConnectionKind,
    Decision,
    Domain,
    Evidence,
    Net,
    Rail,
    Requirement,
    RequirementState,
)
from fang.graph import CONSTRAINT_CHECK, KernelGraph, Snapshot
from fang.identity import authored, derive
from fang.provenance import (
    Actor,
    ActorKind,
    Provenance,
    ProvenanceOrigin,
    ProvenanceRecord,
)
from fang.diagnostics import SourceLocation
from fang.units import Quantity
from fang.values import Value

PROJECT = "PRJ-VERTICAL-SLICE"
WATTS = Quantity.scalar("0", "W").dimension
VOLTS = Quantity.scalar("0", "V").dimension
FIXED_TIME = datetime(2026, 9, 8, 11, 4, 22, tzinfo=timezone.utc)

#: The derived identifiers of the slice, computed rather than written down, so
#: the fixtures cannot drift from the derivation rules.
REGULATOR = derive(PROJECT, "component", "system.power.buck_3v3.U1").id
CONTROLLER = derive(PROJECT, "component", "system.logic.mcu").id


def tool_provenance(*, derived_from=(), file="power/buck_3v3.py", line=42) -> Provenance:
    return Provenance().append(
        ProvenanceRecord(
            ProvenanceOrigin.GENERATED,
            "elaboration",
            Actor(ActorKind.TOOL, "fang", "0.1.0"),
            "REV-000001",
            FIXED_TIME,
            derived_from=tuple(derived_from),
            source_location=SourceLocation(file, line),
        )
    )


@pytest.fixture(autouse=True)
def clean_registry():
    """Each test gets a fresh registry namespace."""
    yield
    ConstraintRegistry.release(PROJECT)


@pytest.fixture
def slice_entities():
    """A controller, a rail, a ground domain, a bus, and a topology-relevant path."""
    requirement = Requirement(
        authored("REQ-PWR-001"),
        statement="Input shall tolerate 36 V continuous",
        state=RequirementState.KNOWN,
        source="user",
        validation_method="analysis",
    )
    evidence = Evidence(
        authored("EVD-TPS62130-VIN"),
        claim="Absolute maximum VIN is 17 V",
        document="SRC-DS-TPS62130",
        locator="table 6.1",
    )
    decision = Decision(
        authored("DEC-017"),
        question="Select 3.3 V buck regulator",
        choice="CMP-U1",
        rationale=("efficiency target", "input voltage margin"),
        requirements=("REQ-PWR-001",),
        provenance=tool_provenance(derived_from=("REQ-PWR-001",)),
    )
    regulator = Component(
        derive(PROJECT, "component", "system.power.buck_3v3.U1"),
        designator="U1",
        part="TPS62130",
        parameters={
            "power_dissipation": Value.explicit(Quantity.scalar("0.1", "W")),
            "vin_max": Value.inferred(
                Quantity.scalar("17", "V"), "EVD-TPS62130-VIN", "0.9"
            ),
        },
        provenance=tool_provenance(derived_from=("DEC-017",)),
    )
    controller = Component(
        derive(PROJECT, "component", "system.logic.mcu"),
        designator="U2",
        part="STM32G474",
        provenance=tool_provenance(line=88),
    )
    rail = Rail(
        authored("RAIL-3V3"),
        parameters={"voltage": Value.explicit(Quantity.with_tolerance("3.3", "0.02", "V"))},
        source_blocks=(),
        load_blocks=(),
    )
    logic_ground = Domain(authored("DOM-LOGIC"), domain_kind="ground")
    motor_ground = Domain(authored("DOM-MOTOR"), domain_kind="ground")
    star = Net(authored("NET-MOTOR-STAR"))
    chassis = Net(authored("NET-CHASSIS"))
    ground = Net(authored("NET-GND"))

    entities = {
        e.id: e
        for e in (
            requirement,
            evidence,
            decision,
            regulator,
            controller,
            rail,
            logic_ground,
            motor_ground,
            star,
            chassis,
            ground,
        )
    }
    return entities


@pytest.fixture
def snapshot(slice_entities):
    return Snapshot(PROJECT, "REV-000000", slice_entities)


@pytest.fixture
def kernel(snapshot):
    return KernelGraph(snapshot, checks=(CONSTRAINT_CHECK,))


@pytest.fixture
def power_constraint():
    return Constraint(
        authored("RULE-PWR-1"),
        constraint_kind="max_power_dissipation",
        targets=(REGULATOR,),
        expression=le(
            Ref(REGULATOR, "power_dissipation", WATTS),
            Literal.of(Quantity.scalar("0.25", "W")),
        ),
        enforcement=Enforcement.HARD,
        source="REQ-PWR-001",
    )


def conductive(id: str, source: str, target: str, kind=ConnectionKind.GROUND) -> Connection:
    return Connection(authored(id), connection_kind=kind, source=source, target=target)
