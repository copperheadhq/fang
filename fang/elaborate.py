"""Elaboration: a Fang program becomes a graph snapshot and a tool plan.

Spec: "Deterministic Sandboxed Elaboration" and "The Elaboration Result".

Elaboration builds a graph. It never mutates geometry and never calls a tool.
Its output is data: the Python object graph is not reachable from the snapshot
and is not the persisted design state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from . import SCHEMA_VERSION, __version__
from .constraints import Constraint, ConstraintClass, Enforcement, Node
from .diagnostics import (
    ELAB_UNTYPED_CONNECTION,
    Diagnostic,
    FangError,
    Severity,
    SourceLocation,
)
from .entities import (
    Assumption,
    Calculation,
    Component,
    Connection,
    ConnectionKind,
    Decision,
    Entity,
    Evidence,
    Interface,
    Pin,
    Port,
    Requirement,
    Signal as SignalSpec,
    Verification,
)
from .graph import Snapshot
from .identity import Identity, Origin, Path, derive, transliterate_siblings
from .interfaces import InterfacePort
from .lowering import emit as emit_lowering, lower
from .lang import ElaborationContext, Module, Surface, System, class_location
from .provenance import Actor, ActorKind, Input, Provenance, ProvenanceOrigin, ProvenanceRecord
from .sandbox import Inputs, Sandbox, SandboxViolation
from .toolplan import ToolPlan
from .traits import TraitRegistry
from .validation import ValidationReport, validate
from .values import Value

#: The default build time. Fixed rather than wall-clock, so reproducibility is
#: the default rather than something a caller has to opt into. A caller that
#: wants the real build time passes it, and thereby declares it as part of the
#: build identity alongside the lock id.
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)

#: An architecture block entity kind maps onto this entity class.
_BLOCK_KIND = "block"


@dataclass(frozen=True)
class Elaboration:
    """Exactly what elaboration returns: a snapshot, a plan, and diagnostics.

    The Python object graph is not here, and cannot be recovered from here.
    """

    snapshot: Snapshot | None
    plan: ToolPlan
    diagnostics: tuple[Diagnostic, ...] = ()
    traits: TraitRegistry = field(default_factory=TraitRegistry)
    validation: ValidationReport | None = None

    @property
    def ok(self) -> bool:
        return self.snapshot is not None and not any(
            d.severity.blocking for d in self.diagnostics
        )

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "snapshot": self.snapshot.as_dict() if self.snapshot else None,
            "plan": self.plan.as_dict(),
            "diagnostics": [d.as_dict() for d in self.diagnostics],
            "traits": self.traits.as_dict(),
        }


class _Block(Entity):
    """An architecture block. Declared here because it is the module's entity."""

    kind: str = _BLOCK_KIND


def _block(identity: Identity, **kwargs) -> Entity:
    return Entity(identity=identity, kind=_BLOCK_KIND, **kwargs)


def elaborate(
    system: System | type[System],
    *,
    project_id: str,
    root: str = "system",
    inputs: Inputs | None = None,
    seed: int | None = None,
    lock_id: str = "unlocked",
    built_at: datetime = EPOCH,
    revision_id: str = "REV-000000",
    enforce_sandbox: bool = True,
) -> Elaboration:
    """Elaborate a program into a snapshot and a tool plan.

    Identical source, dependency lock, compiler version, and declared build time
    produce an identical snapshot and an identical plan.
    """
    if isinstance(system, type):
        instance = system()
        # Instantiated here, so it has no declaring line; its class definition is
        # the real and stable location.
        instance._source = class_location(system) or instance._source
    else:
        instance = system
    diagnostics: list[Diagnostic] = []
    sandbox = Sandbox(inputs, seed=seed, enforce=enforce_sandbox)
    context = ElaborationContext()

    try:
        with sandbox, context:
            _assign_paths(instance, root, project_id)
            _run_hooks(instance, context)
            entities, traits, pin_ids = _build_entities(
                instance, project_id, revision_id, built_at, sandbox
            )
            connections, ordered = _build_connections(
                context, project_id, revision_id, built_at
            )
            entities.update(connections)
            entities.update(
                _build_lowerings(ordered, pin_ids, project_id, revision_id, built_at)
            )
            entities.update(_build_constraints(context, project_id, revision_id, built_at))
    except FangError as exc:
        # A failed elaboration produces diagnostics and no partial graph.
        return Elaboration(None, context.plan.plan(), (exc.diagnostic,))
    except SandboxViolation as exc:
        return Elaboration(
            None,
            context.plan.plan(),
            (
                Diagnostic(
                    "ELAB-0001",
                    Severity.ERROR,
                    f"the elaboration sandbox refused an operation: {exc}",
                ),
            ),
        )

    snapshot = Snapshot(
        project_id,
        revision_id,
        entities,
        schema_version=SCHEMA_VERSION,
        compiler_version=__version__,
        lock_id=lock_id,
    )

    report = validate(entities)
    diagnostics.extend(report.diagnostics)
    if not report.ok:
        return Elaboration(None, context.plan.plan(), tuple(diagnostics), traits, report)

    return Elaboration(
        snapshot, context.plan.plan().with_snapshot(snapshot.hash), tuple(diagnostics), traits, report
    )


# --------------------------------------------------------------------------
# Walking the tree
# --------------------------------------------------------------------------


def _walk(module: Module, path: str) -> Iterable[tuple[str, Module]]:
    """Depth-first in declaration order, so the traversal is reproducible."""
    yield path, module
    children = module.children()
    ordered = sorted(children.items(), key=lambda kv: kv[1]._order)
    names = transliterate_siblings([name for name, _ in ordered])
    for name, child in ordered:
        yield from _walk(child, f"{path}.{names[name]}")


def _assign_paths(root_module: Module, root: str, project_id: str) -> None:
    """Give every module and surface its canonical semantic path and identity."""
    for path, module in _walk(root_module, root):
        module._path = path
        module._entity_id = derive(project_id, _identity_kind(module), path).id

        surfaces = module.surfaces()
        ordered = sorted(surfaces.items(), key=lambda kv: kv[1]._order)
        names = transliterate_siblings([name for name, _ in ordered])
        for name, surface in ordered:
            module._port_ids[name] = derive(
                project_id, "port", f"{path}.{names[name]}"
            ).id


def _identity_kind(module: Module) -> str:
    return "component" if module.entity_kind == "component" else "block"


def _run_hooks(root_module: Module, context: ElaborationContext) -> None:
    """Run architecture() then constraints(), top-down in declaration order."""
    modules = [module for _, module in _walk(root_module, root_module._path or "system")]
    for module in modules:
        context.current = module
        module.architecture()
    for module in modules:
        context.current = module
        module.constraints()
    context.current = None


# --------------------------------------------------------------------------
# Building entities
# --------------------------------------------------------------------------


def _provenance(
    revision_id: str,
    built_at: datetime,
    location: SourceLocation | None,
    *,
    derived_from: Sequence[str] = (),
    inputs: Sequence[Input] = (),
) -> Provenance:
    return Provenance().append(
        ProvenanceRecord(
            ProvenanceOrigin.GENERATED,
            "elaboration",
            Actor(ActorKind.TOOL, "fang", __version__),
            revision_id,
            built_at,
            derived_from=tuple(derived_from),
            inputs=tuple(inputs),
            source_location=location,
        )
    )


def _build_entities(
    root_module: Module,
    project_id: str,
    revision_id: str,
    built_at: datetime,
    sandbox: Sandbox,
) -> tuple[dict[str, Entity], TraitRegistry, dict[tuple[str, str], str]]:
    entities: dict[str, Entity] = {}
    traits = TraitRegistry()
    interface_ids: dict[str, str] = {}
    pin_ids: dict[tuple[str, str], str] = {}
    declared_inputs = tuple(Input(d.id, d.hash) for d in sandbox.inputs)

    for path, module in _walk(root_module, root_module._path or "system"):
        parameters = {
            name: module.value_of(name) for name in sorted(type(module)._parameters)
        }
        provenance = _provenance(
            revision_id, built_at, module._source, inputs=declared_inputs
        )
        identity = derive(
            project_id,
            _identity_kind(module),
            path,
            display_name=type(module).__name__,
        )

        if module.entity_kind == "component":
            entity: Entity = Component(
                identity,
                parameters=parameters,
                provenance=provenance,
                source_location=module._source,
                designator=getattr(module, "designator", None),
                part=type(module).__name__,
                package=getattr(module, "package", None),
                extensions=_part_extensions(module),
            )
        else:
            entity = Entity(
                identity=identity,
                kind=_BLOCK_KIND,
                parameters=parameters,
                provenance=provenance,
                source_location=module._source,
            )
        entities[entity.id] = entity

        for trait in module.traits:
            traits.attach(entity.id, trait)

        # One interface entity per surface type in use; a port instance per
        # declared surface. Stage 3 replaces these with the full catalogue.
        for name, surface in sorted(module.surfaces().items(), key=lambda kv: kv[1]._order):
            interface_id = interface_ids.get(surface.surface_type)
            if interface_id is None:
                interface_identity = derive(
                    project_id, "interface", f"catalogue.{surface.surface_type}"
                )
                interface = Interface(
                    interface_identity,
                    interface_type=surface.surface_type,
                    signals=_signal_specs(surface),
                    provenance=_provenance(revision_id, built_at, surface._source),
                    source_location=surface._source,
                )
                entities[interface.id] = interface
                interface_id = interface.id
                interface_ids[surface.surface_type] = interface_id

            port = Port(
                Identity(
                    module._port_ids[name],
                    Origin.DERIVED,
                    path=Path.parse(f"{path}.{name}"),
                    uuid=derive(project_id, "port", f"{path}.{name}").uuid,
                    display_name=name,
                ),
                interface=interface_id,
                owner=entity.id,
                parameters=_port_parameters(surface),
                provenance=_provenance(revision_id, built_at, surface._source),
                source_location=surface._source,
                direction=surface.direction,
            )
            entities[port.id] = port

        # Whatever the module records about its own reasoning becomes entities
        # too, so the engineering argument lives with the design rather than in
        # a document beside it.
        declarations = sorted(module.rationale().items(), key=lambda kv: kv[1]._order)
        # Resolve sibling names first: a program writes `inputs=("top", "bottom")`
        # and means the modules beside it, not literal strings.
        scope = {
            attribute: derive(
                project_id, declaration.entity_kind, f"{path}.{attribute}"
            ).id
            for attribute, declaration in declarations
        }
        scope.update(
            {attribute: child._entity_id for attribute, child in module.children().items()}
        )
        for name, declaration in declarations:
            rationale_entity = _rationale_entity(
                declaration, f"{path}.{name}", project_id, revision_id, built_at, scope
            )
            entities[rationale_entity.id] = rationale_entity

        # A part's pins are entities in their own right, owned by the component.
        for name, pin in sorted(module.pins().items(), key=lambda kv: kv[1]._order):
            pin_identity = derive(project_id, "pin", f"{path}.{name}")
            pin_entity = Pin(
                pin_identity,
                owner=entity.id,
                vendor_name=pin.name,
                role=pin.role,
                number=pin.number,
                provenance=_provenance(revision_id, built_at, pin._source),
                source_location=pin._source,
            )
            entities[pin_entity.id] = pin_entity
            pin_ids[(entity.id, pin.name)] = pin_entity.id

    return entities, traits, pin_ids


def _build_connections(
    context: ElaborationContext,
    project_id: str,
    revision_id: str,
    built_at: datetime,
) -> tuple[dict[str, Entity], list[tuple[Connection, Surface, Surface, SourceLocation | None]]]:
    """Build the interface connections, and pair each with the surfaces it came
    from so the lowering does not have to guess the correspondence."""
    entities: dict[str, Entity] = {}
    ordered: list[tuple[Connection, Surface, Surface, SourceLocation | None]] = []
    for index, (left, right, location) in enumerate(context.connections):
        source_id = left._entity_id
        target_id = right._entity_id
        path = f"connection.{index:04d}"
        identity = derive(project_id, "net", path)
        connection = Connection(
            identity,
            connection_kind=_connection_kind(left, right),
            source=source_id,
            target=target_id,
            provenance=_provenance(revision_id, built_at, location),
            source_location=location,
        )
        entities[connection.id] = connection
        ordered.append((connection, left, right, location))
    return entities, ordered


def _connection_kind(left: Surface, right: Surface) -> ConnectionKind:
    """The stronger of the two surface kinds names the connection."""
    if left.connection_kind is right.connection_kind:
        return left.connection_kind
    for candidate in (left, right):
        if candidate.connection_kind is not ConnectionKind.ELECTRICAL:
            return candidate.connection_kind
    return ConnectionKind.ELECTRICAL


def _build_constraints(
    context: ElaborationContext,
    project_id: str,
    revision_id: str,
    built_at: datetime,
) -> dict[str, Entity]:
    entities: dict[str, Entity] = {}
    for index, (module, expression, location) in enumerate(context.constraints):
        path = f"{module._path}.constraint[{index}]"
        identity = derive(project_id, "constraint", path)
        constraint = Constraint(
            identity,
            constraint_class=ConstraintClass.ELECTRICAL,
            constraint_kind="declared",
            targets=(module._entity_id,),
            expression=expression,
            enforcement=Enforcement.HARD,
            provenance=_provenance(revision_id, built_at, location),
            source_location=location,
        )
        entities[constraint.id] = constraint
    return entities


def _signal_specs(surface: Surface) -> tuple[SignalSpec, ...]:
    """An interface entity's signals come from its type, with real roles."""
    if isinstance(surface, InterfacePort):
        return tuple(
            SignalSpec(spec.name, spec.role, spec.direction, spec.required)
            for spec in surface.interface.signals
        )
    return tuple(SignalSpec(signal, surface.surface_type) for signal in surface.signals)


def _port_parameters(surface: Surface) -> dict[str, Value]:
    """The electrical parameters a port declares, validated against its type."""
    if not isinstance(surface, InterfacePort):
        return {}
    declared = surface.interface.parameters
    parameters: dict[str, Value] = {}
    for name, quantity in sorted(surface.parameter_values.items()):
        if isinstance(quantity, Value):
            parameters[name] = quantity
            continue
        expected = declared.get(name)
        if expected is not None:
            from .units import Unit

            if quantity.dimension != Unit.parse(expected).dimension:
                raise FangError(
                    Diagnostic(
                        "UNIT-0001",
                        Severity.ERROR,
                        f"{surface.interface.name}.{name} is declared in {expected} "
                        f"but was given {quantity.unit}",
                        location=surface._source,
                    )
                )
        parameters[name] = Value.explicit(quantity)
    return parameters


def _build_lowerings(
    ordered: Sequence[tuple[Connection, Surface, Surface, SourceLocation | None]],
    pin_ids: Mapping[tuple[str, str], str],
    project_id: str,
    revision_id: str,
    built_at: datetime,
) -> dict[str, Entity]:
    """Lower every interface connection to pin connections.

    A lowering that cannot be completed raises, so no partial pin mapping is
    ever recorded.
    """
    entities: dict[str, Entity] = {}

    for connection, left, right, location in ordered:
        connection_id = connection.id
        if not (left.owner.pin_map and right.owner.pin_map):
            # Neither side declares pins yet; the interface connection stands on
            # its own until a part selection gives it pins to lower onto.
            continue

        lowering = lower(
            left,
            right,
            connection_id=connection_id,
            path=str(connection.identity.path or ""),
        )
        entities.update(
            emit_lowering(
                lowering,
                pin_ids=pin_ids,
                derive_id=lambda kind, path: derive(project_id, kind, path),
                provenance=_provenance(
                    revision_id, built_at, location, derived_from=(connection_id,)
                ),
                source_location=location,
            )
        )
    return entities


def _part_extensions(module: Module) -> dict:
    """What a part declares that the entity model does not have a field for.

    The designator prefix belongs to the part type, and the netlist compiler
    needs it; carrying it here keeps it out of the entity schema until something
    other than the netlist wants it.
    """
    extensions: dict = {"designator_prefix": getattr(module, "designator_prefix", "U")}
    manufacturer = getattr(module, "manufacturer", None)
    mpn = getattr(module, "mpn", None)
    if manufacturer:
        extensions["manufacturer"] = manufacturer
    if mpn:
        extensions["mpn"] = mpn
    return extensions


def _rationale_entity(
    declaration,
    path: str,
    project_id: str,
    revision_id: str,
    built_at: datetime,
    scope: Mapping[str, str],
) -> Entity:
    """Turn one rationale declaration into its entity.

    A name that matches something declared beside it resolves to that entity's
    identifier; anything else is left alone, because it names a document or an
    entity outside this module.
    """

    def ref(name: str) -> str:
        return scope.get(name, name)

    def refs(names) -> tuple[str, ...]:
        return tuple(ref(name) for name in names)

    kind = declaration.entity_kind
    identity = derive(project_id, kind, path, display_name=declaration.attribute)
    provenance = _provenance(revision_id, built_at, declaration._source)
    common = {
        "provenance": provenance,
        "source_location": declaration._source,
    }

    if kind == "requirement":
        return Requirement(
            identity,
            statement=declaration.statement,
            state=declaration.state,
            priority=declaration.priority,
            source=declaration.source,
            validation_method=declaration.validation,
            **common,
        )
    if kind == "assumption":
        return Assumption(
            identity, claim=declaration.claim, rationale=declaration.rationale, **common
        )
    if kind == "evidence":
        return Evidence(
            identity,
            claim=declaration.claim,
            document=declaration.document,
            locator=declaration.locator or None,
            **common,
        )
    if kind == "decision":
        return Decision(
            identity,
            question=declaration.question,
            choice=declaration.selected,
            rationale=declaration.rationale,
            alternatives_rejected=declaration.alternatives,
            requirements=refs(declaration.requirements),
            **common,
        )
    if kind == "calculation":
        return Calculation(
            identity,
            expression=declaration.expression,
            inputs=refs(declaration.inputs),
            result=declaration.result,
            requirements=refs(declaration.requirements),
            **common,
        )
    if kind == "verification":
        return Verification(
            identity,
            verifies=ref(declaration.verifies),
            method=declaration.method,
            evidence=refs(declaration.evidence),
            result=declaration.result,
            **common,
        )
    raise ValueError(f"no entity is defined for rationale kind {kind!r}")
