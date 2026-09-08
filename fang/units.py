"""Quantities, units, and dimensions.

Spec: "Physical Quantities and Units". A physical quantity is a record, never a
bare number. A magnitude is a decimal string and never binary floating point.
Canonical form normalizes the symbol and not the magnitude, so ``3.3 V`` stays
``3.3 V`` rather than becoming ``3300 mV``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Context, Decimal, localcontext
from fractions import Fraction
from typing import Iterable, Literal, Mapping

from .diagnostics import (
    UNIT_BAD_EXPONENT,
    UNIT_DIMENSION_MISMATCH,
    UNIT_UNKNOWN_SYMBOL,
    error,
)

#: The seven SI base dimensions, in the fixed order the spec requires.
BASE_DIMENSIONS = (
    "length",
    "mass",
    "time",
    "current",
    "temperature",
    "amount",
    "luminous_intensity",
)

#: Decimal working precision. Fixed so that arithmetic does not vary by platform
#: or by whatever context a caller happens to have installed.
PRECISION = 34


#: One fixed decimal context, so arithmetic never depends on whatever context a
#: caller happens to have installed.
_CONTEXT = Context(prec=PRECISION)


def _ctx():
    return localcontext(_CONTEXT)


@dataclass(frozen=True)
class Dimension:
    """A vector of exponents over the seven SI base dimensions.

    Exponents are ``Fraction`` rather than ``int`` because the spec permits a
    rational exponent. Two quantities are comparable only where their dimension
    vectors are equal, which here is tuple equality.
    """

    exponents: tuple[Fraction, ...] = field(
        default=(Fraction(0),) * 7
    )

    def __post_init__(self) -> None:
        if len(self.exponents) != 7:
            raise ValueError("a dimension has exactly seven exponents")
        object.__setattr__(
            self, "exponents", tuple(Fraction(e) for e in self.exponents)
        )

    @classmethod
    def base(cls, name: str) -> "Dimension":
        index = BASE_DIMENSIONS.index(name)
        exponents = [Fraction(0)] * 7
        exponents[index] = Fraction(1)
        return cls(tuple(exponents))

    @property
    def dimensionless(self) -> bool:
        return all(e == 0 for e in self.exponents)

    def __mul__(self, other: "Dimension") -> "Dimension":
        return Dimension(tuple(a + b for a, b in zip(self.exponents, other.exponents)))

    def __truediv__(self, other: "Dimension") -> "Dimension":
        return Dimension(tuple(a - b for a, b in zip(self.exponents, other.exponents)))

    def __pow__(self, exponent: Fraction | int) -> "Dimension":
        exponent = Fraction(exponent)
        return Dimension(tuple(e * exponent for e in self.exponents))

    def __str__(self) -> str:
        if self.dimensionless:
            return "1"
        parts = []
        for name, e in zip(BASE_DIMENSIONS, self.exponents):
            if e == 0:
                continue
            parts.append(name if e == 1 else f"{name}^{e}")
        return "*".join(parts)

    def as_list(self) -> list[str]:
        """Serialize as decimal strings, so the vector round-trips exactly."""
        return [str(e) for e in self.exponents]


DIMENSIONLESS = Dimension()

# --------------------------------------------------------------------------
# Unit table
# --------------------------------------------------------------------------

_L = Dimension.base("length")
_M = Dimension.base("mass")
_T = Dimension.base("time")
_I = Dimension.base("current")
_K = Dimension.base("temperature")
_N = Dimension.base("amount")
_J = Dimension.base("luminous_intensity")


@dataclass(frozen=True)
class _UnitDef:
    dimension: Dimension
    factor: Decimal  # multiply by this to reach SI base units
    offset: Decimal = Decimal(0)  # affine units only; degC, degF
    prefixable: bool = True


def _d(dimension: Dimension, factor: str = "1", offset: str = "0", prefixable: bool = True) -> _UnitDef:
    return _UnitDef(dimension, Decimal(factor), Decimal(offset), prefixable)


#: Recognized unit symbols. SI symbols, plus the plain ASCII names of units whose
#: symbol is not ASCII (``Ohm``, ``degC``), as the spec requires.
UNITS: Mapping[str, _UnitDef] = {
    # base
    "m": _d(_L),
    "g": _d(_M, "0.001"),
    "s": _d(_T),
    "A": _d(_I),
    "K": _d(_K),
    "mol": _d(_N),
    "cd": _d(_J),
    # derived, electrical
    "V": _d(_L**2 * _M / _T**3 / _I),
    "Ohm": _d(_L**2 * _M / _T**3 / _I**2),
    "S": _d(_T**3 * _I**2 / _L**2 / _M),
    "F": _d(_T**4 * _I**2 / _L**2 / _M),
    "H": _d(_L**2 * _M / _T**2 / _I**2),
    "C": _d(_T * _I),
    "Wb": _d(_L**2 * _M / _T**2 / _I),
    "T": _d(_M / _T**2 / _I),
    # derived, mechanical and thermal
    "N": _d(_L * _M / _T**2),
    "J": _d(_L**2 * _M / _T**2),
    "W": _d(_L**2 * _M / _T**3),
    "Pa": _d(_M / _L / _T**2),
    "Hz": _d(DIMENSIONLESS / _T),
    "degC": _d(_K, "1", "273.15", prefixable=False),
    # dimensionless
    "1": _d(DIMENSIONLESS, prefixable=False),
    "rad": _d(DIMENSIONLESS, prefixable=False),
    "percent": _d(DIMENSIONLESS, "0.01", prefixable=False),
    "ppm": _d(DIMENSIONLESS, "0.000001", prefixable=False),
    # accepted non-SI
    "min": _d(_T, "60", prefixable=False),
    "h": _d(_T, "3600", prefixable=False),
    "L": _d(_L**3, "0.001"),
    "eV": _d(_L**2 * _M / _T**2, "1.602176634E-19"),
}

#: Metric prefixes. A prefix is permitted on input; canonical form keeps it.
PREFIXES: Mapping[str, str] = {
    "Q": "1E30", "R": "1E27", "Y": "1E24", "Z": "1E21", "E": "1E18",
    "P": "1E15", "T": "1E12", "G": "1E9", "M": "1E6", "k": "1E3",
    "h": "1E2", "da": "1E1",
    "d": "1E-1", "c": "1E-2", "m": "1E-3", "u": "1E-6", "n": "1E-9",
    "p": "1E-12", "f": "1E-15", "a": "1E-18", "z": "1E-21", "y": "1E-24",
    "r": "1E-27", "q": "1E-30",
}

_TERM = re.compile(r"^([A-Za-z%1][A-Za-z0-9]*)(?:\^(-?\d+(?:/\d+)?))?$")


def _resolve_symbol(symbol: str) -> tuple[Decimal, Dimension, Decimal]:
    """Resolve one symbol to (factor, dimension, offset)."""
    definition = UNITS.get(symbol)
    if definition is not None:
        return definition.factor, definition.dimension, definition.offset

    # Try a metric prefix. Longest prefix first, so "da" beats "d".
    for length in (2, 1):
        prefix, rest = symbol[:length], symbol[length:]
        if prefix in PREFIXES and rest in UNITS:
            definition = UNITS[rest]
            if not definition.prefixable:
                continue
            with _ctx():
                factor = definition.factor * Decimal(PREFIXES[prefix])
            return factor, definition.dimension, definition.offset

    raise error(UNIT_UNKNOWN_SYMBOL, f"unit symbol {symbol!r} is not recognized")


@dataclass(frozen=True)
class Unit:
    """A parsed unit: a canonical symbol, a dimension, and a scale to SI base.

    The symbol is normalized; the magnitude never is.
    """

    symbol: str
    dimension: Dimension
    factor: Decimal
    offset: Decimal = Decimal(0)

    @classmethod
    def parse(cls, text: str) -> "Unit":
        text = text.strip()
        if not text:
            return cls("1", DIMENSIONLESS, Decimal(1))

        numerator: list[tuple[str, Fraction]] = []
        denominator: list[tuple[str, Fraction]] = []

        # Split on * and / keeping the operator that introduced each term.
        tokens = re.split(r"([*/])", text)
        sign = 1
        for index, token in enumerate(tokens):
            token = token.strip()
            if token == "*":
                sign = 1
                continue
            if token == "/":
                sign = -1
                continue
            if not token:
                continue
            match = _TERM.match(token)
            if match is None:
                raise error(UNIT_UNKNOWN_SYMBOL, f"unit term {token!r} is not well formed")
            symbol, exponent_text = match.group(1), match.group(2)
            exponent = Fraction(exponent_text) if exponent_text else Fraction(1)
            exponent *= sign
            (numerator if exponent > 0 else denominator).append(
                (symbol, abs(exponent))
            )

        dimension = DIMENSIONLESS
        offset = Decimal(0)
        with _ctx():
            factor = Decimal(1)
            for symbol, exponent in numerator:
                term_factor, term_dimension, term_offset = _resolve_symbol(symbol)
                factor *= term_factor ** _as_int_exponent(exponent, symbol)
                dimension = dimension * (term_dimension ** exponent)
                offset = term_offset if len(numerator) == 1 and not denominator else Decimal(0)
            for symbol, exponent in denominator:
                term_factor, term_dimension, _ = _resolve_symbol(symbol)
                factor /= term_factor ** _as_int_exponent(exponent, symbol)
                dimension = dimension / (term_dimension ** exponent)

        return cls(_canonical_symbol(numerator, denominator), dimension, factor, offset)

    def __str__(self) -> str:
        return self.symbol

    @property
    def affine(self) -> bool:
        return self.offset != 0

    def as_dict(self) -> dict:
        return {"symbol": self.symbol, "dimension": self.dimension.as_list()}


def _as_int_exponent(exponent: Fraction, symbol: str) -> int:
    if exponent.denominator != 1:
        raise error(
            UNIT_BAD_EXPONENT,
            f"unit {symbol!r} carries the fractional exponent {exponent}; "
            "a scale factor is defined only for an integer exponent",
        )
    return int(exponent)


def _canonical_symbol(
    numerator: list[tuple[str, Fraction]], denominator: list[tuple[str, Fraction]]
) -> str:
    def render(terms: list[tuple[str, Fraction]]) -> str:
        merged: dict[str, Fraction] = {}
        for symbol, exponent in terms:
            merged[symbol] = merged.get(symbol, Fraction(0)) + exponent
        parts = []
        for symbol in sorted(merged, key=lambda s: [ord(c) for c in s]):
            exponent = merged[symbol]
            if exponent == 0:
                continue
            parts.append(symbol if exponent == 1 else f"{symbol}^{exponent}")
        return "*".join(parts)

    top = render(numerator) or "1"
    bottom = render(denominator)
    return f"{top}/{bottom}" if bottom else top


# --------------------------------------------------------------------------
# Quantities
# --------------------------------------------------------------------------

QuantityKind = Literal["scalar", "range", "tolerance"]
ToleranceKind = Literal["relative", "absolute"]


@dataclass(frozen=True)
class Tolerance:
    kind: ToleranceKind
    value: Decimal

    def as_dict(self) -> dict:
        return {"kind": self.kind, "value": _decimal_str(self.value)}


@dataclass(frozen=True)
class Quantity:
    """A physical quantity. Never a bare number.

    A scalar carries ``value``; a range carries ``min`` and ``max`` and may carry
    ``typical``; a tolerance carries ``nominal`` and a ``tolerance``.
    """

    kind: QuantityKind
    unit: Unit
    value: Decimal | None = None
    minimum: Decimal | None = None
    maximum: Decimal | None = None
    typical: Decimal | None = None
    nominal: Decimal | None = None
    tolerance: Tolerance | None = None
    conditions: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind == "scalar" and self.value is None:
            raise ValueError("a scalar quantity carries a value")
        if self.kind == "range" and (self.minimum is None or self.maximum is None):
            raise ValueError("a range quantity carries min and max")
        if self.kind == "tolerance" and (self.nominal is None or self.tolerance is None):
            raise ValueError("a tolerance quantity carries nominal and a tolerance")

    # -- constructors ------------------------------------------------------

    @classmethod
    def scalar(cls, value: str | Decimal | int, unit: str | Unit, **kwargs) -> "Quantity":
        return cls("scalar", _unit(unit), value=_decimal(value), **kwargs)

    @classmethod
    def range(
        cls,
        minimum: str | Decimal | int,
        maximum: str | Decimal | int,
        unit: str | Unit,
        typical: str | Decimal | int | None = None,
        **kwargs,
    ) -> "Quantity":
        return cls(
            "range",
            _unit(unit),
            minimum=_decimal(minimum),
            maximum=_decimal(maximum),
            typical=None if typical is None else _decimal(typical),
            **kwargs,
        )

    @classmethod
    def with_tolerance(
        cls,
        nominal: str | Decimal | int,
        tolerance: str | Decimal | int,
        unit: str | Unit,
        kind: ToleranceKind = "relative",
        **kwargs,
    ) -> "Quantity":
        return cls(
            "tolerance",
            _unit(unit),
            nominal=_decimal(nominal),
            tolerance=Tolerance(kind, _decimal(tolerance)),
            **kwargs,
        )

    # -- semantics ---------------------------------------------------------

    @property
    def dimension(self) -> Dimension:
        return self.unit.dimension

    def interval(self) -> tuple[Decimal, Decimal]:
        """The closed interval this quantity covers, in SI base units.

        Comparison has interval semantics, so every comparison goes through here
        rather than through a single representative value.
        """
        with _ctx():
            if self.kind == "scalar":
                low = high = self._to_base(self.value)
            elif self.kind == "range":
                low, high = self._to_base(self.minimum), self._to_base(self.maximum)
            else:
                nominal = self.nominal
                if self.tolerance.kind == "relative":
                    delta = abs(nominal) * self.tolerance.value
                else:
                    delta = self.tolerance.value
                low = self._to_base(nominal - delta)
                high = self._to_base(nominal + delta)
            return (low, high) if low <= high else (high, low)

    def _to_base(self, magnitude: Decimal) -> Decimal:
        with _ctx():
            return magnitude * self.unit.factor + self.unit.offset

    def converted_to(self, unit: str | Unit) -> tuple["Quantity", bool]:
        """Convert to a comparable unit.

        Returns the converted quantity and whether the conversion was exact. The
        spec requires exactness where the factor is exact and a recorded rounding
        where it is not, so the caller is handed the fact rather than a silent
        result.
        """
        target = _unit(unit)
        if target.dimension != self.dimension:
            raise error(
                UNIT_DIMENSION_MISMATCH,
                f"cannot convert {self.unit} to {target}: "
                f"{self.dimension} is not {target.dimension}",
            )

        def convert(magnitude: Decimal | None) -> tuple[Decimal | None, bool]:
            if magnitude is None:
                return None, True
            with _ctx():
                base = magnitude * self.unit.factor + self.unit.offset
                result = (base - target.offset) / target.factor
                # Exact when multiplying back reproduces the input exactly.
                round_trip = result * target.factor + target.offset
                return result, round_trip == base

        exact = True
        fields: dict[str, Decimal | None] = {}
        for name in ("value", "minimum", "maximum", "typical", "nominal"):
            converted, was_exact = convert(getattr(self, name))
            fields[name] = converted
            exact = exact and was_exact

        tolerance = self.tolerance
        if tolerance is not None and tolerance.kind == "absolute":
            with _ctx():
                scaled = tolerance.value * self.unit.factor / target.factor
            tolerance = Tolerance("absolute", scaled)

        return (
            Quantity(
                self.kind,
                target,
                tolerance=tolerance,
                conditions=self.conditions,
                **fields,
            ),
            exact,
        )

    def as_dict(self) -> dict:
        out: dict = {"kind": self.kind, "unit": self.unit.symbol}
        for name, key in (
            ("value", "value"),
            ("minimum", "min"),
            ("maximum", "max"),
            ("typical", "typical"),
            ("nominal", "nominal"),
        ):
            magnitude = getattr(self, name)
            if magnitude is not None:
                out[key] = _decimal_str(magnitude)
        if self.tolerance is not None:
            out["tolerance"] = self.tolerance.as_dict()
        if self.conditions:
            out["conditions"] = dict(self.conditions)
        return out

    def __str__(self) -> str:
        if self.kind == "scalar":
            return f"{_decimal_str(self.value)} {self.unit}"
        if self.kind == "range":
            return f"{_decimal_str(self.minimum)}..{_decimal_str(self.maximum)} {self.unit}"
        return f"{_decimal_str(self.nominal)} +/- {_decimal_str(self.tolerance.value)} {self.unit}"


def _unit(unit: str | Unit) -> Unit:
    return unit if isinstance(unit, Unit) else Unit.parse(unit)


def _decimal(value: str | Decimal | int) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        raise TypeError(
            "a magnitude is a decimal string, not binary floating point; "
            f"pass {value!r} as a string"
        )
    return Decimal(str(value))


def _decimal_str(value: Decimal) -> str:
    """Render a Decimal as its canonical decimal string.

    Normalizes away exponent notation for ordinary magnitudes so that the same
    number always serializes the same way, without changing its value.
    """
    if value == value.to_integral_value() and abs(value.as_tuple().exponent) < 20:
        text = str(value.quantize(Decimal(1)))
    else:
        text = format(value.normalize(), "f")
    return "0" if text in ("-0", "0E+0") else text


def require_same_dimension(left: Quantity, right: Quantity, operation: str) -> None:
    """Reject operands of unequal dimension where the operation is written."""
    if left.dimension != right.dimension:
        raise error(
            UNIT_DIMENSION_MISMATCH,
            f"{operation} requires operands of equal dimension: "
            f"{left.unit} is {left.dimension}, {right.unit} is {right.dimension}",
        )
