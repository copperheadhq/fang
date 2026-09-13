"""Decoding serialized records back into typed state.

Spec: "A Persisted Snapshot Reloads Without Running A Program". Every type's
`from_dict` sits beside its `as_dict`; these are the rules they share, so each
decoder refuses to guess in the same two ways. A key the decoder does not model
leaves the record untyped rather than silently dropped, and a field that is
missing or of the wrong type makes the record malformed.

This module imports nothing from the package, so the lowest modules can use it.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Iterable, Mapping, TypeVar

E = TypeVar("E", bound=Enum)


class UnmodelledKeys(ValueError):
    """A record carries a key its decoder does not model.

    The whole record is then kept verbatim rather than decoded without the key,
    because dropping a key would change the bytes the record serializes to.
    """

    def __init__(self, where: str, keys: Iterable[str]) -> None:
        self.where = where
        self.keys = tuple(sorted(keys))
        super().__init__(
            f"{where} carries {', '.join(self.keys)}, which its decoder does not model"
        )


class MalformedRecord(ValueError):
    """A record that cannot be decoded: a field is missing or is not what it must be."""

    def __init__(self, field: str, detail: str) -> None:
        self.field = field
        self.detail = detail
        super().__init__(f"{field}: {detail}")


def expect_keys(record: Any, allowed: Iterable[str], where: str) -> Mapping[str, Any]:
    """Refuse a record that is not an object, or that carries a key outside `allowed`."""
    if not isinstance(record, Mapping):
        raise MalformedRecord(where, f"expected an object, found {type(record).__name__}")
    unknown = set(record) - set(allowed)
    if unknown:
        raise UnmodelledKeys(where, unknown)
    return record


def required(record: Mapping[str, Any], key: str, field: str | None = None) -> Any:
    if key not in record:
        raise MalformedRecord(field or key, "a required field is missing")
    return record[key]


def text(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise MalformedRecord(field, f"expected a string, found {type(value).__name__}")
    return value


def optional_text(record: Mapping[str, Any], key: str, field: str | None = None) -> str | None:
    """A string an `as_dict` writes only when it is set."""
    return text(record[key], field or key) if key in record else None


def listed(value: Any, field: str) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise MalformedRecord(field, f"expected a list, found {type(value).__name__}")
    return tuple(value)


def texts(value: Any, field: str) -> tuple[str, ...]:
    return tuple(text(item, field) for item in listed(value, field))


def text_mapping(value: Any, field: str) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise MalformedRecord(field, f"expected an object, found {type(value).__name__}")
    return {text(key, field): text(item, field) for key, item in value.items()}


def boolean(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise MalformedRecord(field, f"expected true or false, found {type(value).__name__}")
    return value


def integer(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise MalformedRecord(field, f"expected an integer, found {type(value).__name__}")
    return value


def decimal(value: Any, field: str) -> Decimal:
    """A magnitude, which serializes as a decimal string and never as a float."""
    if not isinstance(value, str):
        raise MalformedRecord(field, f"expected a decimal string, found {type(value).__name__}")
    try:
        return Decimal(value)
    except InvalidOperation:
        raise MalformedRecord(field, f"{value!r} is not a decimal") from None


def member(enum: type[E], value: Any, field: str) -> E:
    try:
        return enum(value)
    except (ValueError, TypeError):
        raise MalformedRecord(field, f"{value!r} is not a {enum.__name__} value") from None


def freeze(value: Any) -> Any:
    """JSON arrays back to the tuples the kernel builds, at every depth."""
    if isinstance(value, Mapping):
        return {key: freeze(item) for key, item in value.items()}
    if isinstance(value, list):
        return tuple(freeze(item) for item in value)
    return value
