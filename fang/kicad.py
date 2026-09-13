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
        """Atoms before the first nested list share the head's line; every child
        from the first nested list on takes a line of its own, in order, so that
        `(field (name "MPN") "RC0603")` keeps its name before its value."""
        pad = " " * (indent * width)
        inner = " " * ((indent + 1) * width)

        head = f"{pad}({self.name}"
        lines: list[str] = []
        for child in self.children:
            if isinstance(child, SExpr):
                lines.append(child.render(indent + 1, width))
            elif lines:
                lines.append(f"{inner}{_atom(child)}")
            else:
                head += " " + _atom(child)
        if not lines:
            return head + ")"
        body = "\n".join(lines)
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
    """Render a netlist in the form KiCad writes.

    Every field is a list of its own, `(name "GND")`, as `kicad-cli sch export
    netlist` writes it. The design block names the snapshot the netlist was
    compiled from, so a file on disk can always be traced back to the graph
    state that produced it.
    """
    export = SExpr("export", SExpr("version", NETLIST_VERSION))

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
            fields.add(SExpr("field", SExpr("name", "Manufacturer"), component.manufacturer))
        if component.mpn:
            fields.add(SExpr("field", SExpr("name", "MPN"), component.mpn))
        if fields.children:
            node.add(fields)
        # The entity id is what makes the round trip identity-preserving.
        node.add(
            SExpr(
                "property",
                SExpr("name", FANG_ID_PROPERTY),
                SExpr("value", component.entity_id),
            )
        )
        components.add(node)
    export.add(components)

    nets = SExpr("nets")
    for net in netlist.nets:
        node = SExpr("net", SExpr("code", str(net.code)), SExpr("name", net.name))
        for member in net.nodes:
            node.add(SExpr("node", SExpr("ref", member.designator), SExpr("pin", member.pin)))
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
_KNOWN_EXPORT_BLOCKS = frozenset({"version", "design", "components", "nets"})

#: What the reader models inside each container block. A child outside these is
#: named in the report, because accepting a block and discarding its contents is
#: exactly the silent semantic loss the standard forbids. The design block
#: describes the file rather than the design, and the file is already every
#: imported entity's source location.
_KNOWN_CHILDREN: Mapping[str, frozenset[str]] = {
    "design": frozenset({"source", "date", "tool", "sheet", "snapshot", "project"}),
    "components": frozenset({"comp"}),
    "nets": frozenset({"net"}),
}

#: What the reader stores from a component, a net, and a node. Known means
#: stored: anything else a list carries is reported, including the fields,
#: datasheet, net class, pin function, and pin type a KiCad export writes. A
#: `property` is stored only when it carries the identifier an earlier export
#: wrote, `FANG_ID_PROPERTY`; any other property is reported by name.
_KNOWN_COMP_BLOCKS = frozenset({"ref", "value", "footprint"})
_KNOWN_NET_BLOCKS = frozenset({"code", "name", "node"})
_KNOWN_NODE_BLOCKS = frozenset({"ref", "pin"})

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

    Reads the form KiCad writes, in which every field is a list of its own, and
    the flat form earlier Fang releases wrote. Raises on a malformed file. A
    well-formed file with constructs this adapter does not store still imports,
    and the report names each one.
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

    version = root.pairs().get("version")
    if version is not None and version != NETLIST_VERSION:
        report.note(
            "version",
            source,
            f"netlist version {version!r}; this reader implements {NETLIST_VERSION!r}",
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

        where = f"{source}:{reference}"
        for child in comp.items[1:]:
            if not isinstance(child, Node) or child.head in _KNOWN_COMP_BLOCKS:
                continue
            if child.head == "property":
                name = _named(child)
                if name != FANG_ID_PROPERTY:
                    report.note("property", where, f"property {name!r} is not stored")
            elif child.head == "fields":
                for field_node in child.items[1:]:
                    if not isinstance(field_node, Node):
                        continue
                    if field_node.head == "field":
                        report.note("field", where, f"field {_named(field_node)!r} is not stored")
                    else:
                        report.note(
                            field_node.head, where, "this construct inside fields is not modelled"
                        )
            else:
                report.note(child.head, where, "component block is not modelled")

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
        where = f"{source}:{name}"
        members: list[str] = []

        for child in net.items[1:]:
            if not isinstance(child, Node) or child.head in _KNOWN_NET_BLOCKS:
                continue
            if child.head == "class":
                report.note("class", where, f"net class {fields.get('class')!r} is not stored")
            else:
                report.note(child.head, where, "net block is not modelled")

        for node in net.children("node"):
            node_fields = node.pairs()
            reference, pin_name = node_fields.get("ref"), node_fields.get("pin")
            if not reference or not pin_name:
                report.note("node", where, "a node without ref and pin")
                continue
            for child in node.items[1:]:
                if isinstance(child, Node) and child.head not in _KNOWN_NODE_BLOCKS:
                    report.note(
                        child.head, where, f"{reference}.{pin_name} {child.head} is not stored"
                    )
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
    """An identifier an earlier export wrote is reused rather than re-minted.

    KiCad's form is `(property (name "fang_id") (value "CMP-..."))`; earlier Fang
    releases wrote `(property "name" "fang_id" "CMP-...")`. Both are read.
    """
    for prop in comp.children("property"):
        if _named(prop) != FANG_ID_PROPERTY:
            continue
        nested = prop.value("value")
        if nested:
            return nested
        atoms = prop.atoms()
        if len(atoms) >= 3:
            return atoms[2]
    return None


def _named(node: Node) -> str | None:
    """The name a property or a field carries, in either form."""
    nested = node.value("name")
    if nested is not None:
        return nested
    atoms = node.atoms()
    if len(atoms) >= 2 and atoms[0] == "name":
        return atoms[1]
    return None


def _prefix_of_reference(reference: str) -> str:
    prefix = "".join(char for char in reference if not char.isdigit())
    return prefix or "U"


def _path_safe(name: str) -> str:
    from .identity import transliterate

    return transliterate(name)
