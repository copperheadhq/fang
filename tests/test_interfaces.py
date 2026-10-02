"""Spec: The Shipped Interface Catalogue; The Pin Model; A Port May Be One
Peripheral Instance."""

import pytest

from fang.diagnostics import FangError
from fang.entities import ConnectionKind
from fang.interfaces import (
    AF,
    CATALOGUE,
    I2C,
    SPI,
    UART,
    I2CPort,
    InterfaceCatalogue,
    InterfacePort,
    InterfaceType,
    Pin,
    PinMap,
    Selector,
    SignalSpec,
    default_catalogue,
)
from fang.lang import Part, V, kOhm

#: Every interface the spec requires the catalogue to cover.
REQUIRED = (
    "i2c", "spi", "uart", "usb2", "can", "rs485", "pwm", "quadrature_encoder",
    "power_input", "power_output", "analog_input", "analog_output",
    "motor_phase", "jtag", "swd", "clock", "reset",
)


def test_every_named_interface_is_present():
    catalogue = default_catalogue()
    missing = [name for name in REQUIRED if name not in catalogue]
    assert missing == []


def test_every_interface_carries_at_least_one_required_signal_with_a_role():
    for name in REQUIRED:
        interface = CATALOGUE.get(name)
        assert interface.required_signals, name
        for signal in interface.signals:
            assert signal.role, f"{name}.{signal.name}"


def test_interface_membership_matches_the_protocol():
    assert I2C.required_signals == ("scl", "sda")
    assert set(SPI.required_signals) == {"sck", "mosi", "miso", "cs"}
    assert UART.required_signals == ("tx", "rx")
    assert [s.name for s in UART.signals if not s.required] == ["rts", "cts"]


def test_a_bus_is_marked_multi_drop_and_an_open_drain_bus_needs_a_pull_up():
    assert I2C.multi_drop and I2C.requires_pull_up
    assert CATALOGUE.get("can").multi_drop
    assert not SPI.multi_drop


def test_power_interfaces_carry_power_connection_kind():
    assert CATALOGUE.get("power_output").connection_kind is ConnectionKind.POWER
    assert CATALOGUE.get("motor_phase").connection_kind is ConnectionKind.POWER


def test_a_project_defines_its_own_interface():
    catalogue = default_catalogue()
    custom = InterfaceType(
        "onewire", (SignalSpec("dq", "data", "bidirectional"),), requires_pull_up=True
    )
    catalogue.register(custom)
    assert "onewire" in catalogue
    assert catalogue.get("onewire").required_signals == ("dq",)


def test_an_unregistered_interface_is_refused():
    with pytest.raises(FangError):
        InterfaceCatalogue().get("nothing")


def test_an_invalid_role_is_refused():
    with pytest.raises(ValueError):
        SignalSpec("x", "not-a-role")
    with pytest.raises(ValueError):
        Pin("PB8", role="not-a-role")


# -- the pin model ---------------------------------------------------------


def test_a_pin_preserves_its_vendor_name_alongside_its_role():
    pin = Pin("PB8", role="clock", number="42")
    assert pin.name == "PB8"
    assert pin.role == "clock"
    assert pin.number == "42"


def test_a_signal_may_name_several_candidate_pins():
    mapping = PinMap({"i2c.scl": ["PB8", "PB6"], "i2c.sda": "PB9"})
    assert mapping.candidates("i2c", "scl") == ("PB8", "PB6")
    assert mapping.candidates("i2c", "sda") == ("PB9",)
    assert mapping.candidates("i2c", "absent") == ()


def test_a_pin_map_entry_names_a_port_and_a_signal():
    with pytest.raises(ValueError):
        PinMap({"scl": ["PB8"]})


def test_a_part_declares_pins_surfaces_and_a_pin_map_separately():
    class MCU(Part):
        i2c = InterfacePort(I2C)
        PB8 = Pin("PB8", role="clock")
        PB9 = Pin("PB9", role="data")
        pinmap = PinMap({"i2c.scl": "PB8", "i2c.sda": "PB9"})

    mcu = MCU()
    assert sorted(mcu.pins()) == ["PB8", "PB9"]
    assert sorted(mcu.surfaces()) == ["i2c"]
    assert mcu.children() == {}
    assert mcu.pin_map.candidates("i2c", "scl") == ("PB8",)


def test_two_instances_do_not_share_pins():
    class MCU(Part):
        PB8 = Pin("PB8", role="clock")

    assert MCU().PB8 is not MCU().PB8


def test_an_interface_port_reports_its_type_and_signals():
    port = InterfacePort(I2C, voh_min=2.4 * V)
    assert port.surface_type == "i2c"
    assert port.signals == ("scl", "sda")
    assert port.connection_kind is ConnectionKind.SIGNAL
    assert port.parameter_values["voh_min"] is not None


# -- peripheral instances, selectors and straps ----------------------------


def test_the_new_interface_codes_are_allocated_in_their_own_area():
    from fang.diagnostics import (
        IFACE_SELECTOR_WITHOUT_EVIDENCE,
        IFACE_STRAP_UNKNOWN_PIN,
        REGISTRY,
    )

    codes = [code.code for code in REGISTRY if code.area == "IFACE"]
    assert codes == ["IFACE-0001", "IFACE-0002", "IFACE-0003", "IFACE-0004"]
    assert IFACE_SELECTOR_WITHOUT_EVIDENCE == "IFACE-0003"
    assert IFACE_STRAP_UNKNOWN_PIN == "IFACE-0004"
    # Allocating a code again for another condition is refused, so neither
    # number can have been taken from an existing one.
    with pytest.raises(ValueError):
        REGISTRY.allocate("IFACE-0003", "something else")


def test_a_port_names_its_instance_and_the_instance_is_not_a_parameter():
    port = I2CPort(peripheral="I2C1", voltage=3.3 * V)
    assert port.peripheral == "I2C1"
    assert "peripheral" not in port.parameter_values
    assert I2CPort().peripheral is None
    with pytest.raises(ValueError):
        I2CPort(peripheral="")


def test_an_alternate_function_is_a_selector():
    assert AF(4) == Selector("AF4")
    assert str(AF(7)) == "AF7"
    for bad in (-1, True, "4"):
        with pytest.raises(ValueError):
            AF(bad)
    with pytest.raises(ValueError):
        Selector("")


def test_both_pin_map_forms_give_the_same_candidates_in_the_same_order():
    listed = PinMap({"i2c1.scl": ["PB8", "PB6"], "i2c1.sda": ["PB9", "PB7"]})
    routed = PinMap(
        {
            "i2c1.scl": {"PB8": AF(4), "PB6": AF(4)},
            "i2c1.sda": {"PB9": AF(4), "PB7": AF(4)},
        },
        evidence="af_table",
    )
    for signal in ("scl", "sda"):
        assert routed.candidates("i2c1", signal) == listed.candidates("i2c1", signal)
    assert routed.as_dict() == listed.as_dict()
    assert routed.selector("i2c1", "scl", "PB6") == "AF4"
    assert listed.selector("i2c1", "scl", "PB6") is None
    assert routed.evidence == "af_table" and listed.evidence is None


def test_a_selector_is_written_as_one():
    with pytest.raises(ValueError, match="Selector"):
        PinMap({"i2c1.scl": {"PB8": "AF4"}}, evidence="af_table")


def test_a_candidate_in_the_mapping_form_may_carry_no_selector():
    mapping = PinMap({"i2c1.scl": {"PB8": AF(4), "PB6": None}}, evidence="af_table")
    assert mapping.candidates("i2c1", "scl") == ("PB8", "PB6")
    assert mapping.selector("i2c1", "scl", "PB6") is None
