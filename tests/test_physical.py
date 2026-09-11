"""Spec: The Physical Entity Model; Physical Attributes Resolve Through The
Entity They Realize."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from conftest import PROJECT, tool_provenance
from fang.diff import ChangeClass, diff
from fang.entities import Entity, Net
from fang.graph import Snapshot
from fang.identity import PREFIXES, authored, derive
from fang.physical import (
    PHYSICAL_ATTRIBUTES,
    PHYSICAL_COLLECTIONS,
    PHYSICAL_KEYS,
    Board,
    Layer,
    Pad,
    Placement,
    Point,
    Region,
    Stackup,
    Trace,
    Via,
    Zone,
)
from fang.serialization import canonical_bytes, canonical_dumps
from fang.units import Quantity
from fang.validation import validate

MM = Quantity.scalar("0", "mm").dimension


def trace(id: str, net: str, width: str, **kwargs) -> Trace:
    return Trace(
        authored(id),
        net=net,
        width=Quantity.scalar(width, "mm"),
        provenance=tool_provenance(),
        **kwargs,
    )


def every_kind() -> list[Entity]:
    """One of each physical kind, so a test can sweep them all."""
    return [
        Board(authored("PCB-1"), stackup="STK-1", outline=(Point.of(0, 0), Point.of(10, 0))),
        Stackup(authored("STK-1"), layers=("LYR-TOP", "LYR-BOT")),
        Layer(authored("LYR-TOP"), layer_name="F.Cu", copper_weight=Quantity.scalar("1", "ozcu")),
        Layer(authored("LYR-BOT"), layer_name="B.Cu"),
        Placement(authored("PLC-1"), component="CMP-1", x=Quantity.scalar("5", "mm")),
        Pad(authored("PAD-1"), pin="PIN-1", pad_number="1"),
        Trace(authored("TRC-1"), net="NET-1", width=Quantity.scalar("0.5", "mm")),
        Via(authored("VIA-1"), net="NET-1", layers=("LYR-TOP", "LYR-BOT")),
        Zone(authored("ZONE-1"), net="NET-1"),
        Region(authored("REGION-1"), region_kind="keepout"),
    ]


# -- 1.1 the entity model --------------------------------------------------


def test_every_physical_kind_implements_both_protocol_methods():
    for entity in every_kind():
        assert isinstance(entity.references(), tuple)
        record = entity.as_dict()
        assert record["kind"] == entity.kind
        assert record["id"] == entity.id


def test_every_physical_kind_round_trips_through_canonical_bytes():
    for entity in every_kind():
        encoded = canonical_bytes(entity.as_dict())
        assert json.loads(encoded.decode()) == json.loads(
            canonical_bytes(entity.as_dict()).decode()
        )


def test_every_physical_kind_is_registered_everywhere_it_must_be():
    from fang.diff import _KIND_TO_CHANGED

    for entity in every_kind():
        assert entity.kind in PREFIXES, entity.kind
        assert entity.kind in PHYSICAL_COLLECTIONS, entity.kind
        assert _KIND_TO_CHANGED[entity.kind] is ChangeClass.PHYSICAL_CHANGED


# -- 1.2 a physical entity names what it realizes --------------------------


def test_a_trace_names_the_net_whose_copper_it_is():
    segment = trace("TRC-1", "NET-VBUS", "0.5")
    assert segment.realizes() == ("NET-VBUS",)
    assert "NET-VBUS" in segment.references()


def test_a_trace_does_not_restate_the_net_it_realizes():
    net = Net(authored("NET-VBUS"), aliases=("VBUS",), domain="DOM-POWER")
    record = trace("TRC-1", "NET-VBUS", "0.5").as_dict()
    assert record["net"] == "NET-VBUS"
    for restated in ("aliases", "domain", "members"):
        assert restated not in record
    assert "aliases" in net.as_dict()


def test_a_physical_entity_naming_an_absent_parent_is_a_defect():
    entities = {e.id: e for e in (trace("TRC-1", "NET-MISSING", "0.5"),)}
    report = validate(entities)
    assert not report.ok
    assert any(d.code == "ELAB-0006" for d in report.diagnostics)


# -- 1.3 identity ----------------------------------------------------------


def test_physical_identifiers_derive_reproducibly():
    first = derive(PROJECT, "trace", "board.net.vbus.segment[0]")
    second = derive(PROJECT, "trace", "board.net.vbus.segment[0]")
    assert first.id == second.id
    assert first.id.startswith("TRC-")


def test_geometry_does_not_derive_identity():
    placement = Placement(
        derive(PROJECT, "placement", "board.U1"),
        component="CMP-1",
        x=Quantity.scalar("5", "mm"),
        y=Quantity.scalar("5", "mm"),
    )
    moved = replace(placement, x=Quantity.scalar("40", "mm"))
    assert moved.id == placement.id


# -- 1.4 the root shape ----------------------------------------------------


def test_the_physical_root_carries_every_key_even_when_empty(snapshot):
    root = snapshot.as_dict()
    assert set(root["physical"]) == set(PHYSICAL_KEYS)
    assert all(root["physical"][key] == [] for key in PHYSICAL_KEYS)


def test_physical_entities_group_under_the_physical_root(slice_entities):
    entities = dict(slice_entities)
    for entity in every_kind():
        entities[entity.id] = entity
    root = Snapshot(PROJECT, "REV-000000", entities).as_dict()
    assert [t["id"] for t in root["physical"]["traces"]] == ["TRC-1"]
    assert [b["id"] for b in root["physical"]["boards"]] == ["PCB-1"]
    # and they did not also land in a collection or in extensions
    assert "extensions" not in root
    assert root["components"], "the semantic collections are untouched"


def test_an_unregistered_kind_still_falls_through_to_extensions(slice_entities):
    class Oddity(Entity):
        pass

    entities = dict(slice_entities)
    odd = Oddity(authored("ODD-1"), kind="oddity")
    entities[odd.id] = odd
    root = Snapshot(PROJECT, "REV-000000", entities).as_dict()
    assert [e["id"] for e in root["extensions"]["oddity"]] == ["ODD-1"]


# -- 1.5 ordered where the order is semantic -------------------------------


def test_a_stackup_serializes_top_to_bottom_rather_than_sorted():
    stackup = Stackup(authored("STK-1"), layers=("LYR-TOP", "LYR-INNER", "LYR-BOT"))
    encoded = canonical_dumps(stackup.as_dict())
    assert '"layers":["LYR-TOP","LYR-INNER","LYR-BOT"]' in encoded


def test_a_polygon_keeps_its_vertex_order():
    board = Board(
        authored("PCB-1"),
        outline=(Point.of(10, 0), Point.of(0, 0), Point.of(0, 10)),
    )
    encoded = canonical_dumps(board.as_dict())
    assert encoded.index('"10"') < encoded.index('"0"')


def test_the_physical_collections_are_sorted_by_identifier(slice_entities):
    entities = dict(slice_entities)
    for id in ("TRC-9", "TRC-1", "TRC-5"):
        segment = trace(id, "NET-GND", "0.5")
        entities[segment.id] = segment
    root = Snapshot(PROJECT, "REV-000000", entities).as_dict()
    assert [t["id"] for t in root["physical"]["traces"]] == ["TRC-1", "TRC-5", "TRC-9"]


# -- 1.6 diff classification -----------------------------------------------


def test_moving_a_part_is_a_physical_change_not_an_electrical_one():
    before = Placement(
        authored("PLC-1"), component="CMP-1", x=Quantity.scalar("5", "mm")
    )
    after = replace(before, x=Quantity.scalar("40", "mm"))
    result = diff({before.id: before}, {after.id: after})
    assert [c.type for c in result.changes] == [ChangeClass.PHYSICAL_CHANGED]
    assert not result.electrical


def test_removing_a_trace_does_not_invalidate_an_electrical_check():
    segment = trace("TRC-1", "NET-GND", "0.5")
    result = diff({segment.id: segment}, {})
    assert not result.electrical


# -- 1.7 the schema version ------------------------------------------------


def test_a_one_point_one_artifact_still_reads_under_one_point_two():
    from fang import SCHEMA_VERSION
    from fang.validation import check_schema_version

    assert SCHEMA_VERSION == "1.2"
    check_schema_version("1.1")  # additive minor: still readable


def test_an_unimplemented_major_version_is_still_rejected():
    from fang.diagnostics import FangError
    from fang.validation import check_schema_version

    with pytest.raises(FangError) as caught:
        check_schema_version("2.0")
    assert caught.value.diagnostic.code == "ELAB-0009"


def test_the_schema_version_moves_independently_of_the_compiler_version():
    from fang import SCHEMA_VERSION, __version__

    assert SCHEMA_VERSION != __version__
