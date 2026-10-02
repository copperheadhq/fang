"""Spec: Interface Compatibility Checks; Interface Compatibility Evaluation;
An Addressed Bus Device Carries Its Address."""

from decimal import Decimal

import pytest

from fang.constraints import CheckStatus
from fang.compatibility import compatibility_check, find_links, resolve_address
from fang.elaborate import elaborate
from fang.entities import Port
from fang.identity import derive
from fang.interfaces import I2CPort, Pin, PinMap, PowerIn, PowerOut, SPIPort, Strap
from fang.lang import Electrical, Part, System, A, Ohm, UnitLiteral, V, kHz, kOhm, mA
from fang.parts import Resistor, Transistor
from fang.units import Quantity
from fang.values import Value, ValueStatus

PROJECT = "PRJ-COMPAT"


def statuses(results, rule=None):
    return [
        r.status for r in results if rule is None or rule in r.message
    ]


def build(system):
    result = elaborate(system, project_id=PROJECT)
    assert result.ok, [d.message for d in result.diagnostics]
    return compatibility_check(result.snapshot)


def test_a_healthy_link_passes():
    class Source(Part):
        spi = SPIPort(voh_min=3.0 * V, vol_max=0.4 * V, voltage=3.3 * V)

    class Sink(Part):
        spi = SPIPort(vih_min=2.0 * V, vil_max=0.8 * V, voltage=3.3 * V)

    class Link(System):
        a = Source()
        b = Sink()

        def architecture(self):
            self.a.spi >> self.b.spi

    results = build(Link)
    assert results
    assert all(r.status is CheckStatus.PASS for r in results)


def test_a_logic_level_shortfall_fails_and_names_both_parameters():
    class Weak(Part):
        spi = SPIPort(voh_min=1.8 * V, voltage=3.3 * V)

    class Sink(Part):
        spi = SPIPort(vih_min=2.0 * V, voltage=3.3 * V)

    class Link(System):
        a = Weak()
        b = Sink()

        def architecture(self):
            self.a.spi >> self.b.spi

    results = build(Link)
    failures = [r for r in results if r.status is CheckStatus.FAIL]
    assert failures
    assert "voh_min" in failures[0].message and "vih_min" in failures[0].message


def test_an_unknown_input_returns_undecided_naming_what_is_missing():
    class Source(Part):
        spi = SPIPort(voh_min=3.0 * V)

    class Sink(Part):
        spi = SPIPort()          # vih_min is never declared

    class Link(System):
        a = Source()
        b = Sink()

        def architecture(self):
            self.a.spi >> self.b.spi

    results = build(Link)
    undecided = [r for r in results if r.status is CheckStatus.UNKNOWN]
    assert undecided
    assert "vih_min" in undecided[0].missing
    # It does not pass by default.
    assert CheckStatus.PASS not in {r.status for r in results}


def test_current_capability_is_checked_against_demand():
    class Supply(Part):
        rail = PowerOut(voltage=3.3 * V, current_capability=500 * mA)

    class Load(Part):
        rail = PowerIn(voltage=3.3 * V, current_demand=800 * mA)

    class Link(System):
        a = Supply()
        b = Load()

        def architecture(self):
            self.a.rail >> self.b.rail

    results = build(Link)
    failures = [r for r in results if r.status is CheckStatus.FAIL]
    assert any("below demand" in r.message for r in failures)


def test_sufficient_current_passes():
    class Supply(Part):
        rail = PowerOut(voltage=3.3 * V, current_capability=2 * A)

    class Load(Part):
        rail = PowerIn(voltage=3.3 * V, current_demand=800 * mA)

    class Link(System):
        a = Supply()
        b = Load()

        def architecture(self):
            self.a.rail >> self.b.rail

    results = build(Link)
    assert any(
        r.status is CheckStatus.PASS and "capability covers demand" in r.message
        for r in results
    )


def test_a_voltage_domain_mismatch_is_reported_and_names_the_participant():
    class Source(Part):
        spi = SPIPort(voltage=5 * V, voh_min=4.5 * V)

    class Sink(Part):
        spi = SPIPort(voltage=3.3 * V, vih_min=2.0 * V)

    class Link(System):
        a = Source()
        b = Sink()

        def architecture(self):
            self.a.spi >> self.b.spi

    results = build(Link)
    domain = [r for r in results if "voltage domain" in r.message]
    assert domain and domain[0].status is CheckStatus.FAIL
    assert "PORT-" in domain[0].message


def test_a_bus_checks_every_participant():
    class Node(Part):
        i2c = I2CPort(voltage=3.3 * V, pull_up_resistance=4.7 * kOhm, pull_up_supply=3.3 * V)

    class Odd(Part):
        i2c = I2CPort(voltage=1.8 * V, pull_up_resistance=4.7 * kOhm, pull_up_supply=1.8 * V)

    class Bus(System):
        a = Node()
        b = Node()
        c = Odd()

        def architecture(self):
            self.a.i2c >> self.b.i2c
            self.b.i2c >> self.c.i2c

    results = build(Bus)
    links = [r for r in results if "voltage domain" in r.message]
    assert any(r.status is CheckStatus.FAIL for r in links)


def test_an_open_drain_bus_without_a_pull_up_fails():
    class Node(Part):
        i2c = I2CPort(voltage=3.3 * V)

    class Bus(System):
        a = Node()
        b = Node()

        def architecture(self):
            self.a.i2c >> self.b.i2c

    results = build(Bus)
    assert any(
        r.status is CheckStatus.FAIL and "no participant declares a pull-up" in r.message
        for r in results
    )


def test_a_pull_up_from_the_wrong_rail_fails():
    class Node(Part):
        i2c = I2CPort(voltage=3.3 * V, pull_up_resistance=4.7 * kOhm, pull_up_supply=5 * V)

    class Bus(System):
        a = Node()
        b = Node()

        def architecture(self):
            self.a.i2c >> self.b.i2c

    results = build(Bus)
    assert any(
        r.status is CheckStatus.FAIL and "pull-up" in r.message for r in results
    )


def test_incompatible_bit_rates_fail():
    class Fast(Part):
        i2c = I2CPort(voltage=3.3 * V, bit_rate=400 * kHz,
                      pull_up_resistance=4.7 * kOhm, pull_up_supply=3.3 * V)

    class Slow(Part):
        i2c = I2CPort(voltage=3.3 * V, bit_rate=100 * kHz,
                      pull_up_resistance=4.7 * kOhm, pull_up_supply=3.3 * V)

    class Bus(System):
        a = Fast()
        b = Slow()

        def architecture(self):
            self.a.i2c >> self.b.i2c

    results = build(Bus)
    assert any("bit rate" in r.message and r.status is CheckStatus.FAIL for r in results)


def test_a_datasheet_sourced_input_cites_its_evidence():
    class Source(Part):
        spi = SPIPort(
            voh_min=Value.inferred(Quantity.scalar("3.0", "V"), "EVD-DS-1", "0.9"),
            voltage=3.3 * V,
        )

    class Sink(Part):
        spi = SPIPort(vih_min=2.0 * V, voltage=3.3 * V)

    class Link(System):
        a = Source()
        b = Sink()

        def architecture(self):
            self.a.spi >> self.b.spi

    results = build(Link)
    assert any("EVD-DS-1" in r.evidence for r in results)


def test_a_bus_merges_its_participants_into_one_link():
    class Node(Part):
        i2c = I2CPort(voltage=3.3 * V, pull_up_resistance=4.7 * kOhm, pull_up_supply=3.3 * V)

    class Bus(System):
        a = Node()
        b = Node()
        c = Node()

        def architecture(self):
            self.a.i2c >> self.b.i2c
            self.b.i2c >> self.c.i2c

    result = elaborate(Bus, project_id=PROJECT)
    links = find_links(result.snapshot.entities)
    assert len(links) == 1
    assert len(links[0].participants) == 3


# -- what a link is, and is not --------------------------------------------


def test_a_pad_in_the_path_is_not_asked_what_it_thinks_of_the_bus():
    """A resistor declares no logic levels, so it is not undecided about them.

    A check over a fact one side was never supposed to carry is not a finding;
    it is noise that reads like one.
    """

    class Source(Part):
        spi = SPIPort(voh_min=3.0 * V, vol_max=0.4 * V, voltage=3.3 * V)

    class Series(System):
        a = Source()
        r = Resistor(resistance=33 * Ohm)

        def architecture(self):
            self.a.spi.sck >> self.r.p1

    assert build(Series) == []


def test_a_series_part_joins_the_two_interfaces_it_stands_between():
    """The two ends of the link are compared with each other, not with the part."""

    class Source(Part):
        spi = SPIPort(voh_min=3.0 * V, vol_max=0.4 * V, voltage=3.3 * V)

    class Sink(Part):
        spi = SPIPort(vih_min=2.0 * V, vil_max=0.8 * V, voltage=3.3 * V)

    class Series(System):
        a = Source()
        b = Sink()
        r = Resistor(resistance=33 * Ohm)

        def architecture(self):
            self.a.spi.sck >> self.r.p1
            self.r.p2 >> self.b.spi.sck

    result = elaborate(Series, project_id=PROJECT)
    ends = {
        frozenset(link.participants)
        for link in find_links(result.snapshot.entities)
        if link.interface.name == "spi"
    }
    ports = {
        e.id
        for e in result.snapshot.entities.values()
        if e.kind == "port" and e.identity.display_name == "spi"
    }
    assert frozenset(ports) in ends
    assert any(r.status is CheckStatus.PASS for r in build(Series))


def test_a_series_part_carries_a_mismatch_between_the_ends_through():
    class Source(Part):
        spi = SPIPort(voh_min=4.5 * V, vol_max=0.4 * V, voltage=5 * V)

    class Sink(Part):
        spi = SPIPort(vih_min=2.0 * V, vil_max=0.8 * V, voltage=3.3 * V)

    class Series(System):
        a = Source()
        b = Sink()
        r = Resistor(resistance=33 * Ohm)

        def architecture(self):
            self.a.spi.sck >> self.r.p1
            self.r.p2 >> self.b.spi.sck

    domain = [r for r in build(Series) if "voltage domain" in r.message]
    assert domain and domain[0].status is CheckStatus.FAIL


def test_a_part_that_declares_no_bridge_ends_the_link():
    """A transistor is a switch, so the interface does not continue through it.

    Two pads of one part are joined only where the part says they are; a shared
    pad is a different matter, and joins whatever lands on it.
    """

    class Source(Part):
        spi = SPIPort(voh_min=3.0 * V, vol_max=0.4 * V, voltage=3.3 * V)

    class Sink(Part):
        spi = SPIPort(vih_min=2.0 * V, vil_max=0.8 * V, voltage=3.3 * V)

    class Switched(System):
        a = Source()
        b = Sink()
        q = Transistor(vds_max=20 * V)

        def architecture(self):
            self.a.spi.sck >> self.q.drain
            self.q.source >> self.b.spi.sck

    result = elaborate(Switched, project_id=PROJECT)
    assert Transistor.bridges == ()
    spi_ports = {
        e.id
        for e in result.snapshot.entities.values()
        if e.kind == "port" and e.identity.display_name == "spi"
    }
    assert not [
        link
        for link in find_links(result.snapshot.entities)
        if set(link.participants) == spi_ports
    ]


def test_a_part_records_what_it_bridges():
    """The graph carries the fact, because a component's body is not a connection."""

    class Board(System):
        r = Resistor(resistance=33 * Ohm)

    result = elaborate(Board, project_id=PROJECT)
    component = next(
        e for e in result.snapshot.entities.values() if e.kind == "component"
    )
    assert component.extensions["bridges"] == [["p1", "p2"]]


def test_compatibility_is_a_check_class_the_gate_can_require():
    from fang.checks import COMPATIBILITY_CHECK, DEFAULT_CHECKS

    class Node(Part):
        i2c = I2CPort(voltage=3.3 * V)

    class Bus(System):
        a = Node()
        b = Node()

        def architecture(self):
            self.a.i2c >> self.b.i2c

    result = elaborate(Bus, project_id=PROJECT)
    assert COMPATIBILITY_CHECK in DEFAULT_CHECKS
    assert COMPATIBILITY_CHECK.scope(result.snapshot)
    assert COMPATIBILITY_CHECK.run(result.snapshot)


def test_a_failing_compatibility_check_blocks_the_commit_gate():
    from fang.checks import DEFAULT_CHECKS
    from fang.graph import AddEntity, KernelGraph, Transaction

    class Node(Part):
        i2c = I2CPort(voltage=3.3 * V)      # open-drain with no pull-up

    class Bus(System):
        a = Node()
        b = Node()

        def architecture(self):
            self.a.i2c >> self.b.i2c

    result = elaborate(Bus, project_id=PROJECT)
    graph = KernelGraph(
        result.snapshot.with_entities({}, "REV-000000"), checks=DEFAULT_CHECKS
    )
    operations = tuple(
        AddEntity(entity=e, reason="elaborated")
        for e in sorted(result.snapshot.entities.values(), key=lambda x: x.id)
    )
    proposal = graph.propose(Transaction(graph.head.hash, operations))
    assert proposal.rejected
    assert any(d.code == "TXN-0002" for d in proposal.diagnostics)
    assert len(graph.head) == 0


# -- addressing: an addressed bus device carries its address ----------------

#: Dimensionless, for an address: a count, not a measure.
addr = UnitLiteral("1")

#: Where each address lands when the strap is tied to one of the device's own
#: pins, in the shape a temperature sensor's datasheet gives it.
STRAP = {"GND": 0x48 * addr, "VDD": 0x49 * addr, "SDA": 0x4A * addr, "SCL": 0x4B * addr}


class Host(Part):
    """A bus controller. Its port declares no address: it is not addressed."""

    power = PowerIn(voltage=3.3 * V)
    i2c = I2CPort(voltage=3.3 * V, pull_up_resistance=4.7 * kOhm, pull_up_supply=3.3 * V)
    VDD = Pin("VDD", role="power")
    VSS = Pin("VSS", role="ground")
    SCL = Pin("SCL", role="clock")
    SDA = Pin("SDA", role="data")
    pinmap = PinMap({"power.vcc": "VDD", "power.gnd": "VSS", "i2c.scl": "SCL", "i2c.sda": "SDA"})


class Fixed48(Part):
    power = PowerIn(voltage=3.3 * V)
    i2c = I2CPort(address=0x48 * addr, voltage=3.3 * V)
    VDD = Pin("VDD", role="power")
    GND = Pin("GND", role="ground")
    SCL = Pin("SCL", role="clock")
    SDA = Pin("SDA", role="data")
    pinmap = PinMap({"power.vcc": "VDD", "power.gnd": "GND", "i2c.scl": "SCL", "i2c.sda": "SDA"})


class Strapped(Part):
    """A device whose address is set by where its ADDR pin is tied."""

    power = PowerIn(voltage=3.3 * V)
    i2c = I2CPort(address=Strap("ADDR", STRAP), voltage=3.3 * V)
    strap = Electrical()
    VDD = Pin("VDD", role="power")
    GND = Pin("GND", role="ground")
    SCL = Pin("SCL", role="clock")
    SDA = Pin("SDA", role="data")
    ADDR = Pin("ADDR", role="control")
    pinmap = PinMap(
        {
            "power.vcc": "VDD",
            "power.gnd": "GND",
            "i2c.scl": "SCL",
            "i2c.sda": "SDA",
            "strap.line": "ADDR",
        }
    )


class Rail(Part):
    dc = PowerOut(voltage=3.3 * V, current_capability=500 * mA)
    VCC = Pin("VCC", role="power")
    GND = Pin("GND", role="ground")
    pinmap = PinMap({"dc.vcc": "VCC", "dc.gnd": "GND"})


class Pad(Part):
    """A test pad, on a net none of the strapped device's own pins is on."""

    pad = Electrical()
    P1 = Pin("1", role="unknown")
    pinmap = PinMap({"pad.line": "1"})


def strapped_bus(tie, *, second=None):
    """A host, a strapped device, and optionally a second device, on one bus,
    with a pad beside them.

    `tie` wires the strap pin, given the system; returning without wiring it
    leaves the strap on no net.
    """

    class Bus(System):
        rail = Rail()
        host = Host()
        device = Strapped()
        pad = Pad()
        if second is not None:
            other = second()

        def architecture(self):
            self.rail.dc >> self.host.power
            devices = [self.device] + ([self.other] if second is not None else [])
            for device in devices:
                self.rail.dc >> device.power
                self.host.i2c >> device.i2c
            tie(self)

    return Bus


def addressing(results):
    return [r for r in results if "address" in r.message]


def snapshot_of(system):
    result = elaborate(system, project_id=PROJECT)
    assert result.ok, [d.message for d in result.diagnostics]
    return result.snapshot


def port_at(snapshot, path):
    return next(
        e for e in snapshot.entities.values()
        if isinstance(e, Port) and str(e.identity.path) == path
    )


def pin_at(snapshot, path):
    return derive(PROJECT, "pin", path).id


def test_a_fixed_address_elaborates_to_an_explicit_dimensionless_value():
    class One(System):
        device = Fixed48()

    port = port_at(snapshot_of(One), "system.device.i2c")
    value = port.parameters["address"]
    assert value.status is ValueStatus.EXPLICIT
    assert value.quantity.dimension == Quantity.scalar("1", "1").dimension
    assert value.quantity.interval() == (Decimal(0x48), Decimal(0x48))


def test_an_address_is_not_a_bare_number():
    class Bare(Part):
        i2c = I2CPort(address=0x44)

    class One(System):
        device = Bare()

    result = elaborate(One, project_id=PROJECT)
    assert not result.ok and result.snapshot is None
    assert result.diagnostics[0].code == "UNIT-0001"
    assert "address" in result.diagnostics[0].message


def test_a_strap_is_stored_with_its_pins_resolved():
    class One(System):
        device = Strapped()

    snapshot = snapshot_of(One)
    port = port_at(snapshot, "system.device.i2c")
    assert "address" not in port.parameters
    pins = {name: pin_at(snapshot, f"system.device.{name}") for name in STRAP}
    assert port.address_strap == {
        "pin": pin_at(snapshot, "system.device.ADDR"),
        "by_pin": {pins["GND"]: "72", pins["VDD"]: "73", pins["SDA"]: "74", pins["SCL"]: "75"},
    }
    assert port.as_dict()["address_strap"]["pin"] == pin_at(snapshot, "system.device.ADDR")
    assert set(port.references()) >= set(pins.values())


def test_a_strap_naming_a_pin_the_part_does_not_have_is_refused():
    class Typo(Part):
        i2c = I2CPort(address=Strap("ADR", {"GND": 0x48 * addr}))
        GND = Pin("GND", role="ground")
        ADDR = Pin("ADDR", role="control")

    class One(System):
        device = Typo()

    result = elaborate(One, project_id=PROJECT)
    assert not result.ok
    assert result.diagnostics[0].code == "IFACE-0004"
    assert "'ADR'" in result.diagnostics[0].message
    assert "Typo" in result.diagnostics[0].message


@pytest.mark.parametrize(
    "tie, expected",
    [
        (lambda s: s.device.strap >> s.rail.dc.gnd, 0x48),    # ground
        (lambda s: s.device.strap >> s.rail.dc.vcc, 0x49),    # its own supply
        (lambda s: s.device.strap >> s.host.i2c.sda, 0x4A),   # a bus signal
        (lambda s: s.device.strap >> s.host.i2c.scl, 0x4B),
    ],
    ids=["ground", "supply", "sda", "scl"],
)
def test_a_strap_resolves_to_the_address_its_net_selects(tie, expected):
    snapshot = snapshot_of(strapped_bus(tie))
    value = resolve_address(snapshot, port_at(snapshot, "system.device.i2c"))
    assert value.status is ValueStatus.INFERRED
    assert value.quantity.interval() == (Decimal(expected), Decimal(expected))
    # The source is the device's own pin that selected the address.
    assert snapshot.entities[value.source].owner == port_at(snapshot, "system.device.i2c").owner


def test_a_floating_strap_is_unknown_and_names_the_pin():
    snapshot = snapshot_of(strapped_bus(lambda s: None))
    value = resolve_address(snapshot, port_at(snapshot, "system.device.i2c"))
    assert not value.known
    assert pin_at(snapshot, "system.device.ADDR") in value.rationale
    assert "no net" in value.rationale


def test_a_strap_on_a_net_none_of_its_pins_shares_is_unknown():
    snapshot = snapshot_of(strapped_bus(lambda s: s.device.strap >> s.pad.pad))
    value = resolve_address(snapshot, port_at(snapshot, "system.device.i2c"))
    assert not value.known
    assert "none of" in value.rationale
    assert pin_at(snapshot, "system.device.ADDR") in value.rationale


def test_a_strap_is_resolved_by_net_not_by_whose_pin_it_was_wired_to():
    # Wired to the host's supply pin, which shares the rail with the device's
    # own VDD: the net is what selects, so the address is VDD's.
    snapshot = snapshot_of(strapped_bus(lambda s: s.device.strap >> s.host.power.vcc))
    value = resolve_address(snapshot, port_at(snapshot, "system.device.i2c"))
    assert value.quantity.interval() == (Decimal(0x49), Decimal(0x49))


def short_to_both_bus_signals(s):
    s.device.strap >> s.host.i2c.sda
    s.device.strap >> s.host.i2c.scl


def test_an_ambiguous_strap_is_unknown_and_names_both_pins():
    snapshot = snapshot_of(strapped_bus(short_to_both_bus_signals))
    value = resolve_address(snapshot, port_at(snapshot, "system.device.i2c"))
    assert not value.known
    for name in ("ADDR", "SDA", "SCL"):
        assert pin_at(snapshot, f"system.device.{name}") in value.rationale


def test_a_port_with_no_address_is_not_addressed():
    class One(System):
        host = Host()

    snapshot = snapshot_of(One)
    assert resolve_address(snapshot, port_at(snapshot, "system.host.i2c")) is None


def test_two_devices_at_one_address_fail_naming_both():
    class Bus(System):
        host = Host()
        first = Fixed48()
        second = Fixed48()

        def architecture(self):
            self.host.i2c >> self.first.i2c
            self.host.i2c >> self.second.i2c

    snapshot = snapshot_of(Bus)
    failures = [r for r in addressing(compatibility_check(snapshot)) if r.status is CheckStatus.FAIL]
    assert len(failures) == 1
    assert "0x48" in failures[0].message
    for path in ("system.first.i2c", "system.second.i2c"):
        assert port_at(snapshot, path).id in failures[0].message


def test_a_strap_tied_to_ground_is_compared_like_a_fixed_address():
    tie = lambda s: s.device.strap >> s.rail.dc.gnd           # noqa: E731
    snapshot = snapshot_of(strapped_bus(tie, second=Fixed48))
    failures = [r for r in addressing(compatibility_check(snapshot)) if r.status is CheckStatus.FAIL]
    assert len(failures) == 1
    assert port_at(snapshot, "system.device.i2c").id in failures[0].message
    assert port_at(snapshot, "system.other.i2c").id in failures[0].message

    tie = lambda s: s.device.strap >> s.rail.dc.vcc           # noqa: E731
    results = addressing(compatibility_check(snapshot_of(strapped_bus(tie, second=Fixed48))))
    assert [r.status for r in results] == [CheckStatus.PASS]
    assert "0x48" in results[0].message and "0x49" in results[0].message


@pytest.mark.parametrize(
    "tie, named",
    [
        (lambda s: None, ("ADDR",)),
        (short_to_both_bus_signals, ("ADDR", "SDA", "SCL")),
    ],
    ids=["floating", "ambiguous"],
)
def test_an_unresolved_strap_leaves_the_rule_undecided_naming_the_pins(tie, named):
    snapshot = snapshot_of(strapped_bus(tie, second=Fixed48))
    results = addressing(compatibility_check(snapshot))
    assert [r.status for r in results] == [CheckStatus.UNKNOWN]
    assert "address" in results[0].missing
    for name in named:
        assert pin_at(snapshot, f"system.device.{name}") in results[0].message


def test_a_controller_with_no_address_is_not_reported():
    class Bus(System):
        host = Host()
        device = Fixed48()

        def architecture(self):
            self.host.i2c >> self.device.i2c

    snapshot = snapshot_of(Bus)
    results = addressing(compatibility_check(snapshot))
    host = port_at(snapshot, "system.host.i2c").id
    # The rule is decided over the one device that is addressed.
    assert [r.status for r in results] == [CheckStatus.PASS]
    assert not any(host in r.message for r in results)


# -- the gate brings the addressing rule in when a strap's net changes --------


def strap_connection(snapshot):
    addr_pin = pin_at(snapshot, "system.device.ADDR")
    return next(
        e for e in snapshot.entities.values()
        if e.kind == "connection" and addr_pin in (e.source, e.target)
    )


def test_retying_a_strap_onto_a_taken_address_is_rejected_by_the_gate():
    import dataclasses

    from fang.checks import DEFAULT_CHECKS
    from fang.graph import Connect, KernelGraph, Transaction

    # Tied to its own supply the strap selects 0x49, clear of the other 0x48.
    snapshot = snapshot_of(strapped_bus(lambda s: s.device.strap >> s.rail.dc.vcc, second=Fixed48))
    assert [r.status for r in addressing(compatibility_check(snapshot))] == [CheckStatus.PASS]

    # Moving the same connection to ground selects 0x48: a duplicate.
    old = strap_connection(snapshot)
    retied = dataclasses.replace(
        old, source=pin_at(snapshot, "system.device.ADDR"), target=pin_at(snapshot, "system.device.GND")
    )
    graph = KernelGraph(snapshot, checks=DEFAULT_CHECKS)
    proposal = graph.propose(Transaction(snapshot.hash, (Connect(connection=retied),)))
    assert proposal.rejected
    assert any(r.check == "interface_compatibility" for r in proposal.checks)
    assert any(
        d.code == "TXN-0002" and "0x48" in d.message for d in proposal.diagnostics
    )
    assert graph.head is snapshot


def test_removing_a_strap_connection_runs_the_addressing_rule():
    from fang.checks import DEFAULT_CHECKS
    from fang.graph import KernelGraph, RemoveEntity, Transaction

    snapshot = snapshot_of(strapped_bus(lambda s: s.device.strap >> s.rail.dc.vcc, second=Fixed48))
    graph = KernelGraph(snapshot, checks=DEFAULT_CHECKS)
    proposal = graph.propose(
        Transaction(snapshot.hash, (RemoveEntity(target=strap_connection(snapshot).id),))
    )
    # The strap is left on no net: the rule is run and is undecided, naming the
    # pin. Whether that blocks is the policy's decision, not the scope's.
    results = addressing(proposal.checks)
    assert [r.status for r in results] == [CheckStatus.UNKNOWN]
    assert pin_at(snapshot, "system.device.ADDR") in results[0].message


def test_the_compatibility_scope_holds_what_decides_a_strap_pin_net():
    from fang.compatibility import compatibility_scope

    snapshot = snapshot_of(strapped_bus(lambda s: s.device.strap >> s.rail.dc.vcc, second=Fixed48))
    scope = compatibility_scope(snapshot)
    assert strap_connection(snapshot).id in scope
    for name in ("ADDR", "GND", "VDD", "SDA", "SCL"):
        assert pin_at(snapshot, f"system.device.{name}") in scope
    # The rail's own pin is on the strap's net, so a connection to it is too.
    assert pin_at(snapshot, "system.rail.VCC") in scope
