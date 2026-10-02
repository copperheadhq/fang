"""A first-order RC low-pass, and one question about it asked twice.

An anti-aliasing filter ahead of an ADC: 10 kOhm and 10 nF put the -3 dB
corner at 1 / (2 pi R C), about 1.59 kHz, and the requirement holds it between
1.5 and 1.7 kHz. The program declares the corner as a parameter with no value,
because nothing on this page has measured it, and a question that measures it:
an AC sweep with 1 V driven into the input, the corner being where the output
falls through 1/sqrt(2) of that.

The first `fang verify` finds the constraint undecided and routes the question
to the circuit level, where ngspice answers it; the measurement comes back
through the commit gate. Asked again on the committed head, the same question
is answered at the equation level: the evaluator already decides the
constraint, so nothing runs.
"""

from fang.interfaces import AnalogIn, AnalogOut, Pin, PinMap
from fang.lang import Parameter, Part, System, V, kHz, kOhm, mV, nF, require
from fang.parts import Capacitor, Resistor
from fang.rationale import Calculates, Requires
from fang.simulation import ACSweep
from fang.verification import Crossing, Simulates


class SignalIn(Part):
    """Where the signal arrives: a tip, and a sleeve that is ground."""

    designator_prefix = "J"

    line = AnalogOut()

    TIP = Pin("TIP", role="analog", number="1")
    SLEEVE = Pin("SLEEVE", role="ground", number="2")

    pinmap = PinMap({"line.signal": "TIP", "line.ref": "SLEEVE"})


class AdcInput(Part):
    """Where the filtered signal leaves for the converter."""

    designator_prefix = "J"

    line = AnalogIn()

    SIG = Pin("SIG", role="analog", number="1")
    GND = Pin("GND", role="ground", number="2")

    pinmap = PinMap({"line.signal": "SIG", "line.ref": "GND"})


class RCFilter(System):
    """The filter, the requirement on its corner, and the question that
    measures it."""

    corner_spec = Requires(
        "The anti-aliasing filter's -3 dB corner lies between 1.5 kHz and 1.7 kHz",
        validation="simulation",
    )
    by_hand = Calculates(
        "f_c = 1 / (2 pi R C)",
        inputs=("r", "c"),
        result="1.59 kHz for 10 kOhm and 10 nF",
        requirements=("corner_spec",),
    )

    # No value: the program does not know it, and a number written here would
    # be a claim rather than a measurement.
    corner = Parameter("Hz", description="the -3 dB corner, as measured")

    source = SignalIn(package="PinHeader_1x02_P2.54mm")
    adc = AdcInput(package="PinHeader_1x02_P2.54mm")
    r = Resistor(resistance=10 * kOhm, package="R_0603")
    c = Capacitor(capacitance=10 * nF, package="C_0603")

    # The bench, in full: 1 V into the input, a sweep from 10 Hz to 1 MHz, and
    # the two connectors left out -- they carry the signal and do nothing to it.
    corner_check = Simulates(
        "corner_spec",
        measures={"corner": Crossing("adc.line", level=707.1 * mV, edge="falling")},
        supplies={"source.line": 1 * V},
        analysis=ACSweep(variation="dec", points=100, start="10", stop="1meg"),
        abstracted=("source", "adc"),
    )

    def architecture(self):
        self.source.line.signal >> self.r.p1
        self.r.p2 >> self.c.p1
        self.c.p2 >> self.source.line.ref
        self.adc.line.signal >> self.c.p1
        self.adc.line.ref >> self.c.p2

    def constraints(self):
        require(self.corner >= 1.5 * kHz)
        require(self.corner <= 1.7 * kHz)
