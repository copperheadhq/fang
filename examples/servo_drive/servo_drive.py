"""A three-phase servo drive: the board this toolchain was written for.

Everything here is composition. A `HalfBridge` is a block with two transistors and
a shunt: it owns its own interior and its own constraints, and the drive
instantiates three of them from one declaration. The phase, the encoder, and the
CAN bus are typed ports, so a connection says what it carries rather than which
pad it happens to land on.
"""

from fang.interfaces import (
    AnalogIn,
    CANPort,
    EncoderPort,
    MotorPhase,
    PWMPort,
    Pin,
    PinMap,
    PowerIn,
    PowerOut,
)
from fang.lang import (
    A,
    Module,
    Ohm,
    Part,
    Signal,
    System,
    V,
    W,
    kHz,
    mA,
    mOhm,
    mW,
    nF,
    require,
    uF,
)
from fang.parts import Capacitor, Connector, Regulator, Resistor, Transistor
from fang.rationale import Assumes, Requires


class HalfBridge(Module):
    """Two FETs, the node between them, and the shunt that measures it.

    The block is the unit of reuse: one declaration, three instances, and one set
    of constraints that holds for each of them.
    """

    high = Transistor(
        vds_max=100 * V,
        vgs_threshold=3 * V,
        id_max=60 * A,
        rds_on=4 * mOhm,
        package="PowerPAK-SO8",
    )
    low = Transistor(
        vds_max=100 * V,
        vgs_threshold=3 * V,
        id_max=60 * A,
        rds_on=4 * mOhm,
        package="PowerPAK-SO8",
    )
    shunt = Resistor(resistance=2 * mOhm, power_rating=2 * W, package="R_2512")

    def architecture(self):
        # The interior: a totem pole over a shunt. The midpoint is the phase and
        # the top of the shunt is the current measurement.
        self.high.source >> self.low.drain
        self.low.source >> self.shunt.p1

    def constraints(self):
        # The bus is 24 V nominal but a decelerating motor pushes it up; 100 V
        # parts on a 24 V bus is the usual margin for a regenerative load.
        require(self.high.vds_max >= 60 * V)
        require(self.low.vds_max >= 60 * V)

        # 20 A through 2 mOhm is 0.8 W. The shunt is rated for more than double
        # that, because it sits next to two FETs that are also warm.
        require(self.shunt.resistance <= 5 * mOhm)
        require(self.shunt.power_rating >= 1 * W)

        # A logic-level gate: the driver's rail has to clear the threshold with
        # room to spare, or the FET spends its life half on.
        require(self.high.vgs_threshold <= 4 * V)
        require(self.low.vgs_threshold <= 4 * V)


class GateDriver(Part):
    """One PWM in, a complementary gate pair out, per phase."""

    designator_prefix = "U"

    power = PowerIn(voltage=12 * V, current_demand=50 * mA)
    pwm = PWMPort(vih_min=2 * V, vil_max=0.8 * V, voltage=3.3 * V, bit_rate=20 * kHz)
    high_out = Signal()
    low_out = Signal()

    VCC = Pin("VCC", role="power", number="1")
    GND = Pin("GND", role="ground", number="2")
    IN = Pin("IN", role="control", number="3")
    HO = Pin("HO", role="control", number="7")
    LO = Pin("LO", role="control", number="5")

    pinmap = PinMap(
        {
            "power.vcc": "VCC",
            "power.gnd": "GND",
            "pwm.out": "IN",
            "high_out.line": "HO",
            "low_out.line": "LO",
        }
    )


class Controller(Part):
    """The MCU: three PWM outputs, three current sense inputs, CAN, encoder."""

    designator_prefix = "U"

    power = PowerIn(voltage=3.3 * V, current_demand=120 * mA)
    pwm_u = PWMPort(voh_min=2.9 * V, vol_max=0.4 * V, voltage=3.3 * V, bit_rate=20 * kHz)
    pwm_v = PWMPort(voh_min=2.9 * V, vol_max=0.4 * V, voltage=3.3 * V, bit_rate=20 * kHz)
    pwm_w = PWMPort(voh_min=2.9 * V, vol_max=0.4 * V, voltage=3.3 * V, bit_rate=20 * kHz)
    sense_u = AnalogIn(voltage=3.3 * V, impedance=1 * Ohm)
    sense_v = AnalogIn(voltage=3.3 * V, impedance=1 * Ohm)
    sense_w = AnalogIn(voltage=3.3 * V, impedance=1 * Ohm)
    encoder = EncoderPort(vih_min=2 * V, vil_max=0.8 * V, voltage=3.3 * V)
    can_tx = Signal()
    can_rx = Signal()

    VDD = Pin("VDD", role="power", number="1")
    VSS = Pin("VSS", role="ground", number="2")
    PA8 = Pin("PA8", role="control", number="41")
    PA9 = Pin("PA9", role="control", number="42")
    PA10 = Pin("PA10", role="control", number="43")
    PC0 = Pin("PC0", role="analog", number="8")
    PC1 = Pin("PC1", role="analog", number="9")
    PC2 = Pin("PC2", role="analog", number="10")
    PB4 = Pin("PB4", role="data", number="56")
    PB5 = Pin("PB5", role="data", number="57")
    PB6 = Pin("PB6", role="data", number="58")
    PB8 = Pin("PB8", role="data", number="61")
    PB9 = Pin("PB9", role="data", number="62")

    pinmap = PinMap(
        {
            "power.vcc": "VDD",
            "power.gnd": "VSS",
            "pwm_u.out": "PA8",
            "pwm_v.out": "PA9",
            "pwm_w.out": "PA10",
            "sense_u.signal": "PC0",
            "sense_v.signal": "PC1",
            "sense_w.signal": "PC2",
            "encoder.a": "PB4",
            "encoder.b": "PB5",
            "encoder.index": "PB6",
            "can_tx.line": "PB9",
            "can_rx.line": "PB8",
        }
    )


class CANTransceiver(Part):
    """TTL on the logic side, a differential pair on the bus side."""

    designator_prefix = "U"

    power = PowerIn(voltage=3.3 * V, current_demand=70 * mA)
    bus = CANPort(voltage=3.3 * V, bit_rate=1000 * kHz)
    txd = Signal()
    rxd = Signal()

    VCC = Pin("VCC", role="power", number="3")
    GND = Pin("GND", role="ground", number="2")
    TXD = Pin("TXD", role="data", number="1")
    RXD = Pin("RXD", role="data", number="4")
    CANH = Pin("CANH", role="differential_p", number="7")
    CANL = Pin("CANL", role="differential_n", number="6")

    pinmap = PinMap(
        {
            "power.vcc": "VCC",
            "power.gnd": "GND",
            "txd.line": "TXD",
            "rxd.line": "RXD",
            "bus.canh": "CANH",
            "bus.canl": "CANL",
        }
    )


class MotorConnector(Connector):
    """Three phases out to the windings."""

    designator_prefix = "J"

    phase_u = MotorPhase(voltage=24 * V, current_demand=15 * A)
    phase_v = MotorPhase(voltage=24 * V, current_demand=15 * A)
    phase_w = MotorPhase(voltage=24 * V, current_demand=15 * A)

    U = Pin("U", role="phase", number="1")
    V_ = Pin("V", role="phase", number="2")
    W = Pin("W", role="phase", number="3")

    pinmap = PinMap({"phase_u.phase": "U", "phase_v.phase": "V", "phase_w.phase": "W"})


class EncoderConnector(Connector):
    designator_prefix = "J"

    encoder = EncoderPort(voh_min=2.9 * V, vol_max=0.4 * V, voltage=3.3 * V)

    A_ = Pin("A", role="data", number="1")
    B_ = Pin("B", role="data", number="2")
    Z = Pin("Z", role="data", number="3")

    pinmap = PinMap({"encoder.a": "A", "encoder.b": "B", "encoder.index": "Z"})


class BusConnector(Connector):
    designator_prefix = "J"

    can = CANPort(voltage=3.3 * V, bit_rate=1000 * kHz)

    H = Pin("CANH", role="differential_p", number="1")
    L = Pin("CANL", role="differential_n", number="2")

    pinmap = PinMap({"can.canh": "CANH", "can.canl": "CANL"})


class BusTerminal(Connector):
    """The lugs the 24 V bus arrives on."""

    designator_prefix = "J"

    dc = PowerOut(voltage=24 * V, current_capability=20 * A)

    VP = Pin("V+", role="power", number="1")
    VN = Pin("V-", role="ground", number="2")

    pinmap = PinMap({"dc.vcc": "V+", "dc.gnd": "V-"})


class ServoDrive(System):
    dc_bus = PowerIn(voltage=24 * V, current_capability=20 * A)

    thermal = Requires(
        "Conduction loss per bridge stays under 2 W at 15 A continuous",
        validation="analysis",
    )
    switching_loss = Assumes(
        "Switching loss at 20 kHz is small beside conduction loss",
        rationale="not yet computed; true for these gate charges at this frequency",
    )

    bus_in = BusTerminal(
        current_rating=30 * A, voltage_rating=60 * V, package="TerminalBlock_1x02_P7.62mm"
    )

    # The two housekeeping rails. A drive that only had the bus would still
    # need these, so they belong to the drive rather than to the board it is on.
    gate_rail = Regulator(
        input_voltage_max=60 * V,
        output_voltage=12 * V,
        output_current_max=500 * mA,
        package="SOT-223",
    )
    logic_rail = Regulator(
        input_voltage_max=15 * V,
        output_voltage=3.3 * V,
        output_current_max=1 * A,
        package="SOT-23-5",
    )

    controller = Controller(package="LQFP-64")
    transceiver = CANTransceiver(package="SOIC-8")

    driver_u = GateDriver(package="SOIC-8")
    driver_v = GateDriver(package="SOIC-8")
    driver_w = GateDriver(package="SOIC-8")

    bridge_u = HalfBridge()
    bridge_v = HalfBridge()
    bridge_w = HalfBridge()

    motor = MotorConnector(
        current_rating=20 * A, voltage_rating=60 * V, package="TerminalBlock_1x03_P7.62mm"
    )
    encoder_port = EncoderConnector(
        current_rating=1 * A, voltage_rating=12 * V, package="JST_PH_1x03_P2.00mm"
    )
    can_port = BusConnector(
        current_rating=1 * A, voltage_rating=12 * V, package="JST_PH_1x02_P2.00mm"
    )

    # 120 Ohm, because this node is one end of the bus rather than a stub on it.
    termination = Resistor(resistance=120 * Ohm, power_rating=250 * mW, package="R_0805")
    bus_bulk = Capacitor(capacitance=470 * uF, voltage_rating=63 * V, package="Radial_D10")
    logic_bypass = Capacitor(capacitance=100 * nF, voltage_rating=16 * V, package="C_0402")

    def architecture(self):
        self.dc_bus >> self.bus_in.dc
        self.bus_in.dc >> self.gate_rail.vin
        self.gate_rail.vout >> self.logic_rail.vin

        self.logic_rail.vout >> self.controller.power
        self.logic_rail.vout >> self.transceiver.power

        for driver, bridge, pwm, sense, phase in (
            (self.driver_u, self.bridge_u, self.controller.pwm_u, self.controller.sense_u, self.motor.phase_u),
            (self.driver_v, self.bridge_v, self.controller.pwm_v, self.controller.sense_v, self.motor.phase_v),
            (self.driver_w, self.bridge_w, self.controller.pwm_w, self.controller.sense_w, self.motor.phase_w),
        ):
            self.gate_rail.vout >> driver.power
            pwm >> driver.pwm
            driver.high_out >> bridge.high.gate
            driver.low_out >> bridge.low.gate

            self.bus_in.dc.vcc >> bridge.high.drain
            self.bus_in.dc.gnd >> bridge.shunt.p2
            bridge.low.drain >> phase.phase
            bridge.shunt.p1 >> sense.signal

        self.controller.can_tx >> self.transceiver.txd
        self.controller.can_rx >> self.transceiver.rxd
        self.transceiver.bus >> self.can_port.can
        self.transceiver.bus.canh >> self.termination.p1
        self.transceiver.bus.canl >> self.termination.p2

        self.controller.encoder >> self.encoder_port.encoder

        self.bus_in.dc.vcc >> self.bus_bulk.p1
        self.bus_in.dc.gnd >> self.bus_bulk.p2
        self.controller.power.vcc >> self.logic_bypass.p1
        self.controller.power.gnd >> self.logic_bypass.p2

    def constraints(self):
        # The bus capacitor sees the bus, plus whatever the motor puts back into
        # it; a 63 V part on a 24 V bus is that allowance, stated.
        require(self.bus_bulk.voltage_rating >= 50 * V)
        require(self.termination.resistance == 120 * Ohm)
        require(self.motor.voltage_rating >= 48 * V)
