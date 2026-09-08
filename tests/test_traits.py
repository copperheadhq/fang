"""Spec: Traits As The Extension Mechanism; Trait Registration And Enumeration."""

import pytest

from fang.traits import (
    DatasheetEvidence,
    Footprint,
    Renderable,
    Simulatable,
    Sourcing,
    Trait,
    TraitRegistry,
)


def test_a_trait_declares_the_protocol_it_satisfies():
    assert Footprint().protocol == "footprint"
    assert Simulatable().protocol == "simulatable"

    class Custom(Trait):
        pass

    assert Custom().protocol == "custom"


def test_a_trait_without_a_protocol_is_refused():
    registry = TraitRegistry()
    naked = Trait()
    with pytest.raises(ValueError):
        registry.attach("CMP-1", naked)


def test_traits_are_enumerable_by_protocol_without_instantiating_a_backend():
    registry = TraitRegistry()
    registry.attach("CMP-1", Simulatable(model_kind="spice_subckt", backends=("ngspice",)))
    registry.attach("CMP-2", Simulatable(model_kind="behavioural", backends=("xyce",)))
    registry.attach("CMP-3", Footprint(library="Package_SO", name="SOIC-8"))

    assert registry.entities_with("simulatable") == ["CMP-1", "CMP-2"]
    assert registry.entities_with("footprint") == ["CMP-3"]
    assert registry.entities_with("nothing") == []


def test_a_component_gains_capabilities_without_widening_its_class():
    from fang.lang import Part

    class TPS62130(Part):
        pass

    part = TPS62130()
    part.add_trait(Footprint(library="Package_DFN", name="VQFN-16"))
    part.add_trait(Sourcing(manufacturer="TI", mpn="TPS62130RGTR"))
    part.add_trait(DatasheetEvidence(document="SRC-DS-TPS62130", evidence_ids=("EVD-1",)))

    assert {trait.protocol for trait in part.traits} == {
        "footprint", "sourcing", "datasheet_evidence"
    }
    # The class itself is untouched.
    assert type(part).__mro__ == TPS62130.__mro__


def test_a_model_trait_carries_its_own_provenance():
    from datetime import datetime, timezone

    from fang.provenance import Actor, ActorKind, Provenance, ProvenanceOrigin, ProvenanceRecord

    provenance = Provenance().append(
        ProvenanceRecord(
            ProvenanceOrigin.IMPORTED,
            "vendor_model_import",
            Actor(ActorKind.ADAPTER, "vendor-lib"),
            "REV-1",
            datetime(2026, 9, 8, tzinfo=timezone.utc),
        )
    )
    trait = Simulatable(source="vendor/TPS62130.lib", provenance=provenance)
    assert "provenance" in trait.as_dict()


def test_a_restricted_model_records_that_fact():
    trait = Simulatable(source="vendor/secret.lib", distribution_restricted=True)
    assert trait.as_dict()["distribution_restricted"] is True


def test_the_registry_serializes_deterministically():
    from fang.serialization import canonical_bytes

    registry = TraitRegistry()
    registry.attach("CMP-2", Renderable(symbol="resistor"))
    registry.attach("CMP-1", Footprint(library="L", name="N"))
    assert canonical_bytes(registry.as_dict()) == canonical_bytes(registry.as_dict())
    assert registry.protocols() == ["footprint", "renderable"]


def test_lookup_by_entity_and_protocol():
    registry = TraitRegistry()
    footprint = Footprint(library="Package_SO", name="SOIC-8")
    registry.attach("CMP-1", footprint)
    assert registry.has("CMP-1", "footprint")
    assert not registry.has("CMP-1", "simulatable")
    assert registry.get("CMP-1", "footprint") is footprint
    assert registry.get("CMP-1", "simulatable") is None
    assert len(registry) == 1
