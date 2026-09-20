"""Spec: The External Identifier Mapping Table; Imports Report What They Could
Not Represent; One Safe Round Trip."""

import pytest

from fang.elaborate import elaborate
from fang.entities import Component, Connection, Pin as PinEntity
from fang.graph import AddEntity, KernelGraph, SetParameter, Snapshot, Transaction
from fang.identity import Origin
from fang.importing import MappingTable
from fang.kicad import emit_netlist, read_netlist
from fang.lang import System, kOhm, uF, V
from fang.netlist import compile_netlist
from fang.parts import Capacitor, Resistor
from fang.sexpr import SExprError

PROJECT = "PRJ-IMPORT"


class Divider(System):
    top = Resistor(resistance=10 * kOhm, package="R_0603")
    bottom = Resistor(resistance=4.7 * kOhm, package="R_0603")
    cap = Capacitor(capacitance=100 * uF, package="C_0805")

    def architecture(self):
        self.top.p2 >> self.bottom.p1
        self.bottom.p1 >> self.cap.p1
        self.bottom.p2 >> self.cap.p2


@pytest.fixture
def emitted():
    result = elaborate(Divider, project_id=PROJECT)
    assert result.ok
    netlist = compile_netlist(result.snapshot, traits=result.traits)
    return result, netlist, emit_netlist(netlist, source="divider.py")


def components(entities):
    return {
        e.designator: e for e in entities.values() if isinstance(e, Component)
    }


# -- the mapping table -----------------------------------------------------


def test_an_external_identifier_maps_to_a_canonical_one(emitted):
    _, _, text = emitted
    result = read_netlist(text, project_id=PROJECT, source="divider.net")

    assert "R1" in result.mapping
    canonical = result.mapping.canonical("R1")
    assert canonical is not None
    assert canonical != "R1"
    entity = components(result.entities)["R1"]
    assert entity.id == canonical
    assert entity.identity.origin is Origin.IMPORTED
    assert entity.identity.external_id == "R1"


def test_re_importing_unchanged_sources_reuses_identifiers(emitted):
    _, _, text = emitted
    first = read_netlist(text, project_id=PROJECT, source="divider.net")
    second = read_netlist(text, project_id=PROJECT, source="divider.net")
    assert set(first.entities) == set(second.entities)


def test_an_identifier_the_exporter_wrote_is_recovered(emitted):
    result, _, text = emitted
    imported = read_netlist(text, project_id=PROJECT, source="divider.net")
    # Every imported component reuses the identifier elaboration gave it.
    for entity in components(imported.entities).values():
        assert entity.id in result.snapshot.entities


def test_an_identifier_is_minted_deterministically_when_the_file_carries_none():
    text = """
    (export "version" "E"
      (components
        (comp (ref "R1") (value "10k"))
        (comp (ref "R2") (value "4k7")))
      (nets
        (net "code" "1" "name" "Net-(R1-Pad2)"
          (node "ref" "R1" "pin" "2")
          (node "ref" "R2" "pin" "1"))))
    """
    first = read_netlist(text, project_id=PROJECT, source="plain.net")
    second = read_netlist(text, project_id=PROJECT, source="plain.net")
    assert set(first.entities) == set(second.entities)
    assert all(e.identity.origin is Origin.IMPORTED for e in first.entities.values())


def test_the_mapping_table_round_trips_both_ways():
    table = MappingTable()
    table.record("R1", "CMP-abc")
    assert table.canonical("R1") == "CMP-abc"
    assert table.external("CMP-abc") == "R1"
    assert MappingTable(table.as_dict()).canonical("R1") == "CMP-abc"


# -- loss reporting --------------------------------------------------------


def test_a_lossless_import_reports_no_loss(emitted):
    _, _, text = emitted
    result = read_netlist(text, project_id=PROJECT, source="divider.net")
    assert result.report.lossless
    assert result.report.unrepresented == []


def test_an_unsupported_construct_is_reported_and_the_rest_still_imports():
    text = """
    (export "version" "E"
      (components (comp (ref "R1") (value "10k") (weird_thing "x")))
      (nets)
      (some_unmodelled_block "data"))
    """
    result = read_netlist(text, project_id=PROJECT, source="odd.net")

    assert not result.report.lossless
    constructs = {item.construct for item in result.report.unrepresented}
    assert "some_unmodelled_block" in constructs
    assert "weird_thing" in constructs
    # The component it could recover is still there.
    assert "R1" in components(result.entities)
    assert all(d.severity.value == "warning" for d in result.report.diagnostics())


def test_missing_semantics_are_unknown_rather_than_invented():
    text = '(export "version" "E" (components (comp (ref "R1"))) (nets))'
    result = read_netlist(text, project_id=PROJECT, source="bare.net")
    resistor = components(result.entities)["R1"]
    assert resistor.part is None            # no value in the file, none invented
    assert resistor.package is None
    # A pin's electrical role is not recorded in a netlist, so it stays unknown.
    text_with_pins = """
    (export "version" "E"
      (components (comp (ref "R1")) (comp (ref "R2")))
      (nets (net "code" "1" "name" "N1"
        (node "ref" "R1" "pin" "1") (node "ref" "R2" "pin" "1"))))
    """
    with_pins = read_netlist(text_with_pins, project_id=PROJECT, source="pins.net")
    pins = [e for e in with_pins.entities.values() if isinstance(e, PinEntity)]
    assert pins and all(p.role == "unknown" for p in pins)


def test_a_node_naming_an_unknown_component_is_reported():
    text = """
    (export "version" "E"
      (components (comp (ref "R1")))
      (nets (net "code" "1" "name" "N1"
        (node "ref" "R1" "pin" "1") (node "ref" "R99" "pin" "1"))))
    """
    result = read_netlist(text, project_id=PROJECT, source="dangling.net")
    assert not result.report.lossless
    assert any("R99" in item.detail for item in result.report.unrepresented)


def test_a_file_that_is_not_a_netlist_is_refused():
    with pytest.raises(SExprError, match="not a netlist"):
        read_netlist('(kicad_pcb (version 20240101))', project_id=PROJECT)


# -- the round trip --------------------------------------------------------


def test_an_unchanged_import_re_emits_unchanged(emitted):
    _, original, text = emitted
    imported = read_netlist(text, project_id=PROJECT, source="divider.net")
    snapshot = Snapshot(PROJECT, "REV-IMPORT", imported.entities)
    recompiled = compile_netlist(snapshot)

    assert [(c.designator, c.value) for c in recompiled.components] == [
        (c.designator, c.value) for c in original.components
    ]
    assert [(n.name, [(x.designator, x.pin) for x in n.nodes]) for n in recompiled.nets] == [
        (n.name, [(x.designator, x.pin) for x in n.nodes]) for n in original.nets
    ]


def test_one_safe_edit_changes_only_what_it_names(emitted):
    """Import, change one value through the gate, re-emit."""
    _, original, text = emitted
    imported = read_netlist(text, project_id=PROJECT, source="divider.net")
    graph = KernelGraph(Snapshot(PROJECT, "REV-IMPORT", imported.entities))

    target = components(imported.entities)["R2"]
    edited = target.__class__(
        target.identity,
        designator=target.designator,
        part="22 kOhm",
        package=target.package,
        provenance=target.provenance,
        source_location=target.source_location,
        extensions=target.extensions,
    )
    from fang.graph import RemoveEntity

    proposal = graph.apply(
        Transaction(
            graph.head.hash,
            (
                RemoveEntity(target=target.id, reason="replace with edited value"),
                AddEntity(entity=edited, reason="set R2 to 22 kOhm"),
            ),
        )
    )
    assert proposal.accepted

    recompiled = compile_netlist(graph.head)
    before = {c.designator: c.value for c in original.components}
    after = {c.designator: c.value for c in recompiled.components}

    assert after["R2"] == "22 kOhm"
    assert {k: v for k, v in after.items() if k != "R2"} == {
        k: v for k, v in before.items() if k != "R2"
    }
    # Every net is untouched by a value change.
    assert [(n.name, [(x.designator, x.pin) for x in n.nodes]) for n in recompiled.nets] == [
        (n.name, [(x.designator, x.pin) for x in n.nodes]) for n in original.nets
    ]


def test_an_imported_project_is_usable_without_ever_seeing_fang():
    """A file authored entirely outside Fang still becomes a graph."""
    text = """
    (export "version" "E"
      (components
        (comp (ref "U1") (value "STM32G474") (footprint "Package_QFP:LQFP-64"))
        (comp (ref "C1") (value "100nF") (footprint "Capacitor_SMD:C_0402")))
      (nets
        (net "code" "1" "name" "+3V3"
          (node "ref" "U1" "pin" "1")
          (node "ref" "C1" "pin" "1"))
        (net "code" "2" "name" "GND"
          (node "ref" "U1" "pin" "8")
          (node "ref" "C1" "pin" "2"))))
    """
    result = read_netlist(text, project_id=PROJECT, source="foreign.net")
    assert result.report.lossless
    assert set(components(result.entities)) == {"U1", "C1"}

    snapshot = Snapshot(PROJECT, "REV-IMPORT", result.entities)
    netlist = compile_netlist(snapshot)
    assert len(netlist.nets) == 2
    assert {c.designator for c in netlist.components} == {"U1", "C1"}


# -- the round trip, closed ------------------------------------------------


def snapshot_line(text):
    import re

    return re.sub(r'\(snapshot "[^"]*"\)', '(snapshot "X")', text)


def test_re_emitting_an_import_reproduces_the_file(emitted):
    """The round trip closed: emit, import, emit, and compare the bytes.

    The earlier round-trip tests stopped at the compiled netlist and compared
    designators and net membership, which is why a footprint could be dropped
    on the way out without any test noticing.
    """
    _, _, first = emitted
    imported = read_netlist(first, project_id=PROJECT, source="divider.net")
    second = emit_netlist(
        compile_netlist(Snapshot(PROJECT, "REV-IMPORT", imported.entities)),
        source="divider.py",
    )
    # Only the snapshot hash may differ: it names the graph, not the design.
    assert snapshot_line(second) == snapshot_line(first)


def test_a_file_in_kicads_own_syntax_imports_with_its_connectivity():
    """KiCad writes a keyed value as a nested list, not as flat atoms.

    Fang's own exports once used the flat form, and the reader only understood
    that, so every net in a file exported from Eeschema was read as empty.
    """
    text = """
    (export (version "E")
      (components
        (comp (ref "R1") (value "10k") (footprint "R_0402")
          (libsource (lib "Device") (part "R")))
        (comp (ref "C1") (value "100nF") (footprint "C_0402")
          (libsource (lib "Device") (part "C"))))
      (nets
        (net (code "1") (name "VOUT")
          (node (ref "R1") (pin "2") (pintype "passive"))
          (node (ref "C1") (pin "1") (pintype "passive")))))
    """
    result = read_netlist(text, project_id=PROJECT, source="kicad.net")
    netlist = compile_netlist(Snapshot(PROJECT, "REV-KICAD", result.entities))

    assert {c.designator for c in netlist.components} == {"R1", "C1"}
    # The connectivity, which is the thing a netlist is for.
    vout = next(n for n in netlist.nets if n.name == "VOUT")
    assert {(n.designator, n.pin) for n in vout.nodes} == {("R1", "2"), ("C1", "1")}
    # And what cannot be recovered from a program: footprint and symbol.
    assert {c.designator: c.footprint for c in netlist.components} == {
        "R1": "R_0402",
        "C1": "C_0402",
    }
    assert {c.designator: c.libsource for c in netlist.components} == {
        "R1": "Device:R",
        "C1": "Device:C",
    }


def test_a_file_in_the_older_flat_syntax_still_imports():
    """Files Fang itself wrote before it spoke KiCad's syntax still read."""
    text = """
    (export "version" "E"
      (components
        (comp (ref "R1") (value "10k"))
        (comp (ref "C1") (value "100nF")))
      (nets (net "code" "1" "name" "VOUT"
        (node "ref" "R1" "pin" "2")
        (node "ref" "C1" "pin" "1"))))
    """
    result = read_netlist(text, project_id=PROJECT, source="legacy.net")
    netlist = compile_netlist(Snapshot(PROJECT, "REV-LEGACY", result.entities))
    assert [n.name for n in netlist.nets] == ["VOUT"]


def test_a_designator_that_is_not_a_path_segment_still_imports():
    """KiCad allows a hyphen in a reference; a semantic path segment does not.

    The reference is transliterated the way pin and net names already were, so
    a real board does not fail to import over a character in a designator.
    """
    text = """
    (export (version "E")
      (components
        (comp (ref "TA-101") (value "74LS00"))
        (comp (ref "C1") (value "100nF")))
      (nets
        (net (code "1") (name "GND")
          (node (ref "TA-101") (pin "7"))
          (node (ref "C1") (pin "2")))))
    """
    result = read_netlist(text, project_id=PROJECT, source="hyphen.net")
    netlist = compile_netlist(Snapshot(PROJECT, "REV-HYPHEN", result.entities))

    # The designator is untouched; only the path derived from it is normalized.
    assert {c.designator for c in netlist.components} == {"TA-101", "C1"}
    gnd = next(n for n in netlist.nets if n.name == "GND")
    assert {(n.designator, n.pin) for n in gnd.nodes} == {("TA-101", "7"), ("C1", "2")}
