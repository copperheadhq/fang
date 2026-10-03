"""Quiet Orbit QO-R1: copperhead's four-light USB lamp, its firmware run in simavr.

QO-R1 is a 57 mm board designed with copperhead (copperheadhq/copperhead-
quiet-orbit, 056933b): four amber LEDs at the corners of a 40 mm square, each
sunk by one of an ATtiny84A's four hardware-PWM outputs and fading on its own
phase, powered from USB-C through a polyfuse and a reverse-blocking diode. It
has never been built, and its firmware had never been compiled before this
example ran it.

The board is QO-R1's schematic intent and bill of materials, part for part and
net for net. Its connectors are reduced to one pin per function: the
receptacle's four VBUS and four GND contacts and its shell are joined on the
board, and its D+, D- and SBU contacts are not connected. The firmware is
QO-R1's own, under its own licence (firmware/qo-r1/LICENSE, GPL-3.0-only).

Two questions are asked of the same firmware. As QO-R1's README directs, the
board is programmed with the low fuse 0xE2, the 8 MHz oscillator undivided,
and the lamp fades as designed. But the ATtiny84A ships with its clock divided
by eight, and nothing in QO-R1's build programs the fuse: the second question
runs the firmware on the part as it ships, and the lamp's PWM runs at an
eighth of its rate and its fade takes eight times as long.
"""

from fang.emulation import Count, Duty, EmulationModel, Emulates, Firmware, Rises
from fang.interfaces import Pin, PinMap, PowerIn, PowerOut
from fang.lang import (
    Ohm,
    Parameter,
    Part,
    Signal,
    System,
    UnitLiteral,
    V,
    kOhm,
    mA,
    ms,
    nF,
    require,
    s,
    uF,
)
from fang.parts import LED, Capacitor, DecouplingCapacitor, Diode, Fuse, Resistor, TestPoint
from fang.rationale import Cites, Requires

#: Dimensionless, for edges counted and fractions of a window.
count = UnitLiteral("1")

#: The documents every number below was read from.
MICROCHIP = "SRC-DS-ATTINY84A"      # Microchip DS40002269A, ATtiny24A/44A/84A, 2020
QO_R1 = "SRC-QO-R1"                 # copperheadhq/copperhead-quiet-orbit at 056933b


class ATtiny84A(Part):
    """Microchip's ATtiny84A in SOIC-14, as QO-R1 uses it.

    Each LED is sunk by one of the four compare outputs of Timer/Counter0 and
    Timer/Counter1, which this part names by the light it drives. MOSI and
    MISO share PA6 and PA5 with two of them, which is how QO-R1's ISP header
    reaches the part.
    """

    designator_prefix = "U"

    power = PowerIn(voltage=5 * V)
    led_nw = Signal()
    led_ne = Signal()
    led_se = Signal()
    led_sw = Signal()
    sck = Signal()
    reset = Signal()

    VCC = Pin("VCC", role="power", number="1")
    PB0 = Pin("PB0", role="unknown", number="2")
    PB1 = Pin("PB1", role="unknown", number="3")
    PB3 = Pin("PB3", role="control", number="4")
    PB2 = Pin("PB2", role="data", number="5")
    PA7 = Pin("PA7", role="data", number="6")
    PA6 = Pin("PA6", role="data", number="7")
    PA5 = Pin("PA5", role="data", number="8")
    PA4 = Pin("PA4", role="clock", number="9")
    PA3 = Pin("PA3", role="unknown", number="10")
    PA2 = Pin("PA2", role="unknown", number="11")
    PA1 = Pin("PA1", role="unknown", number="12")
    PA0 = Pin("PA0", role="unknown", number="13")
    GND = Pin("GND", role="ground", number="14")

    pinout = Cites(
        "SOIC-14: 1 VCC, 2 PB0, 3 PB1, 4 PB3 (RESET), 5 PB2, 6 PA7, 7 PA6, 8 PA5, "
        "9 PA4, 10 PA3, 11 PA2, 12 PA1, 13 PA0, 14 GND",
        document=MICROCHIP,
        locator="DS40002269A, figure 1-1 (pinout of ATtiny24A/44A/84A), p. 8",
    )
    compare_outputs = Cites(
        "OC0A is PB2, OC0B is PA7, OC1A is PA6 and OC1B is PA5; PA6 is also MOSI, "
        "PA5 MISO and PA4 SCK",
        document=MICROCHIP,
        locator="DS40002269A, sections 10.2.1 and 10.2.2 (alternate functions of "
        "ports A and B), pp. 66-70",
    )
    shipped_clock = Cites(
        "The device is shipped with CKSEL = 0010, SUT = 10 and CKDIV8 programmed: "
        "the internal oscillator at 8.0 MHz with an initial system clock prescaling "
        "of 8, a 1.0 MHz system clock; the fuse low byte defaults to 0x62",
        document=MICROCHIP,
        locator="DS40002269A, section 6.2.6 (default clock source), p. 36; table 19-5 "
        "(fuse low byte), p. 166",
    )
    part_number = Cites(
        "ATTINY84A-SSU is the ATtiny84A in a 14-lead SOIC (150 mil), -40 to 85 C",
        document=MICROCHIP,
        locator="DS40002269A, section 27 (ordering information)",
    )

    pinmap = PinMap(
        {
            "power.vcc": "VCC",
            "power.gnd": "GND",
            "led_nw.line": "PB2",
            "led_ne.line": "PA7",
            "led_se.line": "PA6",
            "led_sw.line": "PA5",
            "sck.line": "PA4",
            "reset.line": "PB3",
        },
        evidence="pinout",
    )


class UsbCPowerReceptacle(Part):
    """A USB-C receptacle wired as a 5 V sink and nothing else (J1)."""

    designator_prefix = "J"

    vbus = PowerOut(voltage=5 * V)
    cc1 = Signal()
    cc2 = Signal()

    VBUS = Pin("VBUS", role="power", number="A4")
    GND = Pin("GND", role="ground", number="A1")
    CC1 = Pin("CC1", role="control", number="A5")
    CC2 = Pin("CC2", role="control", number="B5")

    pinmap = PinMap({"vbus.vcc": "VBUS", "vbus.gnd": "GND", "cc1.line": "CC1", "cc2.line": "CC2"})


class IspHeader(Part):
    """The six-pin AVR ISP header (J2). Its VCC pin lets a programmer sense
    the board's supply, and is not a way in for power."""

    designator_prefix = "J"

    sense = PowerIn(voltage=5 * V)
    miso = Signal()
    sck = Signal()
    mosi = Signal()
    reset = Signal()

    MISO = Pin("MISO", role="data", number="1")
    VCC = Pin("VCC", role="power", number="2")
    SCK = Pin("SCK", role="clock", number="3")
    MOSI = Pin("MOSI", role="data", number="4")
    RST = Pin("RESET", role="control", number="5")
    GND = Pin("GND", role="ground", number="6")

    pinmap = PinMap(
        {
            "sense.vcc": "VCC",
            "sense.gnd": "GND",
            "miso.line": "MISO",
            "sck.line": "SCK",
            "mosi.line": "MOSI",
            "reset.line": "RESET",
        }
    )


class QuietOrbit(System):
    """QO-R1: four LEDs on four PWM channels, fading a quarter cycle apart.

    The firmware fades each LED through a triangle of 256 steps, each a
    4.013 ms loop at 8 MHz (a 4 ms delay and 102 cycles of loop), the four a
    quarter cycle apart: SE is brightest first, then NE, NW and SW. Both
    questions run it for 2 s and measure the same things: NW's rising edges
    in the second second, which are its PWM rate, and the fraction of a 16 ms
    window each LED's pin is low, its brightness, at the time it should be
    brightest. Neither asserts an LED dark: simavr lights a compare output for
    a period whose compare value is TOP, which the part does not.
    """

    fades = Requires(
        "Programmed with the low fuse 0xE2, as its firmware's README directs, the "
        "four LEDs fade on hardware PWM at the firmware's 488 Hz, a quarter cycle "
        "apart, each fully lit in turn SE, NE, NW and SW",
        validation="emulation",
    )
    fades_as_shipped = Requires(
        "Programmed over ISP with its firmware and nothing else, on a part with "
        "the fuses it ships with, the four LEDs fade as they do with the fuse set",
        validation="emulation",
    )

    pwm_rises = Parameter("", description="NW's rising edges between 1 s and 2 s, fuse set")
    se_lit = Parameter("", description="SE's pin low between 0 and 16 ms, fuse set")
    ne_lit = Parameter("", description="NE's pin low between 257 and 273 ms, fuse set")
    nw_lit = Parameter("", description="NW's pin low between 514 and 530 ms, fuse set")
    sw_lit = Parameter("", description="SW's pin low between 771 and 787 ms, fuse set")
    shipped_pwm_rises = Parameter("", description="NW's rising edges between 1 s and 2 s, as shipped")
    shipped_se_lit = Parameter("", description="SE's pin low between 0 and 16 ms, as shipped")
    shipped_ne_lit = Parameter("", description="NE's pin low between 257 and 273 ms, as shipped")
    shipped_nw_lit = Parameter("", description="NW's pin low between 514 and 530 ms, as shipped")
    shipped_sw_lit = Parameter("", description="SW's pin low between 771 and 787 ms, as shipped")

    # The LEDs and the ISP header share nets with the observed pins and carry
    # no emulation model; the LEDs are what is being lit, and the header has
    # no programmer on it while the lamp runs.
    orbit = Emulates(
        "fades",
        run_until=2 * s,
        measures={
            "pwm_rises": Count(Rises("mcu.led_nw"), within=(1 * s, 2 * s)),
            "se_lit": Duty("mcu.led_se", level=0, within=(0 * ms, 16 * ms)),
            "ne_lit": Duty("mcu.led_ne", level=0, within=(257 * ms, 273 * ms)),
            "nw_lit": Duty("mcu.led_nw", level=0, within=(514 * ms, 530 * ms)),
            "sw_lit": Duty("mcu.led_sw", level=0, within=(771 * ms, 787 * ms)),
        },
        abstracted=("lamp_nw", "lamp_ne", "lamp_se", "lamp_sw", "isp"),
    )
    as_shipped = Emulates(
        "fades_as_shipped",
        run_until=2 * s,
        fuses="factory",
        measures={
            "shipped_pwm_rises": Count(Rises("mcu.led_nw"), within=(1 * s, 2 * s)),
            "shipped_se_lit": Duty("mcu.led_se", level=0, within=(0 * ms, 16 * ms)),
            "shipped_ne_lit": Duty("mcu.led_ne", level=0, within=(257 * ms, 273 * ms)),
            "shipped_nw_lit": Duty("mcu.led_nw", level=0, within=(514 * ms, 530 * ms)),
            "shipped_sw_lit": Duty("mcu.led_sw", level=0, within=(771 * ms, 787 * ms)),
        },
        abstracted=("lamp_nw", "lamp_ne", "lamp_se", "lamp_sw", "isp"),
    )

    readme_fuse = Cites(
        "The ATtiny84A arrives blank and runs on its internal 8 MHz RC oscillator. "
        "If your part ships with the clock divided by 8, change that fuse; nothing "
        "else needs changing",
        document=QO_R1,
        locator="README.md, Building it; firmware/README.md: F_CPU=8000000UL",
    )
    leds_on_pwm = Cites(
        "Each LED SHALL have its own series resistor and its own MCU pin with a "
        "hardware PWM output, permitting four simultaneous independent fades",
        document=QO_R1,
        locator="docs/SPEC.md, light output; docs/PINOUT.md, LED channel mapping",
    )

    # J1 and the CC terminations: a power-only 5 V sink.
    usb = UsbCPowerReceptacle(package="USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal")
    cc1_rd = Resistor(resistance=5.1 * kOhm, package="R_0603_1608Metric")
    cc2_rd = Resistor(resistance=5.1 * kOhm, package="R_0603_1608Metric")

    # Input protection: polyfuse, reverse blocker, bulk on both sides.
    polyfuse = Fuse(current_rating=100 * mA, package="Fuse_0603_1608Metric")
    blocker = Diode(package="D_SOD-123")
    c_in = Capacitor(capacitance=1 * uF, package="C_0603_1608Metric")
    c_bulk = Capacitor(capacitance=4.7 * uF, package="C_0805_2012Metric")

    # The MCU, its bypass and its reset pull-up.
    mcu = ATtiny84A(package="SOIC-14_3.9x8.7mm_P1.27mm")
    bypass = DecouplingCapacitor(capacitance=100 * nF, package="C_0603_1608Metric")
    reset_pullup = Resistor(resistance=10 * kOhm, package="R_0603_1608Metric")

    # The four lights: VCC, a 680 ohm resistor, the LED, and the MCU pin that
    # sinks it, so a pin driven low lights its LED.
    r_nw = Resistor(resistance=680 * Ohm, package="R_0603_1608Metric")
    r_ne = Resistor(resistance=680 * Ohm, package="R_0603_1608Metric")
    r_se = Resistor(resistance=680 * Ohm, package="R_0603_1608Metric")
    r_sw = Resistor(resistance=680 * Ohm, package="R_0603_1608Metric")
    lamp_nw = LED(package="LED_1206_3216Metric")
    lamp_ne = LED(package="LED_1206_3216Metric")
    lamp_se = LED(package="LED_1206_3216Metric")
    lamp_sw = LED(package="LED_1206_3216Metric")

    # Programming and test access.
    isp = IspHeader(package="IDC-Header_2x03_P2.54mm_Vertical")
    tp_vbus = TestPoint(package="TestPoint_Pad_D1.5mm")
    tp_vcc = TestPoint(package="TestPoint_Pad_D1.5mm")
    tp_gnd = TestPoint(package="TestPoint_Pad_D1.5mm")
    tp_reset = TestPoint(package="TestPoint_Pad_D1.5mm")

    def __init__(self, **overrides):
        super().__init__(**overrides)
        self.mcu.select("Microchip", "ATTINY84A-SSU", datasheet=MICROCHIP)
        # What the emulator runs: fang's ATtiny84A platform model, and QO-R1's
        # firmware as published, programmed with the fuse its README sets.
        self.mcu.add_trait(EmulationModel(source="fang:attiny84a"))
        self.mcu.add_trait(
            Firmware("firmware/elf/quiet-orbit-qo-r1.elf", target="attiny84a", fuses={"low": 0xE2})
        )

    def architecture(self):
        vbus, gnd = self.usb.vbus.vcc, self.usb.vbus.gnd

        # VBUS: the receptacle, its input capacitor, the fuse and a test point.
        vbus >> self.c_in.p1
        gnd >> self.c_in.p2
        vbus >> self.polyfuse.p1
        vbus >> self.tp_vbus.probe
        self.usb.cc1 >> self.cc1_rd.p1
        gnd >> self.cc1_rd.p2
        self.usb.cc2 >> self.cc2_rd.p1
        gnd >> self.cc2_rd.p2

        # VBUS_FUSED, then VCC on the blocker's cathode.
        self.polyfuse.p2 >> self.blocker.p1
        vcc = self.blocker.p2
        vcc >> self.c_bulk.p1
        gnd >> self.c_bulk.p2
        vcc >> self.mcu.power.vcc
        gnd >> self.mcu.power.gnd
        self.mcu.power.vcc >> self.bypass.p1
        self.mcu.power.gnd >> self.bypass.p2
        vcc >> self.tp_vcc.probe
        gnd >> self.tp_gnd.probe

        # RESET: pulled up, on the header and a test point.
        vcc >> self.reset_pullup.p1
        self.reset_pullup.p2 >> self.mcu.reset
        self.mcu.reset >> self.isp.reset
        self.mcu.reset >> self.tp_reset.probe

        # The lights, each sunk by its compare output.
        for resistor, lamp, pin in (
            (self.r_nw, self.lamp_nw, self.mcu.led_nw),
            (self.r_ne, self.lamp_ne, self.mcu.led_ne),
            (self.r_se, self.lamp_se, self.mcu.led_se),
            (self.r_sw, self.lamp_sw, self.mcu.led_sw),
        ):
            vcc >> resistor.p1
            resistor.p2 >> lamp.p1
            lamp.p2 >> pin

        # The ISP header shares MOSI with SE and MISO with SW.
        vcc >> self.isp.sense.vcc
        gnd >> self.isp.sense.gnd
        self.mcu.sck >> self.isp.sck
        self.mcu.led_se >> self.isp.mosi
        self.mcu.led_sw >> self.isp.miso

    def constraints(self):
        # 8 MHz / 64 / 256 = 488.28 Hz, within 5 %: the rate the firmware's
        # timer setup gives at the clock it was written for.
        require(self.pwm_rises >= 464 * count)
        require(self.pwm_rises <= 513 * count)
        # Each LED is all but fully lit at its peak: its compare value is near
        # 0 for the whole window.
        require(self.se_lit >= 0.9 * count)
        require(self.ne_lit >= 0.9 * count)
        require(self.nw_lit >= 0.9 * count)
        require(self.sw_lit >= 0.9 * count)

        require(self.shipped_pwm_rises >= 464 * count)
        require(self.shipped_pwm_rises <= 513 * count)
        require(self.shipped_se_lit >= 0.9 * count)
        require(self.shipped_ne_lit >= 0.9 * count)
        require(self.shipped_nw_lit >= 0.9 * count)
        require(self.shipped_sw_lit >= 0.9 * count)
