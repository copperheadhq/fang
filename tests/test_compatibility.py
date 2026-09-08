"""Spec: Interface Compatibility Checks; Interface Compatibility Evaluation."""

import pytest

from fang.constraints import CheckStatus
from fang.compatibility import compatibility_check, find_links
from fang.elaborate import elaborate
from fang.interfaces import I2CPort, Pin, PinMap, PowerIn, PowerOut, SPIPort
from fang.lang import Part, System, A, V, kHz, kOhm, mA
from fang.units import Quantity
from fang.values import Value

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
