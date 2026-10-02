"""Spec: Deterministic Pin Assignment; A Pin Choice Is A Recorded Decision;
An Incomplete Lowering Fails Explicitly; A Port May Be One Peripheral
Instance."""

import pytest

from fang.diagnostics import FangError
from fang.elaborate import elaborate
from fang.entities import Connection, Decision, Evidence, Pin as PinEntity, Port as PortEntity
from fang.identity import derive
from fang.interfaces import AF, I2CPort, Pin, PinMap, SPIPort, UARTPort
from fang.lang import Part, System, V, kOhm
from fang.rationale import Assumes, Cites
from fang.serialization import canonical_bytes

PROJECT = "PRJ-LOWER"


class MCU(Part):
    i2c = I2CPort(voh_min=2.4 * V)
    PB8 = Pin("PB8", role="clock")
    PB6 = Pin("PB6", role="clock")
    PB9 = Pin("PB9", role="data")
    PB7 = Pin("PB7", role="data")
    pinmap = PinMap({"i2c.scl": ["PB8", "PB6"], "i2c.sda": ["PB9", "PB7"]})


class IMU(Part):
    i2c = I2CPort(vih_min=2.0 * V)
    SCL = Pin("SCL", role="clock")
    SDA = Pin("SDA", role="data")
    pinmap = PinMap({"i2c.scl": "SCL", "i2c.sda": "SDA"})


class Board(System):
    mcu = MCU()
    imu = IMU()

    def architecture(self):
        self.mcu.i2c >> self.imu.i2c


def lowered(result):
    return [
        e
        for e in result.snapshot.entities.values()
        if isinstance(e, Connection) and e.derived_from_interface
    ]


def pin_names(result):
    return {
        e.id: e.vendor_name
        for e in result.snapshot.entities.values()
        if isinstance(e, PinEntity)
    }


def test_an_interface_connection_lowers_to_pin_connections():
    result = elaborate(Board, project_id=PROJECT)
    assert result.ok
    names = pin_names(result)
    pairs = {(names[c.source], names[c.target]) for c in lowered(result)}
    assert pairs == {("PB8", "SCL"), ("PB9", "SDA")}


def test_the_same_graph_lowers_identically_every_time():
    first = elaborate(Board, project_id=PROJECT)
    second = elaborate(Board, project_id=PROJECT)
    assert canonical_bytes(first.snapshot.as_dict()) == canonical_bytes(
        second.snapshot.as_dict()
    )


def test_a_lowered_connection_names_the_interface_connection_it_came_from():
    result = elaborate(Board, project_id=PROJECT)
    interface_connections = {
        e.id
        for e in result.snapshot.entities.values()
        if isinstance(e, Connection) and not e.derived_from_interface
    }
    for connection in lowered(result):
        assert connection.derived_from_interface in interface_connections
        recorded = connection.provenance.records[0]
        assert connection.derived_from_interface in recorded.derived_from


def test_a_pin_choice_becomes_a_decision_naming_the_rejected_alternatives():
    result = elaborate(Board, project_id=PROJECT)
    names = pin_names(result)
    decisions = [
        e for e in result.snapshot.entities.values() if isinstance(e, Decision)
    ]
    # The MCU offered two candidates per signal; the IMU offered one.
    assert len(decisions) == 2
    chosen = {names[d.choice] for d in decisions}
    assert chosen == {"PB8", "PB9"}
    rejected = {a["pin"] for d in decisions for a in d.alternatives_rejected}
    assert rejected == {"PB6", "PB7"}
    for decision in decisions:
        assert decision.rationale


def test_a_single_candidate_is_not_a_decision():
    class OnlyOne(Part):
        i2c = I2CPort()
        SCL = Pin("SCL", role="clock")
        SDA = Pin("SDA", role="data")
        pinmap = PinMap({"i2c.scl": "SCL", "i2c.sda": "SDA"})

    class Pair(System):
        a = OnlyOne()
        b = OnlyOne()

        def architecture(self):
            self.a.i2c >> self.b.i2c

    result = elaborate(Pair, project_id=PROJECT)
    assert result.ok
    assert not [e for e in result.snapshot.entities.values() if isinstance(e, Decision)]


def test_one_pin_does_not_carry_two_signals():
    class Overlapping(Part):
        i2c = I2CPort()
        PA0 = Pin("PA0", role="clock")
        PA1 = Pin("PA1", role="data")
        # Both signals name PA0 first; only one can have it.
        pinmap = PinMap({"i2c.scl": ["PA0", "PA1"], "i2c.sda": ["PA0", "PA1"]})

    class Pair(System):
        a = Overlapping()
        b = Overlapping()

        def architecture(self):
            self.a.i2c >> self.b.i2c

    result = elaborate(Pair, project_id=PROJECT)
    assert result.ok
    names = pin_names(result)
    assigned = [names[c.source] for c in lowered(result)]
    assert sorted(assigned) == ["PA0", "PA1"]


def test_a_required_signal_with_no_pin_fails_the_lowering():
    class Incomplete(Part):
        i2c = I2CPort()
        SCL = Pin("SCL", role="clock")
        pinmap = PinMap({"i2c.scl": "SCL"})   # sda has no pin

    class Pair(System):
        a = Incomplete()
        b = IMU()

        def architecture(self):
            self.a.i2c >> self.b.i2c

    result = elaborate(Pair, project_id=PROJECT)
    assert not result.ok
    assert result.snapshot is None                    # no partial mapping
    assert result.diagnostics[0].code == "IFACE-0001"
    assert "sda" in result.diagnostics[0].message


def test_exhausted_candidates_fail_rather_than_partially_mapping():
    class TooFew(Part):
        i2c = I2CPort()
        PA0 = Pin("PA0", role="clock")
        pinmap = PinMap({"i2c.scl": ["PA0"], "i2c.sda": ["PA0"]})

    class Pair(System):
        a = TooFew()
        b = IMU()

        def architecture(self):
            self.a.i2c >> self.b.i2c

    result = elaborate(Pair, project_id=PROJECT)
    assert not result.ok
    assert result.snapshot is None
    assert result.diagnostics[0].code == "IFACE-0001"
    assert "already assigned" in result.diagnostics[0].message


def test_interfaces_disagreeing_on_membership_fail_the_lowering():
    from fang.interfaces import I2C, SPI
    from fang.lowering import check_membership

    class A(Part):
        port = I2CPort()

    class B(Part):
        port = SPIPort()

    a, b = A(), B()
    a.port.attribute = b.port.attribute = "port"
    with pytest.raises(FangError) as caught:
        check_membership(a.port, b.port)
    assert caught.value.diagnostic.code == "IFACE-0002"


def test_an_optional_signal_absent_on_one_side_is_simply_not_lowered():
    class Talker(Part):
        uart = UARTPort()
        TX = Pin("TX", role="data")
        RX = Pin("RX", role="data")
        RTS = Pin("RTS", role="control")
        pinmap = PinMap({"uart.tx": "TX", "uart.rx": "RX", "uart.rts": "RTS"})

    class Listener(Part):
        uart = UARTPort()
        TX = Pin("TX", role="data")
        RX = Pin("RX", role="data")
        pinmap = PinMap({"uart.tx": "TX", "uart.rx": "RX"})

    class Link(System):
        a = Talker()
        b = Listener()

        def architecture(self):
            self.a.uart >> self.b.uart

    result = elaborate(Link, project_id=PROJECT)
    assert result.ok
    # Only the two required signals lowered; rts had no partner and is skipped.
    assert len(lowered(result)) == 2


def test_pins_become_entities_owned_by_their_component():
    result = elaborate(Board, project_id=PROJECT)
    pins = [e for e in result.snapshot.entities.values() if isinstance(e, PinEntity)]
    assert len(pins) == 6
    for pin in pins:
        assert pin.owner in result.snapshot.entities
        assert pin.vendor_name
        assert pin.role in ("clock", "data")


def test_an_interface_connection_without_pins_stands_on_its_own():
    """Before a part selection gives pins, the interface connection is enough."""

    class Abstract(Part):
        i2c = I2CPort()

    class Pair(System):
        a = Abstract()
        b = Abstract()

        def architecture(self):
            self.a.i2c >> self.b.i2c

    result = elaborate(Pair, project_id=PROJECT)
    assert result.ok
    assert lowered(result) == []


# -- signal-level access ---------------------------------------------------


def test_a_named_wire_reaches_a_single_pad():
    """A two-wire rail cannot land on one pad; naming the wire says which."""
    from fang.interfaces import PowerOut
    from fang.lang import V
    from fang.parts import Resistor

    class Rail(Part):
        vout = PowerOut(voltage=3.3 * V)
        VOUT = Pin("VOUT", role="power", number="1")
        GND = Pin("GND", role="ground", number="2")
        pinmap = PinMap({"vout.vcc": "VOUT", "vout.gnd": "GND"})

    class Board(System):
        rail = Rail()
        load = Resistor(resistance=10 * kOhm)

        def architecture(self):
            self.rail.vout.vcc >> self.load.p1
            self.rail.vout.gnd >> self.load.p2

    result = elaborate(Board, project_id=PROJECT)
    assert result.ok, [d.message for d in result.diagnostics]
    names = pin_names(result)
    pairs = {(names[c.source], names[c.target]) for c in lowered(result)}
    assert pairs == {("VOUT", "1"), ("GND", "2")}


def test_a_named_wire_keeps_the_nature_of_the_wire_it_is():
    from fang.entities import ConnectionKind
    from fang.interfaces import PowerOut
    from fang.lang import V
    from fang.parts import Resistor

    class Rail(Part):
        vout = PowerOut(voltage=3.3 * V)
        VOUT = Pin("VOUT", role="power", number="1")
        GND = Pin("GND", role="ground", number="2")
        pinmap = PinMap({"vout.vcc": "VOUT", "vout.gnd": "GND"})

    class Board(System):
        rail = Rail()
        load = Resistor(resistance=10 * kOhm)

        def architecture(self):
            self.rail.vout.vcc >> self.load.p1
            self.rail.vout.gnd >> self.load.p2

    result = elaborate(Board, project_id=PROJECT)
    kinds = {c.connection_kind for c in lowered(result)}
    assert kinds == {ConnectionKind.POWER, ConnectionKind.GROUND}


def test_connecting_a_whole_multi_wire_interface_to_one_pad_is_refused():
    from fang.interfaces import PowerOut
    from fang.lang import V
    from fang.parts import Resistor

    class Rail(Part):
        vout = PowerOut(voltage=3.3 * V)

    class Board(System):
        rail = Rail()
        load = Resistor(resistance=10 * kOhm)

        def architecture(self):
            self.rail.vout >> self.load.p1

    result = elaborate(Board, project_id=PROJECT)
    assert not result.ok
    assert "does not connect" in result.diagnostics[0].message


def test_naming_a_signal_the_interface_does_not_have_is_refused():
    from fang.interfaces import PowerOut

    class Rail(Part):
        vout = PowerOut()

    with pytest.raises(AttributeError, match="no signal"):
        Rail().vout.not_a_wire


# -- peripheral instances and selectors ------------------------------------


class Controller(Part):
    """Two I2C controllers, each a port, each with its own cited candidates."""

    i2c1 = I2CPort(peripheral="I2C1", voh_min=2.4 * V)
    i2c2 = I2CPort(peripheral="I2C2", voh_min=2.4 * V)
    PB8 = Pin("PB8", role="clock")
    PB6 = Pin("PB6", role="clock")
    PB9 = Pin("PB9", role="data")
    PB7 = Pin("PB7", role="data")
    PB10 = Pin("PB10", role="clock")
    PB3 = Pin("PB3", role="data")

    af_table = Cites("I2C1 and I2C2 at AF4, I2C2_SDA on PB3 at AF9", document="SRC-DS-TEST")
    pinmap = PinMap(
        {
            "i2c1.scl": {"PB8": AF(4), "PB6": AF(4)},
            "i2c1.sda": {"PB9": AF(4), "PB7": AF(4)},
            "i2c2.scl": {"PB10": AF(4)},
            "i2c2.sda": {"PB3": AF(9)},
        },
        evidence="af_table",
    )


class RoutedBoard(System):
    mcu = Controller()
    imu = IMU()

    def architecture(self):
        self.mcu.i2c1 >> self.imu.i2c


def ports(result):
    return {
        str(e.identity.path): e
        for e in result.snapshot.entities.values()
        if isinstance(e, PortEntity)
    }


def test_the_instance_is_recorded_on_the_port():
    result = elaborate(RoutedBoard, project_id=PROJECT)
    assert result.ok, [d.message for d in result.diagnostics]
    by_path = ports(result)
    assert by_path["system.mcu.i2c1"].peripheral == "I2C1"
    assert by_path["system.mcu.i2c1"].as_dict()["peripheral"] == "I2C1"
    assert "peripheral" not in by_path["system.mcu.i2c1"].parameters
    # A port that names no instance says nothing about one.
    assert by_path["system.imu.i2c"].peripheral is None
    assert "peripheral" not in by_path["system.imu.i2c"].as_dict()


def test_the_chosen_pins_selector_reaches_the_graph():
    result = elaborate(RoutedBoard, project_id=PROJECT)
    names = pin_names(result)
    evidence = derive(PROJECT, "evidence", "system.mcu.af_table").id
    assert isinstance(result.snapshot.entities[evidence], Evidence)

    by_signal = {names[c.source]: c for c in lowered(result)}
    scl = by_signal["PB8"]
    assert scl.selectors == {scl.source: {"selector": "AF4", "evidence": evidence}}
    # Only the side that declared a selector carries one: the IMU's pin has none.
    assert scl.target not in scl.selectors
    assert scl.as_dict()["selectors"] == {
        scl.source: {"evidence": evidence, "selector": "AF4"}
    }
    assert evidence in scl.references()


def test_a_selector_without_evidence_is_refused_naming_the_part():
    class Uncited(Part):
        i2c1 = I2CPort(peripheral="I2C1")
        PB8 = Pin("PB8", role="clock")
        PB9 = Pin("PB9", role="data")
        pinmap = PinMap({"i2c1.scl": {"PB8": AF(4)}, "i2c1.sda": {"PB9": AF(4)}})

    class Lonely(System):
        mcu = Uncited()

    result = elaborate(Lonely, project_id=PROJECT)
    assert not result.ok and result.snapshot is None
    assert result.diagnostics[0].code == "IFACE-0003"
    assert "Uncited" in result.diagnostics[0].message


def test_a_selector_citing_what_the_part_does_not_declare_is_refused():
    class Miscited(Part):
        i2c1 = I2CPort(peripheral="I2C1")
        PB8 = Pin("PB8", role="clock")
        PB9 = Pin("PB9", role="data")
        hunch = Assumes("I2C1 is on AF4 everywhere")
        pinmap = PinMap(
            {"i2c1.scl": {"PB8": AF(4)}, "i2c1.sda": {"PB9": AF(4)}}, evidence="af_table"
        )

    class Misnamed(Miscited):
        pinmap = PinMap(
            {"i2c1.scl": {"PB8": AF(4)}, "i2c1.sda": {"PB9": AF(4)}}, evidence="hunch"
        )

    for part, phrase in ((Miscited, "declares nothing"), (Misnamed, "not a citation")):
        class Lonely(System):
            mcu = part()

        result = elaborate(Lonely, project_id=PROJECT)
        assert not result.ok
        assert result.diagnostics[0].code == "IFACE-0003"
        assert part.__name__ in result.diagnostics[0].message
        assert phrase in result.diagnostics[0].message


def test_candidates_without_selectors_lower_exactly_as_before():
    """The list form and a mapping that routes nothing give the same bytes, and
    neither puts a selectors key on any connection."""

    class Unrouted(Part):
        i2c = I2CPort(voh_min=2.4 * V)
        PB8 = Pin("PB8", role="clock")
        PB6 = Pin("PB6", role="clock")
        PB9 = Pin("PB9", role="data")
        PB7 = Pin("PB7", role="data")
        pinmap = PinMap(
            {"i2c.scl": {"PB8": None, "PB6": None}, "i2c.sda": {"PB9": None, "PB7": None}}
        )

    class UnroutedBoard(System):
        mcu = Unrouted()
        imu = IMU()

        def architecture(self):
            self.mcu.i2c >> self.imu.i2c

    listed = elaborate(Board, project_id=PROJECT)
    mapped = elaborate(UnroutedBoard, project_id=PROJECT)
    for result in (listed, mapped):
        for connection in lowered(result):
            assert connection.selectors == {}
            assert "selectors" not in connection.as_dict()

    def shape(result):
        # Source locations differ between the two classes; the lowering does not.
        names = pin_names(result)
        return sorted(
            canonical_bytes(
                {
                    "pins": [names[c.source], names[c.target]],
                    "connection": {
                        k: v
                        for k, v in c.as_dict().items()
                        if k not in ("provenance", "source_location")
                    },
                }
            )
            for c in lowered(result)
        ) + sorted(
            canonical_bytes(
                {k: v for k, v in d.as_dict().items() if k not in ("provenance", "source_location")}
            )
            for d in result.snapshot.entities.values()
            if isinstance(d, Decision)
        )

    assert shape(listed) == shape(mapped)


def test_two_controllers_are_two_ports():
    """A connection to one controller lowers onto that controller's pins only."""

    class OnI2C2(System):
        mcu = Controller()
        imu = IMU()

        def architecture(self):
            self.mcu.i2c2 >> self.imu.i2c

    result = elaborate(OnI2C2, project_id=PROJECT)
    assert result.ok, [d.message for d in result.diagnostics]
    names = pin_names(result)
    assigned = sorted(names[c.source] for c in lowered(result))
    assert assigned == ["PB10", "PB3"]
    selectors = sorted(
        entry["selector"] for c in lowered(result) for entry in c.selectors.values()
    )
    assert selectors == ["AF4", "AF9"]

    class Both(System):
        mcu = Controller()
        near = IMU()
        far = IMU()

        def architecture(self):
            self.mcu.i2c1 >> self.near.i2c
            self.mcu.i2c2 >> self.far.i2c

    result = elaborate(Both, project_id=PROJECT)
    assert result.ok, [d.message for d in result.diagnostics]
    names = pin_names(result)
    by_bus = {}
    for connection in lowered(result):
        by_bus.setdefault(connection.derived_from_interface, set()).add(
            names[connection.source]
        )
    assert sorted(map(sorted, by_bus.values())) == [["PB10", "PB3"], ["PB8", "PB9"]]
