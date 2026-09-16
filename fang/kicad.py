"""KiCad interchange: what the kernel writes out, and what it reads back.

Spec: "External Adapters Report Loss", "The Netlist Is A Projection", "Emitted
Design Rules Are Projections", and "Board Import Reports What It Could Not
Represent".

Four artifacts cross this boundary: the netlist and the design rules go out, and
a netlist and a board come back. Every one of them is a projection in one
direction or an import in the other, and none of them is a place an engineering
fact can be recorded — an edit made to an emitted file is reported as a
difference from the registry rather than adopted from it.

Both writers are deterministic: one snapshot emits byte-identical output, which
is what makes a generated file diffable and a round trip reviewable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from . import __version__
from .constraints import (
    PHYSICAL_PREFIX,
    Comparison,
    Enforcement,
    Literal,
    Logical,
    Projection,
    Ref,
)
from .diagnostics import (
    TOPO_BOARD_DISAGREES,
    TOPO_RULES_DIFFER,
    Diagnostic,
    Severity,
    SourceLocation,
)
from .entities import Component, Connection, ConnectionKind, Entity, Net, Pin
from .identity import derive
from .importing import (
    ImportReport,
    ImportResult,
    MappingTable,
    Unrepresented,
    canonical_id_for,
)
from .netlist import Netlist
from .physical import (
    Board,
    Layer,
    Pad,
    Placement,
    Point,
    Stackup,
    Trace,
    Via,
    Zone,
)
from .provenance import Actor, ActorKind, Provenance, ProvenanceOrigin, ProvenanceRecord
from .serialization import canonical_bytes
from .sexpr import Node, SExprError, parse, parse_many
from .units import Quantity, _ctx, _decimal_str
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


# --------------------------------------------------------------------------
# Design rules and net classes
# --------------------------------------------------------------------------

#: The design-rule file format version this emitter writes.
DRU_VERSION = "1"

#: The comment character a `.kicad_dru` uses, alongside the one every other
#: s-expression dialect here agrees on.
DRU_COMMENTS = ";#"

#: The KiCad rule constraint that means the same thing as each physical
#: attribute. An attribute absent here has no KiCad constraint that means the
#: same thing, and is reported rather than bent onto one that means something
#: else — a board thickness is not an annular width.
DRU_CONSTRAINT_OF: Mapping[str, str] = {
    "trace_width": "track_width",
    "trace_length": "length",
    "clearance": "clearance",
    "via_diameter": "via_diameter",
    "via_drill": "hole_size",
}

#: How an enforcement level reports in the layout tool. Advisory intent is
#: carried across and silenced there rather than dropped on the way out, so the
#: file still says the rule exists.
_DRU_SEVERITY: Mapping[Enforcement, str] = {
    Enforcement.HARD: "error",
    Enforcement.SOFT: "warning",
    Enforcement.ADVISORY: "ignore",
}

#: The unit a `.kicad_dru` magnitude is written in.
_DRU_UNIT = "mm"


class Raw:
    """An atom emitted verbatim.

    `_atom` quotes every string, which is right for a name and wrong for a bare
    token: `track_width` and `0.5mm` are symbols in a rule file, not strings.
    """

    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        self.text = text

    def __str__(self) -> str:
        return self.text


@dataclass(frozen=True)
class DesignRules:
    """A rendered rule file, and what could not be projected into it.

    An export is an adapter like an import, and it reports loss the same way:
    a constraint KiCad has no rule for is named here rather than dropped.
    """

    text: str
    projected: tuple[str, ...] = ()
    unrepresented: tuple[Unrepresented, ...] = ()

    @property
    def lossless(self) -> bool:
        return not self.unrepresented

    def diagnostics(self) -> list[Diagnostic]:
        return [item.as_diagnostic() for item in self.unrepresented]


def _magnitude(quantity: Quantity, bound: str) -> tuple[str, bool]:
    """One end of a literal, in the rule file's unit.

    A bound reads off the end of the interval the evaluator would have used: a
    minimum holds only at the literal's top and a maximum only at its bottom,
    which is exactly what `Comparison` decides. For the ordinary scalar literal
    the two ends are the same number and the distinction never shows.
    """
    low, high = quantity.interval()
    base = Quantity.scalar(high if bound == "min" else low, "m")
    converted, exact = base.converted_to(_DRU_UNIT)
    return f"{_decimal_str(converted.value)}{_DRU_UNIT}", exact


def _comparisons(expression) -> list[Comparison] | None:
    """The comparisons a rule states, or None if its shape does not project.

    A conjunction of comparisons is a rule with several bounds. Anything else —
    a disjunction, a negation, arithmetic over two references — says something
    a `.kicad_dru` rule cannot say, and is reported rather than approximated.
    """
    if isinstance(expression, Comparison):
        return [expression]
    if isinstance(expression, Logical) and expression.op == "and":
        found: list[Comparison] = []
        for argument in expression.args:
            nested = _comparisons(argument)
            if nested is None:
                return None
            found.extend(nested)
        return found
    return None


#: Which bound a comparison states, by operator and by which side the reference
#: is on. `gt`, `lt`, and `ne` are deliberately absent: a `.kicad_dru` bound is
#: inclusive, so an exclusive one would have to be approximated to be written.
_BOUNDS: Mapping[tuple[str, bool], tuple[str, ...]] = {
    ("ge", True): ("min",), ("le", True): ("max",), ("eq", True): ("min", "max"),
    ("le", False): ("min",), ("ge", False): ("max",), ("eq", False): ("min", "max"),
}


def _bounds(comparison: Comparison) -> list[tuple[str, str, Quantity]] | None:
    """`(attribute, bound, literal)` for one comparison, or None if it does not
    project."""
    left, right = comparison.args
    if isinstance(left, Ref) and isinstance(right, Literal):
        reference, literal, reference_first = left, right, True
    elif isinstance(right, Ref) and isinstance(left, Literal):
        reference, literal, reference_first = right, left, False
    else:
        return None
    if literal.quantity is None:
        return None
    if not reference.attr.startswith(PHYSICAL_PREFIX):
        return None
    attribute = reference.attr[len(PHYSICAL_PREFIX):]
    if attribute not in DRU_CONSTRAINT_OF:
        return None
    bounds = _BOUNDS.get((comparison.op, reference_first))
    if bounds is None:
        return None
    return [(attribute, bound, literal.quantity) for bound in bounds]


def _condition(projection: Projection) -> str | None:
    """The nets a rule applies to, named by their classes.

    A rule with no class applies to the whole board, which is what a constraint
    targeting something that is not a net means.
    """
    names = projection.class_specific.get("net_classes")
    if not names:
        return None
    return " || ".join(f"A.NetClass == '{name}'" for name in names)


def _rule(projection: Projection) -> tuple[SExpr | None, list[Unrepresented]]:
    constraint = projection.constraint
    where = f"{constraint.constraint_kind} {constraint.id}"

    comparisons = _comparisons(constraint.expression)
    if comparisons is None:
        return None, [
            Unrepresented(
                "constraint expression", where,
                "a design rule states inclusive bounds on one attribute",
            )
        ]

    node = SExpr("rule", constraint.id)
    node.add(SExpr("severity", Raw(_DRU_SEVERITY[constraint.enforcement])))
    lost: list[Unrepresented] = []
    written = 0
    for comparison in comparisons:
        bounds = _bounds(comparison)
        if bounds is None:
            lost.append(
                Unrepresented(
                    "constraint expression", where,
                    f"{comparison.op} on this attribute has no rule that means the same",
                )
            )
            continue
        for attribute, bound, quantity in bounds:
            magnitude, exact = _magnitude(quantity, bound)
            if not exact:
                lost.append(
                    Unrepresented(
                        "magnitude", where,
                        f"{quantity} was rounded to {magnitude}",
                    )
                )
            node.add(
                SExpr(
                    "constraint",
                    Raw(DRU_CONSTRAINT_OF[attribute]),
                    SExpr(bound, Raw(magnitude)),
                )
            )
            written += 1

    if not written:
        return None, lost

    condition = _condition(projection)
    if condition is not None:
        node.add(SExpr("condition", condition))
    return node, lost


def emit_design_rules(
    projections: Sequence[Projection], *, source: str = "fang", snapshot: str = ""
) -> DesignRules:
    """Render layout constraints as a KiCad design-rule file.

    The file is a projection and says so in its own header. Rules come out in
    the order the projections arrive, which `routing.rule_projections` has
    already sorted by constraint identifier, so one snapshot emits one file.
    """
    lines = [
        f"# Generated by fang {__version__} from {source}.",
        f"# Snapshot {snapshot or 'uncommitted'}.",
        "#",
        "# Every rule below projects a constraint in the kernel's one registry and",
        "# is named by the identifier of the record it projects. Editing this file",
        "# does not change the design: the registry governs, and an edit here is",
        "# reported as a difference from it.",
        "",
        f"(version {DRU_VERSION})",
    ]

    projected: list[str] = []
    lost: list[Unrepresented] = []
    for projection in projections:
        node, notes = _rule(projection)
        lost.extend(notes)
        if node is None:
            continue
        lines.extend(["", node.render()])
        projected.append(projection.constraint.id)

    return DesignRules("\n".join(lines) + "\n", tuple(projected), tuple(lost))


def write_design_rules(
    projections: Sequence[Projection], path, *, source: str = "fang", snapshot: str = ""
) -> DesignRules:
    """Write a design-rule file, returning what was written and what was lost."""
    rules = emit_design_rules(projections, source=source, snapshot=snapshot)
    with open(path, "wb") as handle:
        handle.write(rules.text.encode("utf-8"))
    return rules


def emit_net_classes(
    classes: Sequence, *, project_id: str = "", snapshot: str = ""
) -> str:
    """Render net class assignments as canonical JSON.

    Each class names the constraints it was grouped from, so the assignment
    points back into the registry rather than standing on its own. A net appears
    in exactly one class, because the grouping is the set of rules that apply to
    it and a set is a set.
    """
    document = {
        "tool": f"fang {__version__}",
        "project": project_id,
        "snapshot": snapshot,
        "net_classes": [entry.as_dict() for entry in classes],
    }
    return canonical_bytes(document).decode("utf-8")


def compare_design_rules(
    text: str, projections: Sequence[Projection], *, source: str = "<rules>"
) -> list[Diagnostic]:
    """Report where a rule file on disk differs from the registry it projects.

    The comparison is against a fresh emission, so it covers every way the file
    can have drifted: a rule edited, a rule deleted, and a rule someone added by
    hand. Nothing here adopts what it finds — the return value is the report,
    and the registry is not written to.
    """
    expected = _rules_by_name(
        emit_design_rules(projections, source=source).text, source=source
    )
    found = _rules_by_name(text, source=source)

    findings = []
    for name in sorted(set(expected) | set(found)):
        if name not in found:
            detail = "the registry holds this rule and the file does not"
        elif name not in expected:
            detail = "the file holds a rule the registry does not project"
        elif expected[name] != found[name]:
            detail = "the file states this rule differently from the registry"
        else:
            continue
        findings.append(
            Diagnostic(
                TOPO_RULES_DIFFER,
                Severity.WARNING,
                f"{name}: {detail}",
                location=SourceLocation(source, 0),
            )
        )
    return findings


def _rules_by_name(text: str, *, source: str) -> dict[str, str]:
    """Every `(rule ...)` form in a design-rule file, rendered canonically.

    Re-rendering both sides is what makes the comparison about the rules rather
    than about whitespace: a reformatted file is not an edited one.
    """
    rules: dict[str, str] = {}
    for index, form in enumerate(parse_many(text, comments=DRU_COMMENTS)):
        if form.head != "rule":
            continue
        atoms = form.atoms()
        name = atoms[0] if atoms else f"<unnamed rule {index}>"
        rules[name] = _render(form)
    return rules


def _render(node: Node) -> str:
    """One parsed form, rendered back to a canonical string."""
    parts = []
    for item in node.items:
        parts.append(_render(item) if isinstance(item, Node) else _atom(item.value))
    return "(" + " ".join(parts) + ")"


# --------------------------------------------------------------------------
# Reading a board
# --------------------------------------------------------------------------

#: Top-level board blocks the reader models, or recognizes and deliberately
#: records nothing from. `setup` is in the second group and that is the point:
#: it holds the layout tool's own rule defaults, which are not engineering facts
#: the kernel owns, so they are reported rather than adopted.
_KNOWN_BOARD_BLOCKS = frozenset(
    {
        "version", "generator", "generator_version", "paper", "title_block",
        "general", "layers", "setup", "net", "footprint", "segment", "via",
        "zone", "gr_line",
    }
)

#: What the reader turns into entities. The rest of `_KNOWN_BOARD_BLOCKS` is
#: recognized structure it takes nothing from.
_MODELLED_BOARD_BLOCKS = frozenset(
    {"general", "layers", "net", "footprint", "segment", "via", "zone", "gr_line"}
)

#: The layer a board's outline is drawn on.
EDGE_LAYER = "Edge.Cuts"

#: A `.kicad_pcb` is written in millimetres.
_BOARD_UNIT = "mm"


def _mm(value: str | None) -> Quantity | None:
    return None if value is None else Quantity.scalar(value, _BOARD_UNIT)


def _point(node: Node | None, head: str) -> Point | None:
    child = node.child(head) if node is not None else None
    if child is None:
        return None
    atoms = child.atoms()
    if len(atoms) < 2:
        return None
    return Point.of(atoms[0], atoms[1])


def _segment_length(start, end) -> Quantity:
    """The length of a segment already drawn.

    Measuring geometry a file fixed is not computing one: the kernel still
    places nothing and routes nothing. Without it a length rule could only ever
    be undecided about copper that is sitting right there.
    """
    with _ctx():
        dx, dy = end.x - start.x, end.y - start.y
        return Quantity.scalar((dx * dx + dy * dy).sqrt(), _BOARD_UNIT)


def mapping_from_netlist(netlist: Netlist) -> MappingTable:
    """A mapping table binding a board's external names to what already exists.

    A board file names parts and pads the way the netlist does — by designator
    and pad number — so the entities they realize are already in the graph. This
    hands the reader those bindings, which is what keeps a placement pointing at
    its component instead of at nothing.
    """
    table = MappingTable()
    for component in netlist.components:
        table.record(component.designator, component.entity_id)
    for net in netlist.nets:
        for node in net.nodes:
            table.record(f"{node.designator}.{node.pin}", node.pin_id)
    return table


def read_board(
    text: str,
    *,
    project_id: str,
    source: str = "<board>",
    mapping: MappingTable | None = None,
    built_at: datetime | None = None,
    revision_id: str = "REV-IMPORT",
    realizes: Mapping[str, str] | None = None,
) -> ImportResult:
    """Read a KiCad board into physical entities.

    `realizes` binds an external net name to the semantic entity already in the
    graph that its copper realizes. A net named there gets no `Net` entity of
    its own: the design already holds that fact, and minting a second one would
    be a second representation of the same connectivity.

    Raises on a malformed file. A well-formed file carrying constructs this
    adapter does not model still imports, and the report names each one with
    where it was found.
    """
    root = parse(text)
    if root.head != "kicad_pcb":
        raise SExprError(f"{source} is not a board: its top level is {root.head!r}")

    table = mapping or MappingTable()
    report = ImportReport(source)
    bindings = dict(realizes or {})
    entities: dict[str, Entity] = {}
    moment = built_at or datetime.now(timezone.utc)

    def provenance() -> Provenance:
        return Provenance().append(
            ProvenanceRecord(
                ProvenanceOrigin.IMPORTED,
                "kicad_board_import",
                Actor(ActorKind.ADAPTER, "fang-kicad"),
                revision_id,
                moment,
                source_location=SourceLocation(source, 0),
            )
        )

    def identity_for(external: str, kind: str, path: str):
        return canonical_id_for(
            external,
            kind,
            path,
            project_id=project_id,
            mapping=table,
            taken=set(entities),
        )

    def record(entity: Entity) -> None:
        entities[entity.id] = entity
        report.recovered += 1

    # -- what the adapter could not represent ------------------------------
    for block in root.items[1:]:
        if isinstance(block, Node) and block.head not in _KNOWN_BOARD_BLOCKS:
            report.note(block.head, source, "board construct is not modelled")

    # -- the stackup -------------------------------------------------------
    layer_ids: list[str] = []
    layers_block = root.child("layers")
    for entry in layers_block.items[1:] if layers_block else []:
        if not isinstance(entry, Node):
            continue
        # A layer entry is `(<ordinal> "<name>" <function>)`; the ordinal is
        # the tool's own numbering and the stackup's order is the file's order,
        # so it is read past rather than stored.
        atoms = [entry.head] + entry.atoms()
        if len(atoms) < 3:
            report.note("layer", f"{source}:layers", "a layer without a name and a function")
            continue
        name, function = atoms[1], atoms[2]
        identity = identity_for(f"layer:{name}", "layer", f"imported.layer.{_path_safe(name)}")
        record(
            Layer(
                identity,
                layer_name=name,
                function=function,
                provenance=provenance(),
                source_location=SourceLocation(source, 0),
            )
        )
        layer_ids.append(identity.id)

    stackup_id = None
    if layer_ids:
        identity = identity_for("stackup", "stackup", "imported.board.stackup")
        record(
            Stackup(
                identity,
                layers=tuple(layer_ids),   # file order is the stackup order
                provenance=provenance(),
                source_location=SourceLocation(source, 0),
            )
        )
        stackup_id = identity.id

    layer_by_name = {
        entity.layer_name: entity.id
        for entity in entities.values()
        if isinstance(entity, Layer)
    }

    def layer_of(node: Node, head: str = "layer") -> str | None:
        name = node.value(head)
        return layer_by_name.get(name) if name else None

    # -- the board ---------------------------------------------------------
    general = root.child("general")
    outline = []
    for line in root.children("gr_line"):
        if line.value("layer") != EDGE_LAYER:
            report.note("gr_line", f"{source}:{line.value('layer')}", "graphics off the board edge")
            continue
        start = _point(line, "start")
        if start is not None:
            # File order, not a computed ordering: the kernel reads the shape
            # the board states rather than working one out.
            outline.append(start)

    board_identity = identity_for("board", "board", "imported.board")
    record(
        Board(
            board_identity,
            stackup=stackup_id,
            outline=tuple(outline),
            thickness=_mm(general.value("thickness") if general else None),
            unit=_BOARD_UNIT,
            provenance=provenance(),
            source_location=SourceLocation(source, 0),
        )
    )

    # -- the nets ----------------------------------------------------------
    net_names: dict[str, str] = {}
    owner_of_net: dict[str, str] = {}
    for net in root.children("net"):
        atoms = net.atoms()
        if len(atoms) < 2 or atoms[0] == "0":
            continue          # net 0 is the unconnected pseudo-net
        code, name = atoms[0], atoms[1]
        net_names[code] = name
        bound = bindings.get(name)
        if bound is not None:
            owner_of_net[code] = bound
            table.record(name, bound)
            continue
        identity = identity_for(name, "net", f"imported.net.{_path_safe(name)}")
        record(
            Net(
                identity,
                aliases=(name,),
                provenance=provenance(),
                source_location=SourceLocation(source, 0),
            )
        )
        owner_of_net[code] = identity.id

    def net_of(node: Node) -> str | None:
        code = node.value("net")
        return owner_of_net.get(code) if code else None

    # -- placements and their pads -----------------------------------------
    pads_by_reference: dict[tuple[str, str], str] = {}
    for index, footprint in enumerate(root.children("footprint")):
        reference = _reference_of(footprint) or f"footprint{index}"
        external = footprint.value("uuid") or f"footprint:{reference}"
        at = _point(footprint, "at")
        rotation = footprint.child("at").atoms() if footprint.child("at") else []
        identity = identity_for(
            external, "placement", f"imported.placement.{_path_safe(reference)}"
        )
        component = table.canonical(reference)
        record(
            Placement(
                identity,
                component=component or "",
                layer=layer_of(footprint),
                x=_mm(str(at.x)) if at else None,
                y=_mm(str(at.y)) if at else None,
                # A rotation is an angle, not a length; the board writes
                # it in degrees and it is carried in degrees.
                rotation=Quantity.scalar(rotation[2], "deg")
                if len(rotation) > 2
                else None,
                provenance=provenance(),
                source_location=SourceLocation(source, 0),
            )
        )
        if component is None:
            report.note(
                "footprint", f"{source}:{reference}",
                "no component in the graph carries this reference",
            )

        for pad in footprint.children("pad"):
            atoms = pad.atoms()
            number = atoms[0] if atoms else ""
            pad_external = pad.value("uuid") or f"pad:{reference}.{number}"
            pin = table.canonical(f"{reference}.{number}")
            pad_identity = identity_for(
                pad_external,
                "pad",
                f"imported.pad.{_path_safe(reference)}.{_path_safe(number)}",
            )
            record(
                Pad(
                    pad_identity,
                    pin=pin or "",
                    placement=identity.id,
                    layer=layer_of(pad, "layers"),
                    pad_number=number,
                    at=_point(pad, "at"),
                    provenance=provenance(),
                    source_location=SourceLocation(source, 0),
                )
            )
            pads_by_reference[(reference, number)] = pad_identity.id

    # -- the copper --------------------------------------------------------
    for index, segment in enumerate(root.children("segment")):
        start, end = _point(segment, "start"), _point(segment, "end")
        external = segment.value("uuid") or f"segment:{index}"
        identity = identity_for(external, "trace", f"imported.trace[{index}]")
        record(
            Trace(
                identity,
                net=net_of(segment) or "",
                layer=layer_of(segment),
                width=_mm(segment.value("width")),
                length=_segment_length(start, end) if start and end else None,
                path=tuple(p for p in (start, end) if p is not None),
                provenance=provenance(),
                source_location=SourceLocation(source, 0),
            )
        )

    for index, via in enumerate(root.children("via")):
        external = via.value("uuid") or f"via:{index}"
        identity = identity_for(external, "via", f"imported.via[{index}]")
        spanned = via.child("layers")
        record(
            Via(
                identity,
                net=net_of(via) or "",
                layers=tuple(
                    layer_by_name[name]
                    for name in (spanned.atoms() if spanned else [])
                    if name in layer_by_name
                ),
                drill=_mm(via.value("drill")),
                diameter=_mm(via.value("size")),
                at=_point(via, "at"),
                provenance=provenance(),
                source_location=SourceLocation(source, 0),
            )
        )

    for index, zone in enumerate(root.children("zone")):
        external = zone.value("uuid") or f"zone:{index}"
        identity = identity_for(external, "zone", f"imported.zone[{index}]")
        polygon = zone.child("polygon")
        points = polygon.child("pts") if polygon else None
        record(
            Zone(
                identity,
                net=net_of(zone),
                layer=layer_of(zone),
                clearance=_mm(zone.value("clearance")),
                outline=tuple(
                    _xy(child) for child in (points.children("xy") if points else [])
                ),
                provenance=provenance(),
                source_location=SourceLocation(source, 0),
            )
        )

    return ImportResult(entities, table, report)


def _xy(node: Node) -> Point:
    atoms = node.atoms()
    return Point.of(atoms[0], atoms[1])


def _reference_of(footprint: Node) -> str | None:
    """The designator a footprint carries, in either spelling KiCad writes."""
    for prop in footprint.children("property"):
        atoms = prop.atoms()
        if len(atoms) >= 2 and atoms[0] == "Reference":
            return atoms[1]
    for text in footprint.children("fp_text"):
        atoms = text.atoms()
        if len(atoms) >= 2 and atoms[0] == "reference":
            return atoms[1]
    return None


# --------------------------------------------------------------------------
# A board against the netlist it claims to realize
# --------------------------------------------------------------------------


def board_connectivity(
    text: str, *, source: str = "<board>"
) -> dict[str, tuple[tuple[str, str], ...]]:
    """Which `(reference, pad)` a board file joins on each net it names.

    Read for comparison and thrown away. It is deliberately not an entity: the
    netlist already holds this connectivity, so storing the board's account of
    it would make the physical layer a peer source of truth for a fact the
    layers above it own.
    """
    root = parse(text)
    if root.head != "kicad_pcb":
        raise SExprError(f"{source} is not a board: its top level is {root.head!r}")

    names: dict[str, str] = {}
    for net in root.children("net"):
        atoms = net.atoms()
        if len(atoms) >= 2:
            names[atoms[0]] = atoms[1]

    joins: dict[str, set[tuple[str, str]]] = {}
    for index, footprint in enumerate(root.children("footprint")):
        reference = _reference_of(footprint) or f"footprint{index}"
        for pad in footprint.children("pad"):
            atoms = pad.atoms()
            name = names.get(pad.value("net") or "")
            if not atoms or not name:
                continue
            joins.setdefault(name, set()).add((reference, atoms[0]))
    return {name: tuple(sorted(pads)) for name, pads in sorted(joins.items())}


def _netlist_index(netlist: Netlist):
    """`(designator, pin)` to its netlist net name, and to its pin identifier."""
    net_of: dict[tuple[str, str], str] = {}
    pin_of: dict[tuple[str, str], str] = {}
    for net in netlist.nets:
        for node in net.nodes:
            net_of[(node.designator, node.pin)] = net.name
            pin_of[(node.designator, node.pin)] = node.pin_id
    return net_of, pin_of


def compare_board_to_netlist(
    text: str, netlist: Netlist, *, source: str = "<board>"
) -> list[Diagnostic]:
    """Report where a board joins pins the committed netlist keeps apart.

    Where the two disagree the semantic layer governs, so this reports and
    returns. Nothing here rewrites the netlist to match the copper — the copper
    is what is wrong when they differ, and saying so is the useful output.
    """
    net_of, _ = _netlist_index(netlist)
    findings = []
    for name, pads in board_connectivity(text, source=source).items():
        by_net: dict[str, list[tuple[str, str]]] = {}
        for pad in pads:
            if pad in net_of:
                by_net.setdefault(net_of[pad], []).append(pad)
        if len(by_net) > 1:
            joined = "; ".join(
                f"{net} holds " + ", ".join(f"{ref}.{pad}" for ref, pad in sorted(members))
                for net, members in sorted(by_net.items())
            )
            findings.append(
                Diagnostic(
                    TOPO_BOARD_DISAGREES,
                    Severity.ERROR,
                    f"the board's net {name!r} joins pins the netlist keeps "
                    f"apart: {joined}",
                    location=SourceLocation(source, 0),
                )
            )
    return findings


def implied_pin_swaps(
    text: str,
    netlist: Netlist,
    snapshot,
    *,
    source: str = "<board>",
) -> tuple:
    """The semantic changes a board's pin swaps imply, as operations.

    A router may legitimately exchange two pins of one part. That is a change to
    the design, not to its picture, so it does not enter by being read: it comes
    back as operations the gate evaluates like any other. Nothing here applies
    them.
    """
    from .graph import Connect, RemoveEntity

    board = board_connectivity(text, source=source)
    board_net_of = {pad: name for name, pads in board.items() for pad in pads}
    net_of, pin_of = _netlist_index(netlist)

    moved = {
        pad: board_net_of[pad]
        for pad in sorted(net_of)
        if pad in board_net_of and board_net_of[pad] != net_of[pad]
    }
    # A swap is a pair that exchanged nets within one component. A pin that
    # merely moved somewhere else is a disagreement, which `compare_board_to_
    # netlist` reports; it is not a swap to offer back.
    swapped = sorted(
        pad
        for pad, destination in moved.items()
        if any(
            other != pad
            and other[0] == pad[0]
            and moved[other] == net_of[pad]
            and destination == net_of[other]
            for other in moved
        )
    )

    operations = []
    for pad in swapped:
        pin = pin_of[pad]
        connections = sorted(
            (e for e in snapshot.entities.values()
             if isinstance(e, Connection) and pin in (e.source, e.target)),
            key=lambda e: e.id,
        )
        reason = f"layout swapped {pad[0]}.{pad[1]} onto {moved[pad]}"
        for connection in connections:
            operations.append(RemoveEntity(target=connection.id, reason=reason))

        partner = next(
            (
                pin_of[other]
                for other in sorted(net_of)
                if net_of[other] == moved[pad] and other not in swapped
            ),
            None,
        )
        if partner is None:
            continue
        kind = connections[0].connection_kind if connections else ConnectionKind.ELECTRICAL
        identity = derive(
            snapshot.project_id,
            # A connection derives under the net prefix, as `elaborate` does:
            # one convention for one kind, wherever the connection came from.
            "net",
            f"layout.swap.{_path_safe(pad[0])}.{_path_safe(pad[1])}",
            taken=set(snapshot.entities),
        )
        operations.append(
            Connect(
                connection=Connection(
                    identity,
                    connection_kind=kind,
                    source=pin,
                    target=partner,
                    provenance=Provenance().append(
                        ProvenanceRecord(
                            ProvenanceOrigin.IMPORTED,
                            "kicad_board_import",
                            Actor(ActorKind.ADAPTER, "fang-kicad"),
                            snapshot.revision_id,
                            datetime.now(timezone.utc),
                            source_location=SourceLocation(source, 0),
                        )
                    ),
                    source_location=SourceLocation(source, 0),
                ),
                reason=reason,
            )
        )
    return tuple(operations)


def board_realization(
    text: str,
    netlist: Netlist,
    snapshot,
    *,
    parent_snapshot: str | None = None,
    source: str = "<board>",
):
    """A board as a realization of the snapshot it was compiled from.

    It names its parent, so `graph.materialize` refuses it against any other
    snapshot; and it carries what the layout implies rather than applying it.
    """
    from .graph import Realization

    return Realization(
        "board",
        parent_snapshot if parent_snapshot is not None else netlist.snapshot,
        configuration={"source": source},
        tools=("kicad",),
        implied_changes=implied_pin_swaps(text, netlist, snapshot, source=source),
    )
