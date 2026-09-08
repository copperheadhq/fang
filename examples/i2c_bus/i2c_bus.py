"""One controller and three targets on a shared I2C bus.

A bus is a multi-drop interface, so the same port is connected several times and
the lowering resolves it into one net per signal. Two things the graph keeps that
a netlist cannot: the addresses are parameters, so "no two devices answer to the
same address" is a constraint the kernel decides rather than a rule in a linter;
and the RTC's logic thresholds are recorded as an assumption rather than as
numbers, which leaves the check over that link undecided instead of passed.
"""

from fang.interfaces import I2CPort, Pin, PinMap, PowerIn, PowerOut
from fang.lang import (
    Parameter,
    Part,
    System,
    UnitLiteral,
    V,
    kHz,
    kOhm,
    mA,
    require,
    uA,
    uF,
)
from fang.parts import Capacitor, Resistor
from fang.rationale import Assumes, Cites, Requires

#: Dimensionless, for the things on a board that are counts rather than measures.
addr = UnitLiteral("1")


class Target(Part):
    """What every device on this bus has in common: a rail, a bus, an address."""

    designator_prefix = "U"

    address = Parameter("", description="7-bit I2C address")

    power = PowerIn(voltage=3.3 * V)
    i2c = I2CPort(voltage=3.3 * V, bit_rate=400 * kHz)

    VDD = Pin("VDD", role="power", number="1")
    GND = Pin("GND", role="ground", number="2")
    SCL = Pin("SCL", role="clock", number="3")
    SDA = Pin("SDA", role="data", number="4")

    pinmap = PinMap(
        {"power.vcc": "VDD", "power.gnd": "GND", "i2c.scl": "SCL", "i2c.sda": "SDA"}
    )


class TempSensor(Target):
    power = PowerIn(voltage=3.3 * V, current_demand=1 * mA)
    # On an open-drain bus the high level is the pull-up's, not the device's;
    # what the device owes the bus is vol_max, and what it needs is vih_min.
    i2c = I2CPort(
        voh_min=2.9 * V,
        vol_max=0.4 * V,
        vih_min=2.1 * V,
        vil_max=0.8 * V,
        voltage=3.3 * V,
        bit_rate=400 * kHz,
    )

    thresholds = Cites(
        "VIH is 0.7 x VDD and VIL is 0.3 x VDD",
        document="SRC-DS-TMP102",
        locator="table 7.5, electrical characteristics",
    )


class EEPROM(Target):
    power = PowerIn(voltage=3.3 * V, current_demand=5 * mA)
    i2c = I2CPort(
        voh_min=2.9 * V,
        vol_max=0.4 * V,
        vih_min=2.0 * V,
        vil_max=0.8 * V,
        voltage=3.3 * V,
        bit_rate=400 * kHz,
    )

    thresholds = Cites(
        "VIH is 2.0 V minimum over the 1.7-5.5 V supply range",
        document="SRC-DS-24AA02",
        locator="table 1-2, DC characteristics",
    )


class RTC(Target):
    """The part nobody has read the datasheet for yet.

    Its thresholds are absent rather than guessed, so the compatibility check
    over its bus link is undecided. That is the honest answer, and it is the one
    that gets someone to open the datasheet.
    """

    power = PowerIn(voltage=3.3 * V, current_demand=100 * uA)

    thresholds = Assumes(
        "The RTC accepts 3.3 V CMOS levels",
        rationale="every part in this family does; not yet read off the datasheet",
    )


class Controller(Part):
    designator_prefix = "U"

    power = PowerIn(voltage=3.3 * V, current_demand=40 * mA)
    i2c = I2CPort(
        voh_min=2.9 * V,
        vol_max=0.4 * V,
        vih_min=2.0 * V,
        vil_max=0.9 * V,
        voltage=3.3 * V,
        bit_rate=400 * kHz,
        pull_up_resistance=2.2 * kOhm,
        pull_up_supply=3.3 * V,
    )

    VDD = Pin("VDD", role="power", number="1")
    VSS = Pin("VSS", role="ground", number="2")
    PB6 = Pin("PB6", role="clock", number="58")
    PB7 = Pin("PB7", role="data", number="59")

    pinmap = PinMap(
        {"power.vcc": "VDD", "power.gnd": "VSS", "i2c.scl": "PB6", "i2c.sda": "PB7"}
    )


class PowerHeader(Part):
    """Where the 3V3 rail arrives, so the rail is a net and not a promise."""

    designator_prefix = "J"

    dc = PowerOut(voltage=3.3 * V, current_capability=500 * mA)

    VCC = Pin("VCC", role="power", number="1")
    GND = Pin("GND", role="ground", number="2")

    pinmap = PinMap({"dc.vcc": "VCC", "dc.gnd": "GND"})


class SensorBus(System):
    supply = PowerIn(voltage=3.3 * V, current_capability=500 * mA)

    unique_addresses = Requires(
        "No two devices on the bus answer to the same address",
        validation="analysis",
    )

    header = PowerHeader(package="PinHeader_1x02_P2.54mm")
    controller = Controller(package="LQFP-64")
    temperature = TempSensor(address=0x48 * addr, package="SOT-563")
    memory = EEPROM(address=0x50 * addr, package="SOT-23-5")
    clock = RTC(address=0x68 * addr, package="SOIC-8")

    # 2.2k at 400 kHz: the bus is short and the capacitance is low, so the
    # smaller of the two usual values wins the rise-time argument.
    scl_pullup = Resistor(resistance=2.2 * kOhm, package="R_0402")
    sda_pullup = Resistor(resistance=2.2 * kOhm, package="R_0402")
    bulk = Capacitor(capacitance=1 * uF, voltage_rating=16 * V, package="C_0603")

    def architecture(self):
        self.supply >> self.header.dc
        for device in (self.controller, self.temperature, self.memory, self.clock):
            self.header.dc >> device.power

        # One port connected three times: the bus is multi-drop, so this is a
        # bus with four members and not three point-to-point links.
        self.controller.i2c >> self.temperature.i2c
        self.controller.i2c >> self.memory.i2c
        self.controller.i2c >> self.clock.i2c

        self.header.dc.vcc >> self.scl_pullup.p1
        self.scl_pullup.p2 >> self.controller.i2c.scl
        self.header.dc.vcc >> self.sda_pullup.p1
        self.sda_pullup.p2 >> self.controller.i2c.sda

        self.header.dc.vcc >> self.bulk.p1
        self.header.dc.gnd >> self.bulk.p2

    def constraints(self):
        # Address uniqueness, written in the language rather than built into a
        # checker: an address is a parameter, so this is a constraint like any
        # other and it is decided the same way.
        require(self.temperature.address != self.memory.address)
        require(self.temperature.address != self.clock.address)
        require(self.memory.address != self.clock.address)

        # Open-drain: the pull-up sets the rise time and the sink current both.
        require(self.scl_pullup.resistance <= 4.7 * kOhm)
        require(self.scl_pullup.resistance >= 1 * kOhm)
        require(self.sda_pullup.resistance <= 4.7 * kOhm)
        require(self.sda_pullup.resistance >= 1 * kOhm)
