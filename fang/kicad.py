"""KiCad interchange: the s-expression writer and the netlist emitter.

Spec: "External Adapters Report Loss" and "The Netlist Is A Projection".

The writer is deterministic: the same netlist emits byte-identical output, which
is what makes a generated file diffable and a round trip reviewable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from . import __version__
from .diagnostics import SourceLocation
from .entities import Component, Connection, ConnectionKind, Entity, Net, Pin
from .identity import derive
from .importing import ImportReport, ImportResult, MappingTable, canonical_id_for
from .netlist import Netlist
from .provenance import Actor, ActorKind, Provenance, ProvenanceOrigin, ProvenanceRecord
from .sexpr import Node, SExprError, parse
from .units import Quantity
from .values import Value

#: The KiCad netlist format version this emitter writes.
NETLIST_VERSION = "E"


class SExpr:
    """One s-expression node: a name and its children."""

    __slots__ = ("name", "children")

    def __init__(self, name: str, *children: Any) -> None:
        self.name = name
        self.children = list(children)

    def add(self, *children: Any) -> "SExpr":
        self.children.extend(children)
        return self

    def render(self, indent: int = 0, width: int = 2) -> str:
        pad = " " * (indent * width)
        parts = [_atom(child) for child in self.children if not isinstance(child, SExpr)]
        nested = [child for child in self.children if isinstance(child, SExpr)]

        head = f"{pad}({self.name}"
        if parts:
            head += " " + " ".join(parts)
        if not nested:
            return head + ")"
        body = "\n".join(child.render(indent + 1, width) for child in nested)
        return f"{head}\n{body}\n{pad})"

    def __str__(self) -> str:
        return self.render()


def _atom(value: Any) -> str:
    if isinstance(value, str):
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def emit_netlist(netlist: Netlist, *, source: str = "fang") -> str:
    """Render a netlist in KiCad's format.

    The design block names the snapshot the netlist was compiled from, so a file
    on disk can always be traced back to the graph state that produced it.
    """
    export = SExpr("export", "version", NETLIST_VERSION)

    export.add(
        SExpr(
            "design",
            SExpr("source", source),
            SExpr("tool", f"fang {__version__}"),
            SExpr("snapshot", netlist.snapshot),
            SExpr("project", netlist.project_id),
        )
    )

    components = SExpr("components")
    for component in netlist.components:
        node = SExpr("comp", SExpr("ref", component.designator))
        node.add(SExpr("value", component.value))
        if component.footprint:
            node.add(SExpr("footprint", component.footprint))
        fields = SExpr("fields")
        if component.manufacturer:
            fields.add(SExpr("field", "name", "Manufacturer").add(component.manufacturer))
        if component.mpn:
            fields.add(SExpr("field", "name", "MPN").add(component.mpn))
        if fields.children:
            node.add(fields)
        # The entity id is what makes the round trip identity-preserving.
        node.add(SExpr("property", "name", "fang_id").add(component.entity_id))
        components.add(node)
    export.add(components)

    nets = SExpr("nets")
    for net in netlist.nets:
        node = SExpr("net", "code", str(net.code), "name", net.name)
        for member in net.nodes:
            node.add(SExpr("node", "ref", member.designator, "pin", member.pin))
        nets.add(node)
    export.add(nets)

    return export.render() + "\n"


def write_netlist(netlist: Netlist, path, *, source: str = "fang") -> bytes:
    """Write a netlist to disk, returning exactly the bytes written."""
    data = emit_netlist(netlist, source=source).encode("utf-8")
    with open(path, "wb") as handle:
        handle.write(data)
    return data


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

#: Blocks the netlist reader understands. Anything else in the file is reported
#: rather than dropped, so a lossy import is visible instead of silent.
#:
#: `libparts` and `libraries` are absent deliberately: the reader recovers
#: nothing from them, so naming only some nested key would imply the rest was
#: modelled. The whole block is reported instead, which is what is true.
_KNOWN_EXPORT_BLOCKS = frozenset({"design", "components", "nets"})

#: What the reader models inside each container block. A child outside these is
#: named in the report, because accepting a block and discarding its contents is
#: exactly the silent semantic loss the standard forbids.
_KNOWN_CHILDREN: Mapping[str, frozenset[str]] = {
    "libparts": frozenset({"libpart"}),
    "libraries": frozenset({"library"}),
    "design": frozenset({"source", "date", "tool", "sheet", "snapshot", "project"}),
}
_KNOWN_COMP_BLOCKS = frozenset({"ref", "value", "footprint", "fields", "property", "datasheet"})

#: The property name an export writes the canonical identifier under.
FANG_ID_PROPERTY = "fang_id"


def read_netlist(
    text: str,
    *,
    project_id: str,
    source: str = "<netlist>",
    mapping: MappingTable | None = None,
    built_at: datetime | None = None,
    revision_id: str = "REV-IMPORT",
) -> ImportResult:
    """Read a KiCad netlist into kernel entities.

    Raises on a malformed file. A well-formed file with constructs this adapter
    does not model still imports, and the report names each one.
    """
    root = parse(text)
    if root.head != "export":
        raise SExprError(f"{source} is not a netlist: its top level is {root.head!r}")

    table = mapping or MappingTable()
    report = ImportReport(source)
    entities: dict[str, Entity] = {}
    moment = built_at or datetime.now(timezone.utc)

    def provenance(location: str) -> Provenance:
        return Provenance().append(
            ProvenanceRecord(
                ProvenanceOrigin.IMPORTED,
                "kicad_netlist_import",
                Actor(ActorKind.ADAPTER, "fang-kicad"),
                revision_id,
                moment,
                source_location=SourceLocation(source, 0),
            )
        )

    for block in root.items[1:]:
        if not isinstance(block, Node):
            continue
        if block.head not in _KNOWN_EXPORT_BLOCKS:
            report.note(block.head, source, "top-level block is not modelled")
            continue
        modelled = _KNOWN_CHILDREN.get(block.head)
        if modelled is None:
            continue
        for child in block.items[1:]:
            if isinstance(child, Node) and child.head not in modelled:
                report.note(
                    child.head,
                    f"{source}:{block.head}",
                    "this construct inside a recognized block is not modelled",
                )

    pins_by_reference: dict[tuple[str, str], str] = {}

    components_block = root.child("components")
    for comp in components_block.children("comp") if components_block else []:
        reference = comp.value("ref")
        if not reference:
            report.note("comp", source, "a component with no reference was skipped")
            continue

        recovered = _recover_fang_id(comp)
        identity = canonical_id_for(
            reference,
            "component",
            f"imported.{reference.lower()}",
            project_id=project_id,
            mapping=table,
            recovered=recovered,
            taken=set(entities),
        )

        for child in comp.items[1:]:
            if isinstance(child, Node) and child.head not in _KNOWN_COMP_BLOCKS:
                report.note(child.head, f"{source}:{reference}", "component block is not modelled")

        entities[identity.id] = Component(
            identity,
            designator=reference,
            part=comp.value("value"),
            package=comp.value("footprint"),
            provenance=provenance(reference),
            source_location=SourceLocation(source, 0),
            extensions={"designator_prefix": _prefix_of_reference(reference)},
        )
        report.recovered += 1

    nets_block = root.child("nets")
    for net in nets_block.children("net") if nets_block else []:
        fields = net.pairs()
        name = fields.get("name") or f"net-{fields.get('code', '0')}"
        members: list[str] = []

        for node in net.children("node"):
            node_fields = node.pairs()
            reference, pin_name = node_fields.get("ref"), node_fields.get("pin")
            if not reference or not pin_name:
                report.note("node", f"{source}:{name}", "a node without ref and pin")
                continue
            owner = table.canonical(reference)
            if owner is None:
                report.note("node", f"{source}:{name}", f"{reference} is not a known component")
                continue
            key = (reference, pin_name)
            if key not in pins_by_reference:
                pin_identity = canonical_id_for(
                    f"{reference}.{pin_name}",
                    "pin",
                    f"imported.{reference.lower()}.{_path_safe(pin_name)}",
                    project_id=project_id,
                    mapping=table,
                    taken=set(entities),
                )
                entities[pin_identity.id] = Pin(
                    pin_identity,
                    owner=owner,
                    vendor_name=pin_name,
                    role="unknown",     # the file records no role; unknown, not invented
                    number=pin_name,
                    provenance=provenance(f"{reference}.{pin_name}"),
                    source_location=SourceLocation(source, 0),
                )
                pins_by_reference[key] = pin_identity.id
                report.recovered += 1
            members.append(pins_by_reference[key])

        # The file names this net, so the net is the entity and its membership is
        # its own definition. No synthetic connection chain is invented beside
        # it: that would be a second representation of the same connectivity.
        if not members:
            continue
        net_identity = canonical_id_for(
            name,
            "net",
            f"imported.net.{_path_safe(name)}",
            project_id=project_id,
            mapping=table,
            taken=set(entities),
        )
        entities[net_identity.id] = Net(
            net_identity,
            aliases=(name,),
            members=tuple(members),
            provenance=provenance(name),
            source_location=SourceLocation(source, 0),
        )
        report.recovered += 1

    return ImportResult(entities, table, report)


def _recover_fang_id(comp: Node) -> str | None:
    """An identifier an earlier export wrote is reused rather than re-minted."""
    for prop in comp.children("property"):
        atoms = prop.atoms()
        if len(atoms) >= 3 and atoms[0] == "name" and atoms[1] == FANG_ID_PROPERTY:
            return atoms[2]
    return None


def _prefix_of_reference(reference: str) -> str:
    prefix = "".join(char for char in reference if not char.isdigit())
    return prefix or "U"


def _path_safe(name: str) -> str:
    from .identity import transliterate

    return transliterate(name)
