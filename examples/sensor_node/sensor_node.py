"""An STM32F401RE reading an HS3001 over I2C1, with a console on USART2.

It records two facts the other examples cannot state: which of the
microcontroller's controllers a port is, with the alternate function that
routes each signal to its pin, and the address the sensor answers on. Both
decide whether the firmware meets a working bus, and both are read off the
vendors' datasheets and cited, never inferred from a pin's name.

The MCU is reduced to the pins this board uses. Three of its four VDD/VSS
pairs and their capacitors, the 4.7 uF bulk capacitor, VCAP_1, VDDA, VBAT,
NRST and BOOT0 are left out, so this is a board for the checks and for running
firmware against, not one to send to fabrication.
"""

from fang.emulation import (
    Absent,
    At,
    Count,
    EmulationModel,
    Emulates,
    Firmware,
    FirstAt,
    I2CRead,
    PinConfig,
    Rises,
    UartValue,
)
from fang.interfaces import AF, I2CPort, Pin, PinMap, PowerIn, PowerOut, UARTPort
from fang.lang import (
    Electrical,
    Ground,
    Ohm,
    Parameter,
    Part,
    Signal,
    System,
    UnitLiteral,
    V,
    degC,
    kHz,
    kOhm,
    ms,
    nF,
    require,
    s,
)
from fang.parts import LED, DecouplingCapacitor, Resistor
from fang.rationale import Cites, Requires

#: Dimensionless, for a bus address: a count, not a measure.
addr = UnitLiteral("1")
#: Dimensionless, for events counted in an emulated run.
count = UnitLiteral("1")

#: The two datasheets every number below was read from.
ST = "SRC-DS-STM32F401"            # ST DS10086, STM32F401xD/xE, Rev 5
RENESAS = "SRC-DS-HS3XXX"          # Renesas R36DS0045EU0101, HS3xxx, Rev 1.01


class STM32F401RE(Part):
    """The STM32F401RE in LQFP64, with I2C1 and USART2 as named instances.

    I2C1 can reach PB8/PB9 or PB6/PB7, both at AF4; the pair is a recorded
    decision, PB8/PB9 preferred. USART2 is PA2/PA3 at AF7. Each port names its
    instance, so a connection to `i2c1` cannot land on I2C2's pins, and each
    candidate carries the selector the firmware has to write.
    """

    designator_prefix = "U"

    power = PowerIn(voltage=3.3 * V)
    # Levels at VDD = 3.3 V: VIH 0.7 VDD and VIL 0.3 VDD for an FT pin; VOL
    # 0.4 V and VOH VDD - 0.4 V for a CMOS output at 8 mA. Fast mode is the
    # most the I2C controller supports.
    i2c1 = I2CPort(
        peripheral="I2C1",
        voltage=3.3 * V,
        vih_min=2.31 * V,
        vil_max=0.99 * V,
        vol_max=0.4 * V,
        bit_rate=400 * kHz,
    )
    usart2 = UARTPort(
        peripheral="USART2",
        voltage=3.3 * V,
        voh_min=2.9 * V,
        vol_max=0.4 * V,
        vih_min=2.31 * V,
        vil_max=0.99 * V,
    )
    status = Signal()

    # Vendor names and LQFP64 pad numbers, kept apart: the pad number is the
    # package's, and nothing derives a port pin from it.
    VDD = Pin("VDD", role="power", number="64")
    VSS = Pin("VSS", role="ground", number="63")
    PA2 = Pin("PA2", role="data", number="16")
    PA3 = Pin("PA3", role="data", number="17")
    PA5 = Pin("PA5", role="data", number="21")
    PB6 = Pin("PB6", role="clock", number="58")
    PB7 = Pin("PB7", role="data", number="59")
    PB8 = Pin("PB8", role="clock", number="61")
    PB9 = Pin("PB9", role="data", number="62")

    pinout = Cites(
        "LQFP64 pins: PA2 16, PA3 17, PA5 21, PB6 58, PB7 59, PB8 61, PB9 62, "
        "VSS 63, VDD 64; PA2, PA3, PA5 and PB6 to PB9 are 5 V tolerant (FT) I/O",
        document=ST,
        locator="DS10086 Rev 5, table 8 (pin definitions), pp. 38-44; "
        "figure 12 (LQFP64 pinout), p. 35",
    )
    af_table = Cites(
        "I2C1_SCL is AF4 on PB6 and PB8, I2C1_SDA is AF4 on PB7 and PB9; "
        "USART2_TX is AF7 on PA2 and USART2_RX is AF7 on PA3",
        document=ST,
        locator="DS10086 Rev 5, table 9 (alternate function mapping), pp. 45-46",
    )
    io_levels = Cites(
        "FT I/O, 1.7 V <= VDD <= 3.6 V: VIL max 0.3 VDD, VIH min 0.7 VDD. "
        "CMOS port at IIO = 8 mA, 2.7 V <= VDD <= 3.6 V: VOL max 0.4 V, "
        "VOH min VDD - 0.4 V",
        document=ST,
        locator="DS10086 Rev 5, table 54 (I/O static characteristics), p. 91; "
        "table 55 (output voltage characteristics), p. 94",
    )
    i2c_rate = Cites(
        "The I2C interface supports standard mode, up to 100 kHz, and fast "
        "mode, up to 400 kHz",
        document=ST,
        locator="DS10086 Rev 5, section 6.3.19 (I2C interface characteristics), p. 98",
    )
    part_number = Cites(
        "STM32F401RET6 is 64 pins (R), 512 Kbytes of Flash (E), LQFP (T), "
        "-40 to 85 C (6)",
        document=ST,
        locator="DS10086 Rev 5, table 87 (ordering information scheme), p. 132; "
        "table 88 (device order codes), p. 133",
    )

    pinmap = PinMap(
        {"power.vcc": "VDD", "power.gnd": "VSS", "status.line": "PA5"},
        evidence="pinout",
    )
    # Candidates in preference order, each with the alternate function that
    # routes the signal to it. The lowering picks one pair and records why.
    peripherals = PinMap(
        {
            "i2c1.scl": {"PB8": AF(4), "PB6": AF(4)},
            "i2c1.sda": {"PB9": AF(4), "PB7": AF(4)},
            "usart2.tx": {"PA2": AF(7)},
            "usart2.rx": {"PA3": AF(7)},
        },
        evidence="af_table",
    )


class HS3001(Part):
    """Renesas's HS3001 humidity and temperature sensor, at its fixed address.

    The datasheet states no input or output logic levels for SCL and SDA, so
    none is written here, and the logic-level check over the bus is undecided
    rather than passed on a number nobody read.
    """

    designator_prefix = "U"

    power = PowerIn(voltage=3.3 * V)
    # 0x44 is the only address the part answers on; there is no strap pin.
    # The pull-ups to VDD are the ones its application circuit requires.
    i2c = I2CPort(
        address=0x44 * addr,
        voltage=3.3 * V,
        bit_rate=400 * kHz,
        pull_up_resistance=2.2 * kOhm,
        pull_up_supply=3.3 * V,
    )
    vc = Electrical()

    SCL = Pin("SCL", role="clock", number="1")
    SDA = Pin("SDA", role="data", number="2")
    VC = Pin("VC", role="unknown", number="3")
    VDD = Pin("VDD", role="power", number="4")
    # Do not connect: declared so the pinout is whole, and left unconnected.
    NC = Pin("NC", role="unknown", number="5")
    VSS = Pin("VSS", role="ground", number="6")

    fixed_address = Cites(
        "The HS3xxx series I2C address is 0x44, and the device responds only "
        "to this 7-bit address; a custom address is available on request",
        document=RENESAS,
        locator="R36DS0045EU0101 Rev 1.01, section 7.2 (sensor slave address), p. 10",
    )
    pinout = Cites(
        "6-LGA, 3.0 x 2.41 mm: 1 SCL, 2 SDA, 3 VC (0.1 uF to ground), 4 VDD, "
        "5 NC (do not connect), 6 VSS",
        document=RENESAS,
        locator="R36DS0045EU0101 Rev 1.01, section 1.2 and figure 1 "
        "(pin assignments), p. 4",
    )
    application = Cites(
        "Pull-up resistors to VDD are required on SCL and SDA, 2.2 kOhm typical; "
        "0.1 uF from VC to ground and 0.1 uF from VDD to ground",
        document=RENESAS,
        locator="R36DS0045EU0101 Rev 1.01, section 6, figure 13 "
        "(application circuit), p. 9; section 7, p. 10",
    )
    i2c_rate = Cites(
        "SCL clock frequency up to 400 kHz",
        document=RENESAS,
        locator="R36DS0045EU0101 Rev 1.01, table 1 (I2C timing parameters), p. 10",
    )

    pinmap = PinMap(
        {
            "power.vcc": "VDD",
            "power.gnd": "VSS",
            "i2c.scl": "SCL",
            "i2c.sda": "SDA",
            "vc.line": "VC",
        },
        evidence="pinout",
    )


class PowerHeader(Part):
    """Where the 3.3 V rail arrives. What supplies it is not this board's."""

    designator_prefix = "J"

    dc = PowerOut(voltage=3.3 * V)

    VCC = Pin("VCC", role="power", number="1")
    GND = Pin("GND", role="ground", number="2")

    pinmap = PinMap({"dc.vcc": "VCC", "dc.gnd": "GND"})


class ConsoleHeader(Part):
    """Where USART2 leaves the board, for a 3.3 V serial adapter.

    A connector passes the board's signals through, so its pins carry the
    board's names: TXD is what the MCU transmits, and the adapter's cable
    crosses it. The levels on the far side are the adapter's, and not known.
    """

    designator_prefix = "J"

    uart = UARTPort(voltage=3.3 * V)
    ground = Ground()

    TXD = Pin("TXD", role="data", number="1")
    RXD = Pin("RXD", role="data", number="2")
    GND = Pin("GND", role="ground", number="3")

    pinmap = PinMap({"uart.tx": "TXD", "uart.rx": "RXD", "ground.gnd": "GND"})


class SensorNode(System):
    """A sensor on I2C1, a console on USART2 and a status LED on PA5.

    The firmware in `firmware/` is run against this board in Renode, and two
    questions are asked of it: whether it reads the sensor, reports what it
    read and shows a good reading on the LED, and whether it keeps running
    and shows the fault when the sensor is missing. Each is a requirement the
    board is verified against, by emulation, through the commit gate.
    """

    sensor_ready = Requires(
        "Within 200 ms of reset the firmware reads the HS3001, reports the "
        "temperature it read on the console, and blinks the status LED slowly "
        "while readings succeed",
        validation="emulation",
    )
    survives_missing_sensor = Requires(
        "With the HS3001 missing the firmware keeps running and blinks the "
        "status LED fast, and makes no read",
        validation="emulation",
    )

    first_read = Parameter("s", description="when the firmware first reads the sensor")
    reported = Parameter("degC", description="the temperature the firmware prints")
    slow_blinks = Parameter("", description="status LED rises between 1 s and 2 s, sensor present")
    mux_mismatches = Parameter("", description="I2C1 pins configured otherwise than the board requires")
    fast_blinks = Parameter("", description="status LED rises between 1 s and 2 s, sensor missing")
    missing_reads = Parameter("", description="reads of the sensor while it is missing")

    # The sensor is at 25 degC from reset. The pull-ups, the LED's resistor and
    # the console header share nets with the pins the question touches and
    # carry no emulation model, so they are named as abstracted.
    startup = Emulates(
        "sensor_ready",
        run_until=2 * s,
        stimuli=[At(0 * ms, "env.temperature", 25 * degC)],
        measures={
            "first_read": FirstAt(I2CRead("env")),
            "reported": UartValue("mcu.usart2", prefix="temp=", unit=degC),
            "slow_blinks": Count(Rises("mcu.status"), within=(1 * s, 2 * s)),
            "mux_mismatches": PinConfig("mcu.i2c1"),
        },
        abstracted=("scl_pullup", "sda_pullup", "series", "console"),
    )
    sensor_missing = Emulates(
        "survives_missing_sensor",
        run_until=2 * s,
        faults=[Absent("env")],
        measures={
            "fast_blinks": Count(Rises("mcu.status"), within=(1 * s, 2 * s)),
            "missing_reads": Count(I2CRead("env")),
        },
        abstracted=("scl_pullup", "sda_pullup", "series"),
    )

    decoupling = Cites(
        "Each VDD/VSS pair is decoupled with ceramic capacitors close to the "
        "pins; the scheme shows 6 x 100 nF and 1 x 4.7 uF across the VDD pins",
        document=ST,
        locator="DS10086 Rev 5, figure 18 (power supply scheme), section 6.1.6, p. 57",
    )

    header = PowerHeader(package="PinHeader_1x02_P2.54mm")
    mcu = STM32F401RE(package="LQFP-64")
    env = HS3001(package="LGA-6")
    console = ConsoleHeader(package="PinHeader_1x03_P2.54mm")

    # 2.2k to VDD, as the sensor's application circuit draws them.
    scl_pullup = Resistor(resistance=2.2 * kOhm, package="R_0402")
    sda_pullup = Resistor(resistance=2.2 * kOhm, package="R_0402")

    # The one MCU supply pair this board models, decoupled at its pins.
    bypass = DecouplingCapacitor(capacitance=100 * nF, package="C_0402")
    # The sensor's two, from its application circuit.
    env_bypass = DecouplingCapacitor(capacitance=100 * nF, package="C_0402")
    vc_bypass = DecouplingCapacitor(capacitance=100 * nF, package="C_0402")

    series = Resistor(resistance=1 * kOhm, package="R_0402")
    indicator = LED(package="LED_0603")

    def __init__(self, **overrides):
        super().__init__(**overrides)
        # The selection lands on the instance, not the class template.
        self.mcu.select("STMicroelectronics", "STM32F401RET6", datasheet=ST)
        self.env.select("Renesas", "HS3001", datasheet=RENESAS)
        # What the emulator runs: fang's F401 platform model, the firmware
        # beside this program, and Renode's own HS3001 model.
        self.mcu.add_trait(EmulationModel(source="fang:stm32f401re"))
        self.mcu.add_trait(Firmware("firmware/elf/sensor_node.elf", target="stm32f401re"))
        self.env.add_trait(EmulationModel(source="renode:Sensors.HS3001"))

    def architecture(self):
        self.header.dc >> self.mcu.power
        self.header.dc >> self.env.power

        # One connection, one controller: every signal comes from i2c1's
        # candidates, and the pin connections carry AF4.
        self.mcu.i2c1 >> self.env.i2c
        self.header.dc.vcc >> self.scl_pullup.p1
        self.scl_pullup.p2 >> self.mcu.i2c1.scl
        self.header.dc.vcc >> self.sda_pullup.p1
        self.sda_pullup.p2 >> self.mcu.i2c1.sda

        # The header passes USART2 through; PA2 and PA3 carry AF7.
        self.mcu.usart2 >> self.console.uart
        self.header.dc.gnd >> self.console.ground

        self.mcu.status >> self.series.p1
        self.series.p2 >> self.indicator.p1
        self.indicator.p2 >> self.header.dc.gnd

        self.mcu.power.vcc >> self.bypass.p1
        self.mcu.power.gnd >> self.bypass.p2
        self.env.power.vcc >> self.env_bypass.p1
        self.env.power.gnd >> self.env_bypass.p2
        self.env.vc >> self.vc_bypass.p1
        self.env.power.gnd >> self.vc_bypass.p2

    def constraints(self):
        # 3.3 V / 8 mA: whatever the LED drops, PA5 never sources more than the
        # current its output levels are specified at.
        require(self.series.resistance >= 412.5 * Ohm)

        # What the firmware has to do, decided by emulation. 0.05 degC allows
        # the sensor's 14-bit quantization: 25 degC reads back as 25.01.
        require(self.first_read <= 200 * ms)
        require(self.reported >= 24.95 * degC)
        require(self.reported <= 25.05 * degC)
        require(self.slow_blinks == 1 * count)
        require(self.mux_mismatches == 0 * count)
        require(self.fast_blinks >= 4 * count)
        require(self.missing_reads == 0 * count)
