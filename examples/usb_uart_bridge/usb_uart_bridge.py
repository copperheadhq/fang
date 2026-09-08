"""A USB-to-UART bridge: the interface board on nearly every desk.

What it adds over the other examples is the part selection. The bridge and the
regulator are chosen parts — a manufacturer, an MPN, a distributor code, and the
datasheet the numbers came from — attached in `__init__` so the selection lands
on the instance and not on the class template. The logical part stays "a 3.3 V
regulator"; which one was bought is recorded separately.
"""

from fang.interfaces import Pin, PinMap, PowerIn, UARTPort, USB2Port
from fang.lang import (
    MHz,
    Ohm,
    Part,
    Signal,
    System,
    V,
    mA,
    mV,
    nF,
    pF,
    require,
    uF,
)
from fang.parts import Capacitor, Crystal, Diode, Regulator, Resistor, TestPoint
from fang.rationale import Chooses, Cites, Requires


class USBReceptacle(Part):
    """The connector. VBUS and the pair arrive together, so they are one port."""

    designator_prefix = "J"

    # The pair signals at 3.3 V; the 5 V is VBUS, which is one wire of the port
    # rather than the domain the port signals in.
    usb = USB2Port(voltage=3.3 * V, current_capability=500 * mA, bit_rate=12 * MHz)

    VBUS = Pin("VBUS", role="power", number="A4")
    DM = Pin("D-", role="differential_n", number="A7")
    DP = Pin("D+", role="differential_p", number="A6")
    GND = Pin("GND", role="ground", number="A1")

    pinmap = PinMap(
        {"usb.vbus": "VBUS", "usb.dm": "D-", "usb.dp": "D+", "usb.gnd": "GND"}
    )


class Bridge(Part):
    """The bridge IC: USB on one side, UART on the other, a crystal beneath."""

    designator_prefix = "U"

    power = PowerIn(voltage=3.3 * V, current_demand=30 * mA)
    # What the device draws from the bus, which is the number the requirement
    # about pre-enumeration current is actually about.
    usb = USB2Port(voltage=3.3 * V, bit_rate=12 * MHz, current_demand=90 * mA)
    uart = UARTPort(
        voh_min=2.8 * V,
        vol_max=0.4 * V,
        vih_min=2.0 * V,
        vil_max=0.8 * V,
        voltage=3.3 * V,
    )
    xin = Signal()
    xout = Signal()

    VDD = Pin("VDD", role="power", number="16")
    GND = Pin("GND", role="ground", number="1")
    UD_P = Pin("UD+", role="differential_p", number="6")
    UD_M = Pin("UD-", role="differential_n", number="5")
    TXD = Pin("TXD", role="data", number="2")
    RXD = Pin("RXD", role="data", number="3")
    XI = Pin("XI", role="clock", number="7")
    XO = Pin("XO", role="clock", number="8")

    pinmap = PinMap(
        {
            "power.vcc": "VDD",
            "power.gnd": "GND",
            "usb.dp": "UD+",
            "usb.dm": "UD-",
            "uart.tx": "TXD",
            "uart.rx": "RXD",
            "xin.line": "XI",
            "xout.line": "XO",
        }
    )


class Target(Part):
    """Whatever is on the other end of the UART."""

    designator_prefix = "U"

    power = PowerIn(voltage=3.3 * V, current_demand=50 * mA)
    uart = UARTPort(
        voh_min=2.9 * V,
        vol_max=0.4 * V,
        vih_min=2.0 * V,
        vil_max=0.8 * V,
        voltage=3.3 * V,
    )

    VDD = Pin("VDD", role="power", number="1")
    VSS = Pin("VSS", role="ground", number="2")
    PA9 = Pin("PA9", role="data", number="30")
    PA10 = Pin("PA10", role="data", number="31")

    pinmap = PinMap(
        {"power.vcc": "VDD", "power.gnd": "VSS", "uart.tx": "PA9", "uart.rx": "PA10"}
    )


class USBSerial(System):
    """Bus power in, 3.3 V made on the board, a serial port out."""

    bus_powered = Requires(
        "The board draws no more than 100 mA before USB enumeration",
        validation="analysis",
    )
    bridge_choice = Chooses(
        "Which USB-UART bridge?",
        selected="CH340C",
        alternatives=[
            {"part": "FT232RL", "reason": "four times the unit cost at this volume"},
            {"part": "CP2102N", "reason": "needs an external oscillator we would pay for"},
        ],
        requirements=("bus_powered",),
        rationale=(
            "integrated clock removes the crystal from the BOM on the -C variant",
            "known driver support on all three host operating systems",
        ),
    )
    dp_pullup_value = Cites(
        "A full-speed device signals its speed with 1.5k from D+ to 3.3 V",
        document="SRC-USB-2.0",
        locator="section 7.1.5.1",
    )

    connector = USBReceptacle(package="USB_C_Receptacle_16P")
    regulator = Regulator(
        input_voltage_max=6 * V,
        output_voltage=3.3 * V,
        output_current_max=300 * mA,
        dropout_voltage=250 * mV,
        package="SOT-23-5",
    )
    bridge = Bridge(package="SOP-16")
    target = Target(package="LQFP-48")

    resonator = Crystal(frequency=12 * MHz, load_capacitance=20 * pF, package="HC-49S")
    load_c1 = Capacitor(capacitance=22 * pF, voltage_rating=50 * V, package="C_0402")
    load_c2 = Capacitor(capacitance=22 * pF, voltage_rating=50 * V, package="C_0402")

    bulk_in = Capacitor(capacitance=10 * uF, voltage_rating=16 * V, package="C_0805")
    bulk_out = Capacitor(capacitance=10 * uF, voltage_rating=16 * V, package="C_0805")
    bypass = Capacitor(capacitance=100 * nF, voltage_rating=16 * V, package="C_0402")

    # Series resistors on the pair are the usual defence against a long cable's
    # reflections; 22 Ohm keeps the impedance near the pair's own.
    dp_series = Resistor(resistance=22 * Ohm, package="R_0402")
    dm_series = Resistor(resistance=22 * Ohm, package="R_0402")

    esd_dp = Diode(reverse_voltage=5 * V, forward_voltage=1 * V, package="SOD-523")
    esd_dm = Diode(reverse_voltage=5 * V, forward_voltage=1 * V, package="SOD-523")

    tx_probe = TestPoint(package="TestPoint_Pad_1.5x1.5mm")
    rx_probe = TestPoint(package="TestPoint_Pad_1.5x1.5mm")

    def __init__(self, **overrides):
        super().__init__(**overrides)
        # The selection attaches to the instance. Doing it in the class body
        # would attach it to a template that every instance re-derives from.
        self.bridge.select(
            "WCH",
            "CH340C",
            distributor_ids={"lcsc": "C84681"},
            datasheet="SRC-DS-CH340",
        )
        self.regulator.select(
            "Diodes",
            "AP2112K-3.3TRG1",
            distributor_ids={"lcsc": "C51118"},
            datasheet="SRC-DS-AP2112",
        )

    def architecture(self):
        # Bus power in, regulated down, distributed.
        self.connector.usb.vbus >> self.regulator.vin.vcc
        self.connector.usb.gnd >> self.regulator.vin.gnd
        self.regulator.vout >> self.bridge.power
        self.regulator.vout >> self.target.power

        # The pair, through its series resistors, with the clamps on the
        # connector side where the energy actually arrives.
        self.connector.usb.dp >> self.dp_series.p1
        self.dp_series.p2 >> self.bridge.usb.dp
        self.connector.usb.dm >> self.dm_series.p1
        self.dm_series.p2 >> self.bridge.usb.dm
        # Cathode on the line, anode on the return: the clamp catches the
        # negative excursion and stays out of the way of the signal.
        self.connector.usb.dp >> self.esd_dp.p2
        self.connector.usb.gnd >> self.esd_dp.p1
        self.connector.usb.dm >> self.esd_dm.p2
        self.connector.usb.gnd >> self.esd_dm.p1

        # The crystal and its load capacitors.
        self.bridge.xin >> self.resonator.p1
        self.bridge.xout >> self.resonator.p2
        self.resonator.p1 >> self.load_c1.p1
        self.resonator.p2 >> self.load_c2.p1
        self.regulator.vout.gnd >> self.load_c1.p2
        self.regulator.vout.gnd >> self.load_c2.p2

        # A UART crosses. Connecting the two ports would pair like names with
        # like — tx to tx — so the two wires are named, which is the whole
        # reason a signal of an interface is addressable on its own.
        self.bridge.uart.tx >> self.target.uart.rx
        self.bridge.uart.rx >> self.target.uart.tx
        self.bridge.uart.tx >> self.tx_probe.probe
        self.bridge.uart.rx >> self.rx_probe.probe

        self.connector.usb.vbus >> self.bulk_in.p1
        self.connector.usb.gnd >> self.bulk_in.p2
        self.regulator.vout.vcc >> self.bulk_out.p1
        self.regulator.vout.gnd >> self.bulk_out.p2
        self.bridge.power.vcc >> self.bypass.p1
        self.bridge.power.gnd >> self.bypass.p2

    def constraints(self):
        require(self.regulator.output_voltage == 3.3 * V)
        # USB gives 5 V nominal but specifies 5.25 V at the port; the regulator
        # has to survive the top of that, not the nominal.
        require(self.regulator.input_voltage_max >= 5.25 * V)
        require(self.dp_series.resistance <= 33 * Ohm)
        require(self.dm_series.resistance <= 33 * Ohm)
        require(self.resonator.load_capacitance >= 12 * pF)
