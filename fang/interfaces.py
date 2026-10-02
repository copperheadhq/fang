"""Typed interfaces, the shipped catalogue, and the pin model.

Spec: "Typed Interfaces, Ports, Buses, and Domains", "The Shipped Interface
Catalogue", "The Pin Model", and "A Port May Be One Peripheral Instance".

System-level authoring operates on interfaces. Pin assignment is a lowering
result, which is what makes late assignment, part substitution, and honest
compatibility checking tractable.

A port may name the peripheral instance it is, and a candidate pin may carry the
selector that routes the port's signal to it, cited from the part's own
evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Iterable, Mapping, Sequence

from .diagnostics import ELAB_UNTYPED_CONNECTION, error
from .entities import ConnectionKind
from .lang import Declared, Surface
from .units import Unit

#: Canonical electrical roles a signal or a pin carries.
ROLES = (
    "power", "ground", "clock", "data", "control", "reset",
    "differential_p", "differential_n", "analog", "phase", "unknown",
)


@dataclass(frozen=True)
class SignalSpec:
    """One member signal of an interface definition."""

    name: str
    role: str = "data"
    direction: str | None = None      # source, sink, bidirectional
    required: bool = True
    open_drain: bool = False

    def __post_init__(self) -> None:
        if self.role not in ROLES:
            raise ValueError(f"{self.role!r} is not a canonical electrical role")

    def as_dict(self) -> dict:
        out = {"name": self.name, "role": self.role, "required": self.required}
        if self.direction is not None:
            out["direction"] = self.direction
        if self.open_drain:
            out["open_drain"] = True
        return out


@dataclass(frozen=True)
class InterfaceType:
    """An interface definition: its signals, its parameters, its rules.

    Two interfaces of the same type are not automatically compatible; that is
    decided by the compatibility check, not by the type match.
    """

    name: str
    signals: tuple[SignalSpec, ...]
    connection_kind: ConnectionKind = ConnectionKind.SIGNAL
    #: Parameter name to unit symbol. Every one is unknown-representable.
    parameters: Mapping[str, str] = field(default_factory=dict)
    multi_drop: bool = False          # a bus rather than a two-party link
    requires_pull_up: bool = False
    protocol: str | None = None

    @property
    def required_signals(self) -> tuple[str, ...]:
        return tuple(s.name for s in self.signals if s.required)

    @property
    def signal_names(self) -> tuple[str, ...]:
        return tuple(s.name for s in self.signals)

    def signal(self, name: str) -> SignalSpec:
        for spec in self.signals:
            if spec.name == name:
                return spec
        raise KeyError(f"{self.name} has no signal {name!r}")

    def as_dict(self) -> dict:
        out: dict = {
            "name": self.name,
            "signals": [s.as_dict() for s in self.signals],
            "connection_kind": self.connection_kind.value,
            "multi_drop": self.multi_drop,
            "requires_pull_up": self.requires_pull_up,
        }
        if self.parameters:
            out["parameters"] = dict(self.parameters)
        if self.protocol is not None:
            out["protocol"] = self.protocol
        return out


#: Electrical parameters a digital interface carries. Each is a value record and
#: is therefore unknown-representable rather than defaulted.
DIGITAL_PARAMETERS: Mapping[str, str] = {
    # The rail the interface signals against. A digital interface has a voltage
    # domain like any other, and the domain check reads it.
    "voltage": "V",
    "voh_min": "V",
    "vol_max": "V",
    "vih_min": "V",
    "vil_max": "V",
    "current_capability": "A",
    "current_demand": "A",
    "bit_rate": "Hz",
    "pull_up_resistance": "Ohm",
    "pull_up_supply": "V",
}

POWER_PARAMETERS: Mapping[str, str] = {
    "voltage": "V",
    "current_capability": "A",
    "current_demand": "A",
    "ripple": "V",
}

ANALOG_PARAMETERS: Mapping[str, str] = {
    "voltage": "V",
    "impedance": "Ohm",
    "bandwidth": "Hz",
}


def _digital(name: str, signals: Sequence[SignalSpec], **kwargs) -> InterfaceType:
    return InterfaceType(
        name, tuple(signals), ConnectionKind.SIGNAL, DIGITAL_PARAMETERS, **kwargs
    )


class InterfaceCatalogue:
    """The interface types available to a project.

    A project registers its own; a registered type participates in lowering and
    compatibility exactly as a shipped one.
    """

    def __init__(self, types: Iterable[InterfaceType] = ()) -> None:
        self._types: dict[str, InterfaceType] = {t.name: t for t in types}

    def register(self, interface: InterfaceType) -> InterfaceType:
        self._types[interface.name] = interface
        return interface

    def get(self, name: str) -> InterfaceType:
        try:
            return self._types[name]
        except KeyError:
            raise error(
                ELAB_UNTYPED_CONNECTION,
                f"no interface type named {name!r} is registered",
            ) from None

    def names(self) -> list[str]:
        return sorted(self._types)

    def __contains__(self, name: object) -> bool:
        return name in self._types

    def __len__(self) -> int:
        return len(self._types)

    def __iter__(self):
        return iter(sorted(self._types.values(), key=lambda t: t.name))


# --------------------------------------------------------------------------
# The shipped catalogue
# --------------------------------------------------------------------------

I2C = _digital(
    "i2c",
    (
        SignalSpec("scl", "clock", "bidirectional", open_drain=True),
        SignalSpec("sda", "data", "bidirectional", open_drain=True),
    ),
    multi_drop=True,
    requires_pull_up=True,
    protocol="i2c",
)

SPI = _digital(
    "spi",
    (
        SignalSpec("sck", "clock", "source"),
        SignalSpec("mosi", "data", "source"),
        SignalSpec("miso", "data", "sink"),
        SignalSpec("cs", "control", "source"),
    ),
    protocol="spi",
)

UART = _digital(
    "uart",
    (
        SignalSpec("tx", "data", "source"),
        SignalSpec("rx", "data", "sink"),
        SignalSpec("rts", "control", "source", required=False),
        SignalSpec("cts", "control", "sink", required=False),
    ),
    protocol="uart",
)

USB2 = _digital(
    "usb2",
    (
        SignalSpec("dp", "differential_p", "bidirectional"),
        SignalSpec("dm", "differential_n", "bidirectional"),
        SignalSpec("vbus", "power", "source", required=False),
        SignalSpec("gnd", "ground", "bidirectional"),
    ),
    protocol="usb2",
)

CAN = _digital(
    "can",
    (
        SignalSpec("canh", "differential_p", "bidirectional"),
        SignalSpec("canl", "differential_n", "bidirectional"),
    ),
    multi_drop=True,
    protocol="can",
)

RS485 = _digital(
    "rs485",
    (
        SignalSpec("a", "differential_p", "bidirectional"),
        SignalSpec("b", "differential_n", "bidirectional"),
        SignalSpec("de", "control", "source", required=False),
    ),
    multi_drop=True,
    protocol="rs485",
)

PWM = _digital(
    "pwm",
    (SignalSpec("out", "control", "source"),),
    protocol="pwm",
)

QUADRATURE_ENCODER = _digital(
    "quadrature_encoder",
    (
        SignalSpec("a", "data", "source"),
        SignalSpec("b", "data", "source"),
        SignalSpec("index", "data", "source", required=False),
    ),
    protocol="quadrature",
)

JTAG = _digital(
    "jtag",
    (
        SignalSpec("tck", "clock", "source"),
        SignalSpec("tms", "control", "source"),
        SignalSpec("tdi", "data", "source"),
        SignalSpec("tdo", "data", "sink"),
        SignalSpec("trst", "reset", "source", required=False),
    ),
    protocol="jtag",
)

SWD = _digital(
    "swd",
    (
        SignalSpec("swclk", "clock", "source"),
        SignalSpec("swdio", "data", "bidirectional"),
    ),
    protocol="swd",
)

CLOCK = _digital("clock", (SignalSpec("clk", "clock", "source"),), protocol="clock")

RESET = _digital("reset", (SignalSpec("nrst", "reset", "source"),), protocol="reset")

POWER_OUT = InterfaceType(
    "power_output",
    (SignalSpec("vcc", "power", "source"), SignalSpec("gnd", "ground", "bidirectional")),
    ConnectionKind.POWER,
    POWER_PARAMETERS,
    multi_drop=True,
)

POWER_IN = InterfaceType(
    "power_input",
    (SignalSpec("vcc", "power", "sink"), SignalSpec("gnd", "ground", "bidirectional")),
    ConnectionKind.POWER,
    POWER_PARAMETERS,
)

ANALOG_IN = InterfaceType(
    "analog_input",
    (SignalSpec("signal", "analog", "sink"), SignalSpec("ref", "ground", "bidirectional", required=False)),
    ConnectionKind.ELECTRICAL,
    ANALOG_PARAMETERS,
)

ANALOG_OUT = InterfaceType(
    "analog_output",
    (SignalSpec("signal", "analog", "source"), SignalSpec("ref", "ground", "bidirectional", required=False)),
    ConnectionKind.ELECTRICAL,
    ANALOG_PARAMETERS,
)

MOTOR_PHASE = InterfaceType(
    "motor_phase",
    (SignalSpec("phase", "phase", "source"),),
    ConnectionKind.POWER,
    {"voltage": "V", "current_capability": "A", "current_demand": "A"},
)

# The stage-2 single-signal surfaces, expressed as catalogue entries so that
# nothing written against them breaks.
ELECTRICAL = InterfaceType(
    "electrical", (SignalSpec("line", "unknown", "bidirectional"),), ConnectionKind.ELECTRICAL
)
GROUND = InterfaceType(
    "ground", (SignalSpec("gnd", "ground", "bidirectional"),), ConnectionKind.GROUND
)
SIGNAL = InterfaceType("signal", (SignalSpec("line", "data"),), ConnectionKind.SIGNAL)
POWER = InterfaceType(
    "power",
    (SignalSpec("vcc", "power", "bidirectional"),),
    ConnectionKind.POWER,
    POWER_PARAMETERS,
)


def default_catalogue() -> InterfaceCatalogue:
    """The catalogue every project starts with."""
    return InterfaceCatalogue(
        (
            I2C, SPI, UART, USB2, CAN, RS485, PWM, QUADRATURE_ENCODER,
            JTAG, SWD, CLOCK, RESET,
            POWER_IN, POWER_OUT, ANALOG_IN, ANALOG_OUT, MOTOR_PHASE,
            ELECTRICAL, GROUND, SIGNAL, POWER,
        )
    )


CATALOGUE = default_catalogue()


# --------------------------------------------------------------------------
# The language surface
# --------------------------------------------------------------------------


class InterfacePort(Surface):
    """A port: an interface instance owned by a module.

    Declared as `i2c = InterfacePort(I2C)`, or through the shorthand classes
    below. Connecting two ports records an interface connection, which the
    lowering turns into pin connections.

    `peripheral` names the instance the port is, such as ``"I2C1"``: a part
    whose I2C is available on two controllers declares two ports, so that one
    connection cannot land on both. It is consumed here, before the parameter
    catch-all, because it is a fact about the port and not an electrical value.
    """

    def __init__(
        self,
        interface: InterfaceType,
        *,
        role: str = "peer",
        name: str = "",
        direction: str | None = None,
        peripheral: str | None = None,
        **parameters,
    ) -> None:
        super().__init__(name=name, direction=direction)
        if peripheral is not None and (not isinstance(peripheral, str) or not peripheral):
            raise ValueError(
                f"a peripheral instance is named by a string, not {peripheral!r}"
            )
        self.interface = interface
        self.role = role
        self.peripheral = peripheral
        self.parameter_values = dict(parameters)

    @property
    def surface_type(self) -> str:  # type: ignore[override]
        return self.interface.name

    @property
    def connection_kind(self) -> ConnectionKind:  # type: ignore[override]
        return self.interface.connection_kind

    @property
    def signals(self) -> tuple[str, ...]:  # type: ignore[override]
        return self.interface.signal_names

    def __getattr__(self, name: str) -> "SignalSurface":
        """`power.vcc` is the single wire of a multi-wire interface.

        A two-wire rail cannot meaningfully land on one pad, so connecting a
        whole power interface to a single pin is refused. Naming the signal says
        which wire is meant, which is exactly the missing information.
        """
        if name.startswith("_") or "interface" not in self.__dict__:
            raise AttributeError(name)
        if name not in self.__dict__["interface"].signal_names:
            raise AttributeError(
                f"{self.__dict__['interface'].name} has no signal {name!r}"
            )
        return SignalSurface(self, name)

    def __repr__(self) -> str:
        owner = self.owner._path if self.owner and self.owner._path else "?"
        return f"<{self.interface.name} {owner}.{self.attribute}>"


class SignalSurface(Surface):
    """One named wire of an interface, so a rail can reach a single pad."""

    def __init__(self, port: InterfacePort, signal: str) -> None:
        super().__init__(name=signal)
        self.port = port
        self.signal_name = signal
        self.owner = port.owner
        self.attribute = port.attribute
        spec = port.interface.signal(signal)
        self._role = spec.role

    @property
    def surface_type(self) -> str:  # type: ignore[override]
        # A single wire keeps the nature of the wire it is: a rail wire stays
        # power, a return stays ground, and anything else is plain electrical.
        if self._role == "ground":
            return "ground"
        if self._role == "power":
            return "power"
        return "electrical"

    @property
    def connection_kind(self) -> ConnectionKind:  # type: ignore[override]
        if self._role == "ground":
            return ConnectionKind.GROUND
        if self._role == "power":
            return ConnectionKind.POWER
        return ConnectionKind.ELECTRICAL

    @property
    def signals(self) -> tuple[str, ...]:  # type: ignore[override]
        return ("line",)

    def pin_lookup(self, signal: str) -> tuple[str, str]:
        # Always the wire this surface names, never the synthetic "line".
        return (self.port.attribute, self.signal_name)

    @property
    def _entity_id(self) -> str:
        return self.port._entity_id

    def __repr__(self) -> str:
        owner = self.owner._path if self.owner and self.owner._path else "?"
        return f"<signal {owner}.{self.port.attribute}.{self.signal_name}>"


def _port_class(interface: InterfaceType, class_name: str) -> type:
    """A shorthand class so a program writes `I2CPort()` rather than a factory."""

    def __init__(self, **kwargs):
        InterfacePort.__init__(self, interface, **kwargs)

    return type(class_name, (InterfacePort,), {"__init__": __init__})


I2CPort = _port_class(I2C, "I2CPort")
SPIPort = _port_class(SPI, "SPIPort")
UARTPort = _port_class(UART, "UARTPort")
USB2Port = _port_class(USB2, "USB2Port")
CANPort = _port_class(CAN, "CANPort")
RS485Port = _port_class(RS485, "RS485Port")
PWMPort = _port_class(PWM, "PWMPort")
EncoderPort = _port_class(QUADRATURE_ENCODER, "EncoderPort")
JTAGPort = _port_class(JTAG, "JTAGPort")
SWDPort = _port_class(SWD, "SWDPort")
ClockPort = _port_class(CLOCK, "ClockPort")
ResetPort = _port_class(RESET, "ResetPort")
PowerIn = _port_class(POWER_IN, "PowerIn")
PowerOut = _port_class(POWER_OUT, "PowerOut")
AnalogIn = _port_class(ANALOG_IN, "AnalogIn")
AnalogOut = _port_class(ANALOG_OUT, "AnalogOut")
MotorPhase = _port_class(MOTOR_PHASE, "MotorPhase")


# --------------------------------------------------------------------------
# The pin model
# --------------------------------------------------------------------------


class Pin(Declared):
    """One pin of a part.

    The canonical role is what the kernel reasons about; the vendor name is what
    the engineer and the datasheet call it, and is preserved.
    """

    _declaration_kind = "pin"

    def __init__(self, name: str, *, role: str = "unknown", number: str | None = None) -> None:
        if role not in ROLES:
            raise ValueError(f"{role!r} is not a canonical electrical role")
        self.name = name
        self.role = role
        self.number = number
        self.owner = None
        self.attribute = ""

    def __repr__(self) -> str:
        return f"<Pin {self.name} ({self.role})>"


@dataclass(frozen=True)
class Selector:
    """What routes a peripheral's signal to one candidate pin.

    Vendors spell it differently — an alternate-function number, a mux mode, a
    pin-select register value — so the general form is the vendor's own text.
    It is part data, taken from a table the part cites, never inferred from a
    pin's name.
    """

    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text:
            raise ValueError(f"a selector is a non-empty string, not {self.text!r}")

    def __str__(self) -> str:
        return self.text


def AF(number: int) -> Selector:
    """An STM32-family alternate function: `AF(4)` is `Selector("AF4")`."""
    if isinstance(number, bool) or not isinstance(number, int) or number < 0:
        raise ValueError(
            f"an alternate function is a non-negative integer, not {number!r}"
        )
    return Selector(f"AF{number}")


class PinMap(Declared):
    """Which pins can carry which interface signal.

    A signal may name several candidates; choosing between them is a decision the
    lowering records, not an implicit result.

    Candidates are a pin name, a list of them in preference order, or a mapping
    from each pin name to the `Selector` that routes the signal to it:
    `PinMap({"i2c1.scl": {"PB8": AF(4), "PB6": AF(4)}}, evidence="af_table")`.
    A map that carries any selector names, as `evidence`, the `Cites`
    declaration on the same part its selectors were read from; elaboration
    refuses one that does not.
    """

    _declaration_kind = "pin_map"

    def __init__(
        self,
        mapping: Mapping[str, Sequence[str] | str | Mapping[str, Selector | None]],
        *,
        evidence: str | None = None,
    ) -> None:
        normalized: dict[str, tuple[str, ...]] = {}
        selectors: dict[str, dict[str, str]] = {}
        for signal_path, candidates in mapping.items():
            if "." not in signal_path:
                raise ValueError(
                    f"{signal_path!r} names a signal as '<port>.<signal>'"
                )
            if isinstance(candidates, str):
                candidates = (candidates,)
            elif isinstance(candidates, Mapping):
                routed = {}
                for pin, selector in candidates.items():
                    if selector is None:
                        continue
                    if not isinstance(selector, Selector):
                        raise ValueError(
                            f"{signal_path} -> {pin}: a selector is written "
                            f"Selector(...) or AF(n), not {selector!r}"
                        )
                    routed[pin] = selector.text
                if routed:
                    selectors[signal_path] = routed
            normalized[signal_path] = tuple(candidates)
        self.mapping = normalized
        self.selectors = selectors
        self.evidence = evidence

    def candidates(self, port_attribute: str, signal: str) -> tuple[str, ...]:
        return self.mapping.get(f"{port_attribute}.{signal}", ())

    def selector(self, port_attribute: str, signal: str, pin: str) -> str | None:
        """The selector routing this signal to this candidate, if one is declared."""
        return self.selectors.get(f"{port_attribute}.{signal}", {}).get(pin)

    def as_dict(self) -> dict:
        return {key: list(value) for key, value in sorted(self.mapping.items())}
