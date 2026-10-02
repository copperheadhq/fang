"""Interface compatibility checking.

Spec: "Interface Compatibility Checks", "Interface Compatibility
Evaluation", and "An Addressed Bus Device Carries Its Address".

A check whose inputs are unknown returns undecided and names the missing input.
It never passes by default, because a check that passes on absent data is worse
than no check.

Two rules decide what a link is, and both exist to keep that promise honest:

- The parties to a link are the ports whose interface declares parameters. A
  resistor pad or a test point is a wire on the link, not a party to it, and a
  check is run only over the parameters every party declares. An undecided
  result about a fact one side was never supposed to carry reads like a finding
  and is not one.
- An interface continues through a part that declares it bridges its terminals,
  so a connector and the device behind two series resistors are the two ends of
  one link and are compared with each other. Without that, the only thing the
  check has to say about the pair is what the resistors think of it.

Addressing is read from the board, not from firmware. A device's port carries
its address, fixed or strapped, and `resolve_address` is the one function that
reads it, so the check and anything else that needs an address cannot disagree.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable, Mapping, Sequence

from .constraints import CheckStatus
from .diagnostics import Severity
from .entities import Connection, Entity, Evidence, Interface, Pin, Port
from .interfaces import CATALOGUE, InterfaceType
from .units import Quantity
from .values import ConflictingValue, Value, ValueStatus

#: The noise margin applied to a logic-level comparison. Zero by default: a
#: margin is an engineering choice, and inventing one would hide a real
#: shortfall behind a number nobody chose.
DEFAULT_MARGIN = Quantity.scalar("0", "V")


@dataclass(frozen=True)
class Link:
    """One interface connection and the ports that participate in it."""

    connection: str
    interface: InterfaceType
    participants: tuple[str, ...]

    @property
    def multi_drop(self) -> bool:
        return self.interface.multi_drop


def _value(port: Port, name: str) -> Value | None:
    value = port.parameters.get(name)
    return value if isinstance(value, Value) else None


def _interval(value: Value | None) -> tuple[Decimal, Decimal] | None:
    if value is None or not value.known or value.quantity is None:
        return None
    return value.quantity.interval()


def _evidence(*values: Value | None) -> tuple[str, ...]:
    """The evidence entities behind the inputs a result used."""
    return tuple(
        sorted(
            {
                value.source
                for value in values
                if value is not None and value.source and value.status is not ValueStatus.EXPLICIT
            }
            | {
                value.source
                for value in values
                if value is not None and value.source and value.status is ValueStatus.EXPLICIT
            }
        )
    )


def _port_interface(port: Port, entities: Mapping[str, Entity]) -> InterfaceType | None:
    entity = entities.get(port.interface)
    return _interface_type(entity) if isinstance(entity, Interface) else None


def _declared_parameters(port: Port, entities: Mapping[str, Entity]) -> frozenset[str]:
    """The parameters this port's interface is supposed to carry.

    A plain pad declares none, which is the difference between a wire and a
    contract.
    """
    interface = _port_interface(port, entities)
    return frozenset(interface.parameters) if interface is not None else frozenset()


def _shared_parameters(
    ports: Sequence[Port], entities: Mapping[str, Entity]
) -> frozenset[str]:
    """The parameters every participant declares.

    A comparison is only meaningful over a fact both sides are supposed to hold.
    A 22 Ohm resistor in series with a USB pair declares no logic levels and no
    bit rate, so asking it for them yields an undecided result about nothing —
    which is worse than silence, because it reads like a finding.
    """
    shared: frozenset[str] | None = None
    for port in ports:
        declared = _declared_parameters(port, entities)
        shared = declared if shared is None else (shared & declared)
    return shared if shared is not None else frozenset()


def find_links(entities: Mapping[str, Entity]) -> list[Link]:
    """Group port-to-port connections into links, merging a bus's participants."""
    interfaces = {
        entity.id: entity for entity in entities.values() if isinstance(entity, Interface)
    }
    ports = {entity.id: entity for entity in entities.values() if isinstance(entity, Port)}

    links: list[Link] = []
    #: A multi-drop interface merges every connection touching the same members.
    merged: dict[str, set[str]] = {}
    merged_order: list[str] = []

    for connection in sorted(
        (e for e in entities.values() if isinstance(e, Connection)), key=lambda c: c.id
    ):
        source, target = ports.get(connection.source), ports.get(connection.target)
        if source is None or target is None:
            continue
        interface_entity = interfaces.get(source.interface)
        if interface_entity is None:
            continue
        interface = _interface_type(interface_entity)
        if interface is None:
            continue

        if not interface.multi_drop:
            links.append(Link(connection.id, interface, (source.id, target.id)))
            continue

        for key, participants in merged.items():
            if participants & {source.id, target.id}:
                participants |= {source.id, target.id}
                break
        else:
            merged[connection.id] = {source.id, target.id}
            merged_order.append(connection.id)

    for key in merged_order:
        interface_entity = interfaces[ports[sorted(merged[key])[0]].interface]
        interface = _interface_type(interface_entity)
        if interface is not None:
            links.append(Link(key, interface, tuple(sorted(merged[key]))))

    links.extend(_series_links(entities, ports, links))
    return sorted(links, key=lambda link: (link.connection, link.participants))


def _bridged_ports(entities: Mapping[str, Entity], ports: Mapping[str, Port]) -> dict[str, set[str]]:
    """Port adjacency across the parts that declare they conduct between them.

    A part says which of its own surfaces it bridges; nothing else in the graph
    does, because a component's body is not a connection.
    """
    by_owner: dict[str, dict[str, str]] = {}
    for port in ports.values():
        name = port.identity.display_name
        if name:
            by_owner.setdefault(port.owner, {})[name] = port.id

    adjacency: dict[str, set[str]] = {}
    for entity in entities.values():
        pairs = getattr(entity, "extensions", {}).get("bridges") or ()
        names = by_owner.get(entity.id, {})
        for pair in pairs:
            left, right = (names.get(pair[0]), names.get(pair[1]))
            if left and right:
                adjacency.setdefault(left, set()).add(right)
                adjacency.setdefault(right, set()).add(left)
    return adjacency


def _series_links(
    entities: Mapping[str, Entity],
    ports: Mapping[str, Port],
    direct: Sequence[Link],
) -> list[Link]:
    """Links between two interfaces that a series part stands between.

    A connector and the bridge IC behind two 22 Ohm resistors are the two ends of
    one USB link. Without this they are never compared with each other, and the
    only thing the check has to say about that pair is what the resistors think.
    """
    from .topology import CONDUCTIVE_KINDS

    wire: dict[str, set[str]] = {}
    connection_of: dict[tuple[str, str], str] = {}
    for connection in sorted(
        (e for e in entities.values() if isinstance(e, Connection)), key=lambda c: c.id
    ):
        if connection.connection_kind not in CONDUCTIVE_KINDS:
            continue
        source, target = connection.source, connection.target
        if source not in ports or target not in ports:
            continue
        wire.setdefault(source, set()).add(target)
        wire.setdefault(target, set()).add(source)
        connection_of.setdefault((source, target), connection.id)
        connection_of.setdefault((target, source), connection.id)

    bridges = _bridged_ports(entities, ports)
    carries = {
        port_id: _declared_parameters(port, entities) for port_id, port in ports.items()
    }
    already = {frozenset(link.participants) for link in direct}
    found: dict[frozenset, tuple[str, InterfaceType]] = {}

    for start in sorted(pid for pid, declared in carries.items() if declared):
        # Breadth-first through pads only: a contract-carrying port is an end of
        # the link, never a waypoint in it. The walk starts on a pad, so a link
        # that already exists directly is not rediscovered as a traced one.
        queue: list[tuple[str, str]] = [
            (neighbour, connection_of[(start, neighbour)])
            for neighbour in sorted(wire.get(start, ()))
            if not carries[neighbour]
        ]
        seen = {start}
        while queue:
            node, subject = queue.pop(0)
            if node in seen:
                continue
            seen.add(node)
            if carries[node]:
                pair = frozenset({start, node})
                left, right = _port_interface(ports[start], entities), _port_interface(ports[node], entities)
                # Two ends of one link are the same interface. Anything else is
                # a rail meeting a bus, which the direct link already covers.
                if left is not None and left is right and pair not in already:
                    existing = found.get(pair)
                    if existing is None or subject < existing[0]:
                        found[pair] = (subject, left)
                continue
            for neighbour in sorted(wire.get(node, set()) | bridges.get(node, set())):
                if neighbour in seen:
                    continue
                queue.append((neighbour, min(subject, connection_of.get((node, neighbour), subject))))

    return [
        Link(subject, interface, tuple(sorted(pair)))
        for pair, (subject, interface) in sorted(
            found.items(), key=lambda item: (item[1][0], sorted(item[0]))
        )
    ]


def _interface_type(entity: Interface) -> InterfaceType | None:
    if entity.interface_type in CATALOGUE:
        return CATALOGUE.get(entity.interface_type)
    return None


def check_link(
    link: Link,
    entities: Mapping[str, Entity],
    *,
    margin: Quantity = DEFAULT_MARGIN,
):
    """Evaluate one link. Returns the results, one per rule evaluated."""
    from .graph import CheckResult

    ports = [entities[pid] for pid in link.participants if pid in entities]

    # A pad on the link is a wire, not a party to it. A capacitor sitting on a
    # rail is not a second opinion about that rail's voltage, and a link with
    # only one party has nothing to compare against anything.
    parties = [port for port in ports if _declared_parameters(port, entities)]
    if len(parties) < 2:
        return []

    results: list[CheckResult] = []
    subject = link.connection

    def undecided(rule: str, missing: Sequence[str], detail: str = ""):
        return CheckResult(
            "interface_compatibility",
            CheckStatus.UNKNOWN,
            subject,
            message=(
                f"{rule} is undecided on {link.interface.name}: "
                f"{', '.join(missing)} unknown{'; ' + detail if detail else ''}"
            ),
            missing=tuple(missing),
        )

    # And only over what every party is supposed to declare: asking one side for
    # a fact its interface never carries produces an undecided result about
    # nothing, which reads like a finding and is not one.
    shared = _shared_parameters(parties, entities)

    if {"voh_min", "vih_min", "vol_max", "vil_max"} & shared:
        results.extend(_check_logic_levels(link, parties, subject, margin, undecided))
    if {"current_capability", "current_demand"} & shared:
        results.extend(_check_current(link, parties, subject, undecided))
    if "voltage" in shared:
        results.extend(_check_domains(link, parties, subject, undecided))
    if {"pull_up_resistance", "pull_up_supply"} & shared:
        results.extend(_check_pull_up(link, parties, subject, undecided))
    results.extend(
        _check_protocol(link, parties, subject, undecided, shared, entities=entities)
    )
    return results


def _check_logic_levels(link, ports, subject, margin, undecided):
    from .graph import CheckResult

    results = []
    margin_low, margin_high = margin.interval()

    for source in ports:
        for sink in ports:
            if source.id == sink.id:
                continue
            voh = _value(source, "voh_min")
            vih = _value(sink, "vih_min")
            if voh is None and vih is None:
                continue
            voh_interval, vih_interval = _interval(voh), _interval(vih)
            if voh_interval is None or vih_interval is None:
                missing = [
                    name
                    for name, interval in (("voh_min", voh_interval), ("vih_min", vih_interval))
                    if interval is None
                ]
                results.append(undecided("logic high margin", missing))
                continue
            if voh_interval[0] >= vih_interval[1] + margin_high:
                status, message = CheckStatus.PASS, "logic high margin holds"
            elif voh_interval[1] < vih_interval[0] + margin_low:
                status, message = (
                    CheckStatus.FAIL,
                    f"source voh_min {voh_interval[0]} is below sink vih_min "
                    f"{vih_interval[1]} plus margin",
                )
            else:
                results.append(
                    undecided("logic high margin", ["voh_min/vih_min overlap"])
                )
                continue
            results.append(
                CheckResult(
                    "interface_compatibility",
                    status,
                    subject,
                    message=f"{message} ({source.id} -> {sink.id})",
                    evidence=_evidence(voh, vih),
                )
            )

            vol = _value(source, "vol_max")
            vil = _value(sink, "vil_max")
            vol_interval, vil_interval = _interval(vol), _interval(vil)
            if vol_interval is None or vil_interval is None:
                if vol is not None or vil is not None:
                    missing = [
                        name
                        for name, interval in (("vol_max", vol_interval), ("vil_max", vil_interval))
                        if interval is None
                    ]
                    results.append(undecided("logic low margin", missing))
                continue
            low_ok = vol_interval[1] <= vil_interval[0] - margin_high
            results.append(
                CheckResult(
                    "interface_compatibility",
                    CheckStatus.PASS if low_ok else CheckStatus.FAIL,
                    subject,
                    message=(
                        "logic low margin holds"
                        if low_ok
                        else f"source vol_max {vol_interval[1]} exceeds sink vil_max "
                        f"{vil_interval[0]} less margin"
                    )
                    + f" ({source.id} -> {sink.id})",
                    evidence=_evidence(vol, vil),
                )
            )
    return results


def _check_current(link, ports, subject, undecided):
    from .graph import CheckResult

    results = []
    capabilities = [(p, _value(p, "current_capability")) for p in ports]
    demands = [(p, _value(p, "current_demand")) for p in ports]
    supplying = [(p, v) for p, v in capabilities if v is not None]
    drawing = [(p, v) for p, v in demands if v is not None]
    if not supplying and not drawing:
        return results
    if not supplying or not drawing:
        results.append(
            undecided(
                "current capability",
                ["current_capability"] if not supplying else ["current_demand"],
            )
        )
        return results

    total_low = sum((_interval(v)[0] for _, v in drawing), Decimal(0))
    total_high = sum((_interval(v)[1] for _, v in drawing), Decimal(0))
    for port, capability in supplying:
        interval = _interval(capability)
        if interval is None:
            results.append(undecided("current capability", ["current_capability"]))
            continue
        if interval[0] >= total_high:
            status, message = CheckStatus.PASS, "current capability covers demand"
        elif interval[1] < total_low:
            status, message = (
                CheckStatus.FAIL,
                f"capability {interval[1]} is below demand {total_low}",
            )
        else:
            results.append(undecided("current capability", ["capability/demand overlap"]))
            continue
        results.append(
            CheckResult(
                "interface_compatibility",
                status,
                subject,
                message=f"{message} ({port.id})",
                evidence=_evidence(capability, *(v for _, v in drawing)),
            )
        )
    return results


def _check_domains(link, ports, subject, undecided):
    """Voltage domains must agree across every participant, not just two."""
    from .graph import CheckResult

    results = []
    declared = [(p, _value(p, "voltage")) for p in ports]
    known = [(p, v) for p, v in declared if _interval(v) is not None]
    if not known:
        return results
    if len(known) < len(declared):
        missing = [p.id for p, v in declared if _interval(v) is None]
        results.append(undecided("voltage domain", ["voltage"], f"on {', '.join(sorted(missing))}"))
        return results

    reference_port, reference = known[0]
    reference_interval = _interval(reference)
    for port, value in known[1:]:
        interval = _interval(value)
        agrees = interval == reference_interval
        results.append(
            CheckResult(
                "interface_compatibility",
                CheckStatus.PASS if agrees else CheckStatus.FAIL,
                subject,
                message=(
                    "voltage domains agree"
                    if agrees
                    else f"{port.id} is in a different voltage domain from "
                    f"{reference_port.id} ({interval[0]} against {reference_interval[0]})"
                ),
                evidence=_evidence(reference, value),
            )
        )
    return results


def _check_pull_up(link, ports, subject, undecided):
    """An open-drain interface needs a pull-up, and it needs a valid supply."""
    from .graph import CheckResult

    if not link.interface.requires_pull_up:
        return []

    resistances = [(p, _value(p, "pull_up_resistance")) for p in ports]
    declared = [(p, v) for p, v in resistances if _interval(v) is not None]
    if not declared:
        return [
            CheckResult(
                "interface_compatibility",
                CheckStatus.FAIL,
                subject,
                message=(
                    f"{link.interface.name} is open-drain and no participant "
                    "declares a pull-up resistance"
                ),
            )
        ]

    results = []
    for port, resistance in declared:
        supply = _value(port, "pull_up_supply")
        if _interval(supply) is None:
            results.append(undecided("pull-up supply", ["pull_up_supply"], f"on {port.id}"))
            continue
        rail = _interval(supply)
        domain = _interval(_value(port, "voltage"))
        if domain is not None and rail != domain:
            results.append(
                CheckResult(
                    "interface_compatibility",
                    CheckStatus.FAIL,
                    subject,
                    message=(
                        f"the pull-up on {port.id} is supplied from {rail[0]} but "
                        f"the bus domain is {domain[0]}"
                    ),
                    evidence=_evidence(supply),
                )
            )
        else:
            results.append(
                CheckResult(
                    "interface_compatibility",
                    CheckStatus.PASS,
                    subject,
                    message=f"pull-up on {port.id} is valid for the bus",
                    evidence=_evidence(supply, resistance),
                )
            )
    return results


def _check_protocol(
    link, ports, subject, undecided, shared=frozenset({"bit_rate"}), *, entities=None
):
    """Protocol, rate, and addressing must agree."""
    from .graph import CheckResult

    results = []
    rates = [(p, _value(p, "bit_rate")) for p in ports] if "bit_rate" in shared else []
    known = [(p, v) for p, v in rates if _interval(v) is not None]
    if known and len(known) < len(rates):
        results.append(undecided("bit rate", ["bit_rate"]))
    elif len(known) > 1:
        reference = _interval(known[0][1])
        for port, value in known[1:]:
            interval = _interval(value)
            overlaps = interval[0] <= reference[1] and reference[0] <= interval[1]
            results.append(
                CheckResult(
                    "interface_compatibility",
                    CheckStatus.PASS if overlaps else CheckStatus.FAIL,
                    subject,
                    message=(
                        "bit rates are compatible"
                        if overlaps
                        else f"{port.id} cannot meet the link's bit rate"
                    ),
                    evidence=_evidence(known[0][1], value),
                )
            )

    if link.multi_drop:
        results.extend(_check_addresses(link, ports, subject, undecided, entities or {}))
    return results


def _check_addresses(link, ports, subject, undecided, entities):
    """No two devices on one bus answer to one address.

    Every participant's address is read through `resolve_address`. A port that
    declares none, such as the controller's, is not addressed and is not
    reported; one whose address is unknown, a strap that resolves to nothing or
    a conflict nobody has resolved, is undecided, naming why.

    Addresses are compared by overlap, not by equality. Two equal scalars clash
    and fail. Two overlapping intervals that are not one scalar, such as a range
    beside an address inside it, may or may not clash, so the pair is undecided.
    The rule passes only when every address is known and no two overlap.
    """
    from .graph import CheckResult

    results = []
    nets: dict[str, frozenset[str]] | None = None
    known: list[tuple[tuple[Decimal, Decimal], str, Value]] = []
    unresolved = False
    for port in sorted(ports, key=lambda p: p.id):
        if port.address_strap is not None and nets is None:
            nets = _nets_by_pin(entities)
        value = _resolve_address(entities, port, nets or {})
        if value is None:
            continue
        interval = _interval(value)
        if interval is None:
            unresolved = True
            reason = f": {value.rationale}" if value.rationale else ""
            results.append(undecided("addressing", ["address"], f"on {port.id}{reason}"))
            continue
        known.append((interval, port.id, value))
    known.sort(key=lambda held: (held[0], held[1]))

    scalars: dict[Decimal, list[tuple[str, Value]]] = {}
    for (low, high), port_id, value in known:
        if low == high:
            scalars.setdefault(low, []).append((port_id, value))
    clashes = False
    for address, holders in sorted(scalars.items()):
        if len(holders) > 1:
            clashes = True
            results.append(
                CheckResult(
                    "interface_compatibility",
                    CheckStatus.FAIL,
                    subject,
                    message=(
                        f"address {_address_text((address, address))} is claimed by "
                        f"more than one participant: {', '.join(sorted(p for p, _ in holders))}"
                    ),
                    evidence=_cited(entities, (v for _, v in holders)),
                )
            )

    overlaps = False
    for index, (left, left_port, _) in enumerate(known):
        for right, right_port, _ in known[index + 1:]:
            if left[0] == left[1] == right[0] == right[1]:
                continue                    # one scalar: a clash, reported above
            if left[0] <= right[1] and right[0] <= left[1]:
                overlaps = True
                results.append(
                    undecided(
                        "addressing",
                        ["address"],
                        f"{_address_text(left)} ({left_port}) overlaps "
                        f"{_address_text(right)} ({right_port}), so whether they "
                        "clash depends on which address each answers on",
                    )
                )

    if known and not clashes and not overlaps and not unresolved:
        held = ", ".join(
            f"{_address_text(interval)} ({port_id})" for interval, port_id, _ in known
        )
        results.append(
            CheckResult(
                "interface_compatibility",
                CheckStatus.PASS,
                subject,
                message=f"addresses on {link.interface.name} are distinct: {held}",
                evidence=_cited(entities, (v for _, _, v in known)),
            )
        )
    return results


def _cited(entities: Mapping[str, Entity], values) -> tuple[str, ...]:
    """The evidence entities behind some addresses. A strap-resolved address
    names the pin that selected it as its source, which is not evidence."""
    return tuple(
        source
        for source in _evidence(*values)
        if isinstance(entities.get(source), Evidence)
    )


def _address_text(interval: tuple[Decimal, Decimal]) -> str:
    """An address as a datasheet writes it: 0x44, not 68, and 0x48..0x4B for a
    range."""

    def one(value: Decimal) -> str:
        if value == value.to_integral_value() and value >= 0:
            return f"0x{int(value):02X}"
        return str(value)

    low, high = interval
    return one(low) if low == high else f"{one(low)}..{one(high)}"


def _nets_by_pin(entities: Mapping[str, Entity]) -> dict[str, frozenset[str]]:
    """Each pin's net, as the set of pins sharing it, from the inferred netlist."""
    from .netlist import infer_nets

    nets: dict[str, frozenset[str]] = {}
    for members in infer_nets(entities):
        net = frozenset(members)
        for pin in members:
            nets[pin] = net
    return nets


def _pin_label(entities: Mapping[str, Entity], pin_id: str) -> str:
    pin = entities.get(pin_id)
    name = pin.vendor_name if isinstance(pin, Pin) and pin.vendor_name else "?"
    return f"{name} ({pin_id})"


def resolve_address(snapshot, port: Port) -> Value | None:
    """The address a bus device's port answers on, read from the board.

    A fixed `address` parameter is returned as it is recorded. A conflicting one
    gives the value its resolution chose or, while unresolved, an unknown value
    whose reason names the candidates' sources. A strap is resolved from the
    inferred nets: the one pin of its strap map that shares the strap pin's net
    selects the address, returned as an inferred value whose source is that
    pin. A strap pin on no net, on a net no pin of its map shares, or on a net
    two of them share, gives an unknown value whose reason names the strap pin,
    and both pins when two share it. A port with neither a fixed address nor a
    strap is not addressed, and gives None.

    `snapshot` is a snapshot or its entity mapping.
    """
    entities = getattr(snapshot, "entities", snapshot)
    nets = _nets_by_pin(entities) if port.address_strap is not None else {}
    return _resolve_address(entities, port, nets)


def _resolve_address(
    entities: Mapping[str, Entity], port: Port, nets: Mapping[str, frozenset[str]]
) -> Value | None:
    fixed = port.parameters.get("address")
    if isinstance(fixed, Value):
        return fixed
    if isinstance(fixed, ConflictingValue):
        # Competing evidence is an address not yet known, never no address: the
        # port is still addressed, and dropping it would let the rule pass.
        if fixed.resolved:
            return fixed.chosen
        return Value.unknown(
            "the address has conflicting candidates from "
            + " and ".join(sorted(candidate.source for candidate in fixed.candidates))
            + ", and no decision has chosen one"
        )
    strap = port.address_strap
    if strap is None:
        return None

    pin = strap["pin"]
    by_pin = strap["by_pin"]
    net = nets.get(pin, frozenset({pin}))
    label = _pin_label(entities, pin)
    if len(net) < 2:
        return Value.unknown(f"the address strap pin {label} is on no net")
    sharing = sorted(
        candidate for candidate in by_pin if candidate in net and candidate != pin
    )
    if not sharing:
        return Value.unknown(
            f"the address strap pin {label} shares a net with none of "
            + ", ".join(_pin_label(entities, candidate) for candidate in sorted(by_pin))
        )
    if len(sharing) > 1:
        return Value.unknown(
            f"the address strap pin {label} shares a net with "
            + " and ".join(_pin_label(entities, candidate) for candidate in sharing)
            + ", so it selects no one address"
        )
    # Read off the graph rather than stated, so inferred; nothing about the
    # reading is uncertain once the nets are known, so its confidence is whole.
    selected = sharing[0]
    return Value.inferred(
        Quantity.scalar(by_pin[selected], "1"), source=selected, confidence="1"
    )


def compatibility_check(snapshot):
    """The compatibility check class, over every link in the graph."""
    results = []
    for link in find_links(snapshot.entities):
        results.extend(check_link(link, snapshot.entities))
    return results


def compatibility_scope(snapshot) -> set[str]:
    """What the compatibility check covers: every link's connection and its
    participants, and whatever decides the net of a participant's strap pin.

    The addressing rule reads a strapped address off the net the strap pin is
    on, so re-tying that pin, or removing a connection on its net, changes an
    address without touching any port. For a participant with a strap, the
    scope therefore holds the strap pin, the pins its map names, and every pin,
    conductive connection and stated net on the strap pin's net; otherwise a
    duplicate address could reach the head with the rule never run.
    """
    from .entities import Net
    from .topology import CONDUCTIVE_KINDS

    entities = snapshot.entities
    scope: set[str] = set()
    strapped: list[Port] = []
    for link in find_links(entities):
        scope.add(link.connection)
        scope.update(link.participants)
        strapped.extend(
            port
            for port in (entities.get(pid) for pid in link.participants)
            if isinstance(port, Port) and port.address_strap is not None
        )
    if not strapped:
        return scope

    nets = _nets_by_pin(entities)
    on_strap_nets: set[str] = set()
    for port in strapped:
        pin = port.address_strap["pin"]
        scope.add(pin)
        scope.update(port.address_strap["by_pin"])
        on_strap_nets.update(nets.get(pin, frozenset({pin})))
    scope.update(on_strap_nets)
    for entity in entities.values():
        if isinstance(entity, Connection):
            if entity.connection_kind in CONDUCTIVE_KINDS and (
                entity.source in on_strap_nets or entity.target in on_strap_nets
            ):
                scope.add(entity.id)
        elif isinstance(entity, Net) and on_strap_nets.intersection(entity.members):
            scope.add(entity.id)
    return scope
