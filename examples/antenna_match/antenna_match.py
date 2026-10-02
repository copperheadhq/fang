"""A 2.4 GHz chip antenna behind an L match, and whether it is matched.

The antenna carries its network parameters as data: a one-port Touchstone
file, `chip_antenna.s1p`, which is synthetic and says so -- a series RLC
resonator written by hand, standing in for the vendor file a real design would
cite. Between the connector and the antenna sit two parts: a 1.5 pF shunt
capacitor at the connector and a 1.8 nH series inductor toward the antenna,
worked out by hand from the antenna's impedance at 2.44 GHz.

The requirement asks for 10 dB of return loss at 2.44 GHz. The program
declares the return loss as a parameter with no value and a question that
evaluates it: `fang verify` reads the file, interpolates it at 2.44 GHz,
composes the two parts with the values the graph holds, and returns the
number through the commit gate. It is answered at the equation level, in
closed form: there is nothing to simulate.
"""

from fang.interfaces import AnalogIn, AnalogOut, Pin, PinMap
from fang.lang import GHz, Parameter, Part, System, dB, nH, pF, require
from fang.parts import Capacitor, Inductor
from fang.rationale import Calculates, Requires
from fang.traits import Touchstone
from fang.verification import Evaluates, ReturnLoss, assumed_provenance


class ChipAntenna(Part):
    """A chip antenna: a feed and a ground, and a model of what it reflects."""

    designator_prefix = "AE"

    rf = AnalogIn()

    FEED = Pin("FEED", role="analog", number="1")
    GND = Pin("GND", role="ground", number="2")

    pinmap = PinMap({"rf.signal": "FEED", "rf.ref": "GND"})


class RFConnector(Part):
    """Where the radio's 50 Ohm line arrives."""

    designator_prefix = "J"

    rf = AnalogOut()

    SIG = Pin("SIG", role="analog", number="1")
    GND = Pin("GND", role="ground", number="2")

    pinmap = PinMap({"rf.signal": "SIG", "rf.ref": "GND"})


class AntennaMatch(System):
    """The antenna, its match, and the question that checks the match."""

    match_spec = Requires(
        "The antenna presents at least 10 dB of return loss at 2.44 GHz, the "
        "middle of the 2.4 GHz band",
        validation="analysis",
    )
    l_match = Calculates(
        "Q = sqrt(R0 / RL - 1); X_series = Q RL - X_antenna; B_shunt = Q / R0",
        inputs=("shunt_c", "series_l", "antenna"),
        result="1.82 nH series and 1.47 pF shunt for 22 - j3.1 Ohm at 2.44 GHz; "
        "fitted with 1.8 nH and 1.5 pF",
        requirements=("match_spec",),
    )

    # No value: the program has not measured it, and a number written here
    # would be a claim rather than a measurement.
    return_loss = Parameter("dB", description="return loss at the connector, at 2.44 GHz")

    feed = RFConnector(package="UFL")
    shunt_c = Capacitor(capacitance=1.5 * pF, package="C_0402")
    series_l = Inductor(inductance=1.8 * nH, package="L_0402")
    antenna = ChipAntenna(package="Antenna_Chip_3216")

    # The return loss looking in from the connector: through the shunt
    # capacitor, then the series inductor, into the antenna's model.
    matched = Evaluates(
        "match_spec",
        measures={
            "return_loss": ReturnLoss(
                "antenna.rf", at=2.44 * GHz, through=("shunt_c", "series_l")
            ),
        },
    )

    def __init__(self, **overrides):
        super().__init__(**overrides)
        self.antenna.add_trait(
            Touchstone(
                source="chip_antenna.s1p",
                ports=("FEED",),
                provenance=assumed_provenance(
                    "a synthetic series RLC resonator, standing in for a vendor file"
                ),
            )
        )

    def architecture(self):
        self.feed.rf.signal >> self.shunt_c.p1
        self.feed.rf.signal >> self.series_l.p1
        self.shunt_c.p2 >> self.feed.rf.ref
        self.series_l.p2 >> self.antenna.rf.signal
        self.antenna.rf.ref >> self.feed.rf.ref

    def constraints(self):
        require(self.return_loss >= 10 * dB)
