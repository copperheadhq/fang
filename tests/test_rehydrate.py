"""Spec: A Persisted Snapshot Reloads Without Running A Program.

Every decoder is checked the way the kernel uses it: serialize to the canonical
form, parse that as JSON the way the record stream is read, decode, and
serialize again. Equal bytes are the contract, because equal bytes are what keep
a snapshot's hash.
"""

import json
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

from conftest import FIXED_TIME, PROJECT, VOLTS, WATTS, tool_provenance

from examples.divider.divider import Divider
from examples.regenerate import PROJECT as EXAMPLES_PROJECT, examples as example_names
from fang import rehydrate
from fang.cli import load_system
from fang.constraints import (
    Arithmetic,
    CheckStatus,
    Constraint,
    ConstraintClass,
    Enforcement,
    Literal,
    Logical,
    Ref,
    VerificationMethod,
    le,
    node_from_dict,
)
from fang.diagnostics import (
    ELAB_DUPLICATE_ID,
    ELAB_MALFORMED_RECORD,
    ELAB_SNAPSHOT_MISMATCH,
    FangError,
    SourceLocation,
)
from fang.elaborate import elaborate
from fang.entities import (
    Assumption,
    Bus,
    Calculation,
    Component,
    Connection,
    ConnectionKind,
    Decision,
    Domain,
    Entity,
    Evidence,
    Interface,
    Model,
    Net,
    Pin,
    Port,
    Rail,
    Requirement,
    RequirementState,
    Signal,
    Verification,
)
from fang.graph import _COLLECTION_OF, Snapshot
from fang.identity import Identity, Path as SemanticPath, authored, derive, imported
from fang.netlist import compile_netlist
from fang.provenance import (
    Actor,
    ActorKind,
    Confidence,
    Input,
    Provenance,
    ProvenanceOrigin,
    ProvenanceRecord,
)
from fang.rehydrate import OpaqueEntity, decode_record, decode_records, entity_decoders
from fang.serialization import (
    canonical_dumps,
    canonical_record_stream,
    parse_rfc3339,
    rfc3339,
)
from fang.topology import TopologyConstraint, TopologyMode
from fang.traits import (
    DatasheetEvidence,
    Footprint,
    OpaqueTrait,
    Renderable,
    Simulatable,
    Sourcing,
    Trait,
    TraitRegistry,
    trait_decoders,
)
from fang.units import Dimension, Quantity
from fang.values import Candidate, ConflictingValue, Value, parameter_from_dict
from fang.workspace import Workspace

AMPS = Quantity.scalar("1", "A").dimension
OHMS = Quantity.scalar("1", "Ohm").dimension

ROOT = Path(__file__).resolve().parent.parent / "examples"
EXAMPLES = [ROOT / name / f"{name}.py" for name in example_names()]


def on_disk(record: dict) -> dict:
    """What reading the record stream hands a decoder: parsed canonical JSON."""
    return json.loads(canonical_dumps(record))


def same_bytes(left, right) -> bool:
    return canonical_dumps(left) == canonical_dumps(right)


# --------------------------------------------------------------------------
# Value types
# --------------------------------------------------------------------------

IDENTITIES = [
    authored("REQ-PWR-001"),
    authored("REQ-PWR-002", display_name="input range"),
    derive(PROJECT, "component", "system.power.buck_3v3.U1", key="U1", display_name="TPS62130"),
    imported("NET-7f3a", "GND", path=SemanticPath.parse("board.gnd"), display_name="GND"),
]


@pytest.mark.parametrize("identity", IDENTITIES, ids=lambda identity: identity.id)
def test_an_identity_round_trips(identity):
    assert Identity.from_dict(on_disk(identity.as_dict())) == identity


def test_a_source_location_round_trips_with_and_without_a_column():
    for location in (SourceLocation("power/buck.py", 42), SourceLocation("power/buck.py", 42, 7)):
        assert SourceLocation.from_dict(on_disk(location.as_dict())) == location


def test_rfc3339_parses_exactly_the_form_it_writes():
    assert parse_rfc3339(rfc3339(FIXED_TIME)) == FIXED_TIME
    assert parse_rfc3339("2026-09-08T11:04:22.5Z").microsecond == 500000
    for text in ("2026-09-08T11:04:22+00:00", "2026-09-08 11:04:22Z", "2026-09-08", 1757329462):
        with pytest.raises(ValueError):
            parse_rfc3339(text)


def test_a_provenance_chain_round_trips_oldest_first():
    chain = (
        tool_provenance(derived_from=("DEC-017", "REQ-PWR-001"))
        .append(
            ProvenanceRecord(
                ProvenanceOrigin.INFERRED,
                "datasheet_extraction",
                Actor(ActorKind.MODEL, "extractor", "2"),
                "REV-000002",
                FIXED_TIME,
                inputs=(Input("SRC-DS-TPS62130", "sha256:" + "0" * 64),),
                source_location=SourceLocation("ds.pdf", 12, 3),
                confidence=Confidence.INFERRED,
            )
        )
        .append(
            ProvenanceRecord(
                ProvenanceOrigin.IMPORTED,
                "netlist_import",
                Actor(ActorKind.ADAPTER, "kicad"),
                "REV-000003",
                FIXED_TIME,
            )
        )
    )
    # Wrapped in its key, because the key is what declares the list ordered.
    stored = on_disk({"provenance": chain.as_list()})
    decoded = Provenance.from_list(stored["provenance"])
    assert [record.activity for record in decoded] == [record.activity for record in chain]
    assert same_bytes({"provenance": decoded.as_list()}, {"provenance": chain.as_list()})


QUANTITIES = [
    Quantity.scalar("3.3", "V"),
    Quantity.scalar("0.1", "W", conditions={"ambient": "25 degC"}),
    Quantity.range("2.7", "5.5", "V", typical="3.3"),
    Quantity.range("-40", "85", "degC"),
    Quantity.with_tolerance("10", "0.01", "kOhm"),
    Quantity.with_tolerance("3.3", "0.1", "V", kind="absolute"),
    Quantity.scalar("9.81", "m/s^2"),
    Quantity.scalar("1", "1"),
]


@pytest.mark.parametrize("quantity", QUANTITIES, ids=str)
def test_a_quantity_round_trips(quantity):
    decoded = Quantity.from_dict(on_disk(quantity.as_dict()))
    assert decoded == quantity
    assert same_bytes(decoded.as_dict(), quantity.as_dict())


def test_a_dimension_round_trips_with_a_rational_exponent():
    dimension = AMPS ** Fraction(1, 2) * OHMS
    assert Dimension.from_list(dimension.as_list()) == dimension


def test_a_dimension_keeps_its_order_in_canonical_form():
    """The exponents are positional; sorting them would change the dimension."""
    record = on_disk(Ref("CMP-A", "voltage", VOLTS).as_dict())
    assert Dimension.from_list(record["dimension"]) == VOLTS


CONFLICT = ConflictingValue(
    (
        Candidate(Value.explicit(Quantity.scalar("17", "V")), "EVD-A"),
        Candidate(Value.explicit(Quantity.scalar("20", "V")), "EVD-B"),
    )
)

VALUES = [
    Value.explicit(Quantity.scalar("3.3", "V")),
    Value.explicit(Quantity.scalar("3.3", "V"), source="REQ-PWR-001"),
    Value.inferred(Quantity.scalar("17", "V"), "EVD-TPS62130-VIN", "0.9"),
    Value.assumed(Quantity.scalar("25", "degC"), "typical bench ambient"),
    Value.unknown(),
    CONFLICT,
    CONFLICT.resolve("EVD-A", "DEC-017"),
]


@pytest.mark.parametrize("value", VALUES, ids=lambda value: type(value).__name__)
def test_a_parameter_round_trips(value):
    assert parameter_from_dict(on_disk(value.as_dict())) == value


@pytest.mark.parametrize(
    "signal",
    [Signal("scl", "clock"), Signal("sda", "data", direction="bidirectional", required=False)],
    ids=lambda signal: signal.name,
)
def test_a_signal_round_trips(signal):
    assert Signal.from_dict(on_disk(signal.as_dict())) == signal


NODES = [
    Literal.of(Quantity.scalar("0.25", "W")),
    Literal.of(3),
    Literal.of("SOIC-8"),
    Literal.of(True),
    Literal.of(False),
    Ref("CMP-A", "current", AMPS),
    Arithmetic("pow", (Ref("CMP-A", "current", AMPS),), Fraction(2)),
    Arithmetic("pow", (Ref("CMP-A", "current", AMPS),), Fraction(1, 2)),
    Arithmetic("sub", (Ref("CMP-A", "v_in", VOLTS), Ref("CMP-A", "v_out", VOLTS))),
    le(
        Arithmetic("mul", (Ref("CMP-A", "current", AMPS), Ref("CMP-A", "resistance", OHMS))),
        Literal.of(Quantity.scalar("5", "V")),
    ),
    Logical("and", (Literal.of(True), Logical("not", (Literal.of(False),)))),
]


@pytest.mark.parametrize("node", NODES, ids=lambda node: node.as_dict()["node"])
def test_an_expression_node_round_trips_with_its_operand_order(node):
    decoded = node_from_dict(on_disk(node.as_dict()))
    assert decoded == node
    assert decoded.dimension == node.dimension


# --------------------------------------------------------------------------
# Every entity kind
# --------------------------------------------------------------------------


def _catalogue() -> list[Entity]:
    """At least one entity of every class, with optional fields both set and unset."""
    provenance = tool_provenance(derived_from=("REQ-PWR-001",))
    carried = {
        "footprint": Footprint(library="Package_DFN_QFN", name="VQFN-16"),
        "sourcing": Sourcing(
            manufacturer="TI", mpn="TPS62130RGTR", distributor_ids={"lcsc": "C123"}
        ),
        "datasheet_evidence": DatasheetEvidence(
            document="SRC-DS-TPS62130", evidence_ids=("EVD-2", "EVD-1")
        ),
        "simulatable": Simulatable(
            backends=("xyce", "ngspice"),
            source="vendor/TPS62130.lib",
            pin_map={"1": "VIN"},
            conditions={"ambient": "25 degC"},
            distribution_restricted=True,
            provenance=provenance,
        ),
        "renderable": Renderable(symbol="regulator"),
    }
    return [
        Entity(identity=derive(PROJECT, "block", "system.power"), kind="block"),
        Entity(
            identity=derive(PROJECT, "block", "system.logic", display_name="Logic"),
            kind="block",
            parameters={"supply": Value.explicit(Quantity.scalar("3.3", "V"))},
            provenance=provenance,
            source_location=SourceLocation("logic.py", 3, 1),
            extensions={"kicad": {"sheet": "logic", "fields": ["b", "a"]}},
            traits={"renderable": Renderable(symbol="block"), "simulatable": Simulatable()},
        ),
        Requirement(
            authored("REQ-PWR-001"),
            statement="Input shall tolerate 36 V continuous",
            validation_method="analysis",
        ),
        Requirement(
            authored("REQ-PWR-002"),
            statement="Quiescent current is not yet known",
            state=RequirementState.MISSING,
            priority="SHOULD",
            source="datasheet",
        ),
        Connection(
            authored("CN-1"), connection_kind=ConnectionKind.POWER, source="CMP-A", target="RAIL-3V3"
        ),
        Connection(
            authored("CN-2"),
            connection_kind=ConnectionKind.SIGNAL,
            source="PORT-1",
            target="PORT-2",
            derived_from_interface="IF-I2C",
        ),
        Component(
            derive(PROJECT, "component", "system.power.buck_3v3.U1", display_name="TPS62130"),
            designator="U1",
            part="TPS62130",
            package="VQFN-16",
            models=("MOD-2", "MOD-1"),
            parameters={
                "vin": Value.inferred(Quantity.scalar("17", "V"), "EVD-1", "0.9"),
                "vin_max": CONFLICT,
                "tj": Value.unknown(),
                "iq": Value.assumed(Quantity.scalar("20", "uA"), "typical of the family"),
            },
            provenance=provenance,
            traits=carried,
        ),
        Component(authored("CMP-BARE")),
        Net(authored("NET-GND")),
        Net(
            imported("NET-7f3a", "GND", display_name="GND"),
            aliases=("DGND", "AGND"),
            domain="DOM-LOGIC",
            members=("PIN-2", "PIN-1"),
        ),
        Rail(
            authored("RAIL-3V3"),
            members=("PIN-3",),
            source_blocks=("BLK-2", "BLK-1"),
            load_blocks=("BLK-3",),
            power_sequence=("RAIL-5V", "RAIL-3V3", "RAIL-1V8"),
        ),
        Interface(
            authored("IF-I2C"),
            interface_type="i2c",
            signals=(
                Signal("sda", "data", direction="bidirectional"),
                Signal("scl", "clock", required=False),
            ),
            direction="controller",
        ),
        Interface(authored("IF-NONE"), interface_type="none"),
        Port(authored("PORT-1"), interface="IF-I2C", owner="CMP-A"),
        Port(authored("PORT-2"), interface="IF-I2C", owner="CMP-B", direction="target"),
        Pin(authored("PIN-1"), owner="CMP-A", vendor_name="VIN", role="power_in", number="1"),
        Pin(authored("PIN-2"), owner="CMP-A", vendor_name="NC"),
        Bus(authored("BUS-I2C"), interface="IF-I2C", participants=("PORT-2", "PORT-1")),
        Domain(authored("DOM-LOGIC"), domain_kind="ground", members=("NET-GND",)),
        Decision(
            authored("DEC-017"),
            question="Select 3.3 V buck regulator",
            choice="CMP-A",
            rationale=("input voltage margin", "efficiency target"),
            alternatives_rejected=(
                {"part": "LM2596", "reason": "too large"},
                {"option": "LDO", "reason": "dissipates too much"},
            ),
            requirements=("REQ-PWR-001",),
        ),
        Decision(authored("DEC-018"), question="Which connector?"),
        Evidence(
            authored("EVD-1"),
            claim="Absolute maximum VIN is 17 V",
            document="SRC-DS-TPS62130",
            locator="table 6.1",
        ),
        Evidence(authored("EVD-2"), claim="An uncited claim"),
        Calculation(
            authored("CALC-1"),
            expression="P = I^2 * R",
            inputs=("CMP-B", "CMP-A"),
            result="0.1 W",
            requirements=("REQ-PWR-001",),
        ),
        Calculation(authored("CALC-2"), expression="x"),
        Verification(
            authored("VER-1"), verifies="REQ-PWR-001", method="test", evidence=("EVD-1",), result="PASS"
        ),
        Verification(authored("VER-2")),
        Assumption(authored("ASM-1"), claim="Ambient stays below 40 degC", rationale="indoor enclosure"),
        Model(
            authored("MOD-1"),
            component="CMP-A",
            backends=("ngspice",),
            source="vendor/a.lib",
            pin_map={"1": "VIN"},
            conditions={"ambient": "25 degC"},
            distribution_restricted=True,
        ),
        Model(authored("MOD-2"), component="CMP-A"),
        Constraint(
            authored("RULE-PWR-1"),
            constraint_kind="max_power_dissipation",
            targets=("CMP-A",),
            expression=le(Ref("CMP-A", "power_dissipation", WATTS), Literal.of(Quantity.scalar("0.25", "W"))),
        ),
        Constraint(
            authored("RULE-PWR-2"),
            constraint_class=ConstraintClass.PHYSICS,
            constraint_kind="ohmic_drop",
            targets=("CMP-B", "CMP-A"),
            expression=NODES[9],
            applicability=Logical("not", (Literal.of(False),)),
            enforcement=Enforcement.SOFT,
            verification_method=VerificationMethod.RULE_CHECK,
            verification_status=CheckStatus.PASS,
            source="REQ-PWR-001",
        ),
        TopologyConstraint(
            authored("RULE-TOPO-1"),
            net="NET-GND",
            center="NET-MOTOR-STAR",
            branches=("DOM-MOTOR", "DOM-LOGIC"),
        ),
        TopologyConstraint(
            authored("RULE-TOPO-2"),
            net="NET-CHASSIS",
            mode=TopologyMode.MESH,
            forbid_parallel_paths=False,
            enforcement=Enforcement.ADVISORY,
        ),
    ]


CATALOGUE = _catalogue()


@pytest.mark.parametrize("entity", CATALOGUE, ids=lambda e: f"{type(e).__name__}:{e.id}")
def test_every_entity_kind_round_trips_through_its_decoder(entity):
    decoded, untyped = decode_record(on_disk(entity.as_dict()))
    assert type(decoded) is type(entity)
    assert untyped == ()
    assert same_bytes(decoded.as_dict(), entity.as_dict())


def _subclasses(cls):
    for subclass in cls.__subclasses__():
        yield subclass
        yield from _subclasses(subclass)


def test_every_entity_class_and_trait_class_has_a_registered_decoder():
    decoders = entity_decoders()
    classes = {
        cls
        for cls in _subclasses(Entity)
        if cls.__module__.startswith("fang.")
        and not cls.__name__.startswith("_")
        and cls is not OpaqueEntity
    }
    assert classes
    for cls in classes:
        assert cls.__dataclass_fields__["kind"].default in decoders, cls.__name__
    assert "block" in decoders
    # A class that shares a kind is told apart by its decoder, so each needs an
    # entity above that proves the dispatch lands on it.
    assert classes <= {type(entity) for entity in CATALOGUE}

    protocols = trait_decoders()
    for cls in _subclasses(Trait):
        if cls.__module__.startswith("fang.") and cls is not OpaqueTrait:
            assert cls.protocol in protocols, cls.__name__


def test_the_catalogue_exercises_every_registered_decoder():
    """A decoder nothing round-trips is a decoder nothing checks."""
    assert {entity.kind for entity in CATALOGUE} == set(entity_decoders())
    assert {protocol for entity in CATALOGUE for protocol in entity.traits} == set(trait_decoders())


def test_only_kinds_that_no_class_defines_lack_a_decoder():
    assert set(_COLLECTION_OF) - set(entity_decoders()) == {"circuit", "outcome"}


# --------------------------------------------------------------------------
# What cannot be typed is kept; what cannot be read is refused
# --------------------------------------------------------------------------

CIRCUIT = {
    "id": "CKT-1",
    "kind": "circuit",
    "identity": {"id": "CKT-1", "origin": "authored"},
    "blocks": ["BLK-1", "BLK-2"],
}


def _component_record(**extra) -> dict:
    record = on_disk(
        Component(
            authored("CMP-A"), part="TPS62130", traits={"footprint": Footprint("L", "N")}
        ).as_dict()
    )
    record.update(extra)
    return record


def test_a_record_of_an_unregistered_kind_is_kept_and_reported():
    entity, untyped = decode_record(on_disk(CIRCUIT))
    assert isinstance(entity, OpaqueEntity)
    assert (entity.id, entity.kind, entity.references()) == ("CKT-1", "circuit", ())
    assert same_bytes(entity.as_dict(), CIRCUIT)
    assert [(item.subject, item.construct) for item in untyped] == [("CKT-1", "kind circuit")]


def test_a_known_record_with_an_unmodelled_key_is_kept_whole():
    record = _component_record(thermal_resistance="40 K/W")
    entity, untyped = decode_record(record)
    assert isinstance(entity, OpaqueEntity) and entity.kind == "component"
    assert same_bytes(entity.as_dict(), record)
    assert "thermal_resistance" in untyped[0].reason


def test_a_trait_of_an_unregistered_protocol_is_kept_on_a_typed_entity():
    record = _component_record()
    record["traits"]["thermal"] = {"protocol": "thermal", "theta_ja": "40"}
    entity, untyped = decode_record(record)
    assert isinstance(entity, Component)
    assert isinstance(entity.traits["footprint"], Footprint)
    assert isinstance(entity.traits["thermal"], OpaqueTrait)
    assert same_bytes(entity.as_dict(), record)
    assert [(item.subject, item.construct) for item in untyped] == [("CMP-A", "trait thermal")]


def test_a_trait_with_an_unmodelled_key_is_kept_on_a_typed_entity():
    record = _component_record()
    record["traits"]["footprint"]["pad_count"] = 16
    entity, untyped = decode_record(record)
    assert isinstance(entity, Component)
    assert isinstance(entity.traits["footprint"], OpaqueTrait)
    assert same_bytes(entity.as_dict(), record)
    assert [item.construct for item in untyped] == ["trait footprint"]


def test_a_record_that_would_not_reserialize_identically_is_kept_verbatim():
    record = on_disk(
        Component(
            authored("CMP-A"), parameters={"voltage": Value.explicit(Quantity.scalar("3.3", "V"))}
        ).as_dict()
    )
    record["parameters"]["voltage"]["quantity"]["value"] = "3.30"
    entity, untyped = decode_record(record)
    assert isinstance(entity, OpaqueEntity)
    assert same_bytes(entity.as_dict(), record)
    assert "reserialize" in untyped[0].reason


def test_a_later_change_registers_its_own_kind(monkeypatch):
    monkeypatch.setattr(rehydrate, "_DECODERS", dict(rehydrate._DECODERS))
    rehydrate.register_entity(
        "circuit",
        lambda record: Entity(identity=Identity.from_dict(record["identity"]), kind="circuit"),
    )
    record = {key: CIRCUIT[key] for key in ("id", "kind", "identity")}
    entity, untyped = decode_record(on_disk(record))
    assert type(entity) is Entity and untyped == ()


@pytest.mark.parametrize(
    "entity, mutate, named",
    [
        (Requirement(authored("REQ-1"), statement="s"), lambda r: r.pop("statement"), "statement"),
        (
            Pin(authored("PIN-1"), owner="CMP-A", vendor_name="VIN"),
            lambda r: r.update(owner=5),
            "owner",
        ),
        (
            Connection(authored("CN-1"), connection_kind=ConnectionKind.POWER, source="A", target="B"),
            lambda r: r.update(connection_kind="wireless"),
            "connection_kind",
        ),
        (Component(authored("CMP-A")), lambda r: r.update(id="CMP-B"), "id"),
        (
            Component(
                authored("CMP-A"), parameters={"v": Value.explicit(Quantity.scalar("3.3", "V"))}
            ),
            lambda r: r["parameters"]["v"]["quantity"].update(unit="furlong"),
            "furlong",
        ),
        (
            Component(authored("CMP-A"), traits={"footprint": Footprint("L", "N")}),
            lambda r: r["traits"]["footprint"].update(name=7),
            "footprint.name",
        ),
    ],
    ids=["missing-field", "wrong-type", "enum-outside-its-set", "id-disagrees", "unknown-unit", "bad-trait-field"],
)
def test_a_malformed_record_refuses_the_whole_load_naming_the_record(entity, mutate, named):
    record = on_disk(entity.as_dict())
    mutate(record)
    with pytest.raises(FangError) as failure:
        decode_records([on_disk(Component(authored("CMP-OK")).as_dict()), record])
    diagnostic = failure.value.diagnostic
    assert diagnostic.code == ELAB_MALFORMED_RECORD
    assert named in diagnostic.message
    assert diagnostic.entities == (record["id"],)


def test_two_records_with_one_id_refuse_the_load():
    record = on_disk(Component(authored("CMP-A")).as_dict())
    with pytest.raises(FangError) as failure:
        decode_records([record, record])
    assert failure.value.diagnostic.code == ELAB_DUPLICATE_ID


# --------------------------------------------------------------------------
# Workspaces
# --------------------------------------------------------------------------


@pytest.fixture(scope="module", params=EXAMPLES, ids=[path.stem for path in EXAMPLES])
def saved(request, tmp_path_factory):
    """An example elaborated once and written to a workspace of its own."""
    result = elaborate(load_system(request.param), project_id=EXAMPLES_PROJECT)
    assert result.ok, [d.message for d in result.diagnostics]
    workspace = Workspace(tmp_path_factory.mktemp(request.param.stem))
    return result, workspace, workspace.write_snapshot(result.snapshot)


def test_the_examples_are_not_empty():
    assert len(EXAMPLES) >= 8


def test_a_reloaded_example_has_the_hash_it_was_saved_with(saved):
    result, workspace, manifest = saved
    loaded = Workspace(workspace.root).read_snapshot()
    assert loaded.report.complete, [item.as_dict() for item in loaded.report.untyped]
    assert loaded.report.decoded == len(result.snapshot.entities)
    assert loaded.snapshot.hash == manifest.snapshot == result.snapshot.hash
    assert canonical_record_stream(loaded.snapshot.records()) == workspace.design_path.read_bytes()


def test_a_netlist_compiled_from_a_reloaded_example_matches_the_elaboration(saved):
    result, workspace, _ = saved
    reloaded = Workspace(workspace.root).read_snapshot().snapshot
    from_program = compile_netlist(result.snapshot, traits=result.traits)
    from_workspace = compile_netlist(reloaded)
    assert from_workspace.as_dict() == from_program.as_dict()
    assert all(component.footprint for component in from_workspace.components)


def test_traits_are_enumerable_from_a_reloaded_example(saved):
    result, workspace, _ = saved
    reloaded = Workspace(workspace.root).read_snapshot().snapshot
    registry = TraitRegistry.from_entities(reloaded.entities)
    assert registry.protocols() == result.traits.protocols()
    for protocol in registry.protocols():
        assert registry.entities_with(protocol) == result.traits.entities_with(protocol)
    for entity_id in registry.entities_with("footprint"):
        before = result.snapshot.entities[entity_id].traits["footprint"]
        after = reloaded.entities[entity_id].traits["footprint"]
        assert after == before and after is not before


def test_an_elaborated_entity_holds_a_copy_of_its_modules_traits():
    board = Divider()
    result = elaborate(board, project_id=PROJECT)
    top = next(
        entity
        for entity in result.snapshot.entities.values()
        if isinstance(entity, Component) and str(entity.identity.path) == "system.top"
    )
    declared = next(trait for trait in board.top.traits if trait.protocol == "footprint")
    assert top.traits["footprint"] == declared
    assert top.traits["footprint"] is not declared


def test_the_slice_and_an_untyped_record_survive_a_workspace_round_trip(tmp_path, snapshot):
    circuit, _ = decode_record(on_disk(CIRCUIT))
    extended = snapshot.with_entities({**snapshot.entities, circuit.id: circuit}, snapshot.revision_id)
    manifest = Workspace(tmp_path).write_snapshot(extended)

    loaded = Workspace(tmp_path).read_snapshot()
    assert loaded.snapshot.hash == manifest.snapshot
    assert loaded.report.decoded == len(snapshot.entities)
    assert [item.subject for item in loaded.report.untyped] == ["CKT-1"]
    assert isinstance(loaded.snapshot.entities["CKT-1"], OpaqueEntity)
    assert canonical_dumps(loaded.report.as_dict())


def test_the_manifest_records_the_extracted_upstream_the_hash_covers(tmp_path, snapshot):
    upstream = replace(snapshot, extracted_upstream=("SRC-B", "SRC-A"))
    manifest = Workspace(tmp_path).write_snapshot(upstream)
    stored = json.loads(Workspace(tmp_path).manifest_path.read_text())
    assert stored["extracted_upstream"] == ["SRC-A", "SRC-B"]
    assert Workspace(tmp_path).read_snapshot().snapshot.hash == manifest.snapshot == upstream.hash


def test_a_stream_that_does_not_match_its_manifest_is_refused(tmp_path):
    result = elaborate(Divider, project_id=PROJECT)
    workspace = Workspace(tmp_path)
    manifest = workspace.write_snapshot(result.snapshot)
    records = workspace.read_records()
    next(record for record in records if record["kind"] == "component")["part"] = "Other"
    workspace.design_path.write_bytes(canonical_record_stream(records))

    with pytest.raises(FangError) as failure:
        workspace.read_snapshot()
    diagnostic = failure.value.diagnostic
    assert diagnostic.code == ELAB_SNAPSHOT_MISMATCH
    assert manifest.snapshot in diagnostic.message
    assert diagnostic.message.count("sha256:") == 2


def test_a_malformed_design_file_loads_nothing(tmp_path):
    result = elaborate(Divider, project_id=PROJECT)
    workspace = Workspace(tmp_path)
    workspace.write_snapshot(result.snapshot)
    records = workspace.read_records()
    pin = next(record for record in records if record["kind"] == "pin")
    del pin["owner"]
    workspace.design_path.write_bytes(canonical_record_stream(records))

    with pytest.raises(FangError) as failure:
        workspace.read_snapshot()
    assert failure.value.diagnostic.code == ELAB_MALFORMED_RECORD
    assert failure.value.diagnostic.entities == (pin["id"],)


def test_a_workspace_written_before_traits_were_persisted_still_loads(tmp_path):
    result = elaborate(Divider, project_id=PROJECT)
    bare = {entity_id: replace(entity, traits={}) for entity_id, entity in result.snapshot.entities.items()}
    earlier = replace(result.snapshot, entities=bare, schema_version="1.1")
    workspace = Workspace(tmp_path)
    manifest = workspace.write_snapshot(earlier)
    assert b'"traits"' not in workspace.design_path.read_bytes()

    loaded = workspace.read_snapshot()
    assert loaded.snapshot.schema_version == "1.1"
    assert loaded.snapshot.hash == manifest.snapshot
    assert loaded.report.complete
    assert not any(entity.traits for entity in loaded.snapshot.entities.values())
