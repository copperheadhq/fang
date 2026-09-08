"""A regulated sensor board: a rail, an MCU, and an I2C sensor on it.

Shows the parts the toolchain is actually for: typed interfaces lowering to
pins, a decision recorded where the MCU offered a choice, and constraints that
stay undecided until someone supplies the missing datasheet number.
"""

from fang.interfaces import I2CPort, Pin, PinMap, PowerIn
from fang.lang import A, Part, System, V, kHz, kOhm, mA, require, uF
from fang.parts import Capacitor, Regulator, Resistor


class MCU(Part):
    """A microcontroller with two possible pin pairs for its I2C peripheral."""

    designator_prefix = "U"

    power = PowerIn(voltage=3.3 * V, current_demand=80 * mA)
    i2c = I2CPort(
        voh_min=2.4 * V,
        vol_max=0.4 * V,
        voltage=3.3 * V,
        bit_rate=400 * kHz,
        pull_up_resistance=4.7 * kOhm,
        pull_up_supply=3.3 * V,
    )

    VDD = Pin("VDD", role="power", number="1")
    VSS = Pin("VSS", role="ground", number="2")
    PB8 = Pin("PB8", role="clock", number="61")
    PB9 = Pin("PB9", role="data", number="62")
    PB6 = Pin("PB6", role="clock", number="58")
    PB7 = Pin("PB7", role="data", number="59")

    pinmap = PinMap(
        {
            "power.vcc": "VDD",
            "power.gnd": "VSS",
            # Two candidates each: the lowering picks one and records why.
            "i2c.scl": ["PB8", "PB6"],
            "i2c.sda": ["PB9", "PB7"],
        }
    )


class IMU(Part):
    """An inertial sensor. Its logic thresholds come from the datasheet."""

    designator_prefix = "U"

    power = PowerIn(voltage=3.3 * V, current_demand=3 * mA)
    i2c = I2CPort(vih_min=2.0 * V, vil_max=0.8 * V, voltage=3.3 * V, bit_rate=400 * kHz)

    VDD = Pin("VDD", role="power", number="1")
    GND = Pin("GND", role="ground", number="2")
    SCL = Pin("SCL", role="clock", number="3")
    SDA = Pin("SDA", role="data", number="4")

    pinmap = PinMap(
        {"power.vcc": "VDD", "power.gnd": "GND", "i2c.scl": "SCL", "i2c.sda": "SDA"}
    )


class SensorBoard(System):
    supply = PowerIn(voltage=5 * V, current_capability=1 * A)

    regulator = Regulator(
        input_voltage_max=17 * V,
        output_voltage=3.3 * V,
        output_current_max=1000 * mA,
        package="SOT-23-5",
    )
    mcu = MCU(package="LQFP-64")
    imu = IMU(package="LGA-14")

    bulk = Capacitor(capacitance=10 * uF, voltage_rating=16 * V, package="C_0805")
    scl_pullup = Resistor(resistance=4.7 * kOhm, package="R_0402")
    sda_pullup = Resistor(resistance=4.7 * kOhm, package="R_0402")

    def architecture(self):
        self.supply >> self.regulator.vin
        self.regulator.vout >> self.mcu.power
        self.regulator.vout >> self.imu.power
        self.mcu.i2c >> self.imu.i2c

        self.regulator.vout.vcc >> self.bulk.p1
        self.regulator.vout.gnd >> self.bulk.p2

        # Open drain: without these the bus never comes back up.
        self.regulator.vout.vcc >> self.scl_pullup.p1
        self.scl_pullup.p2 >> self.mcu.i2c.scl
        self.regulator.vout.vcc >> self.sda_pullup.p1
        self.sda_pullup.p2 >> self.mcu.i2c.sda

    def constraints(self):
        require(self.regulator.output_voltage == 3.3 * V)
        # The regulator must carry both loads. Stated as intent; the kernel
        # decides once every current figure is known.
        require(self.regulator.output_current_max >= 100 * mA)
