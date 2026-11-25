"""Deterministic canonical serialization.

Spec: "Deterministic Canonical Serialization". Reserializing unchanged state
produces byte-identical output, on any machine and in any process. This module
is the only path to serialized output, so the guarantee lives in one place
rather than in every caller's discipline.
"""

from __future__ import annotations

import hashlib
import math
import unicodedata
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

from .units import _decimal_str

#: Collections whose order carries engineering meaning and is therefore
#: preserved rather than sorted. Everything else is an unordered collection,
#: sorted as ``_entity_sort_key`` says. The schema states which collections
#: these are, so this table is the schema's statement of it; the layout
#: records' ordered keys are those of copperhead RFC 11 Section 6.13.
ORDERED_COLLECTIONS: frozenset[str] = frozenset(
    {
        # RFC 3 Section 17.1: order is declared by key, and the set is the
        # union each standard states. An encoder orders exactly this set.
        "provenance",              # RFC 3 14: oldest first; append-only
        "rationale",               # RFC 3 13: a decision's argument
        "alternatives_rejected",   # RFC 3 13: the options it set aside
        "args",                    # RFC 3 11.3: an expression's operands
        "power_sequence",          # RFC 3 9.2: a rail's power-up order
        "branches",                # RFC 12: a topology constraint's branches
        "calls",                   # RFC 12: a tool plan's calls
        "outline",                 # RFC 11 6.13: a ring's points
        "layers",                  # RFC 11 6.13: a stackup, top to bottom
        "preserved",               # RFC 11 6.13: verbatim records, file order
    }
)

_ESCAPES = {
    '"': '\\"',
    "\\": "\\\\",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
    "\b": "\\b",
    "\f": "\\f",
}


class NotCanonicalizable(TypeError):
    """A value that has no deterministic serialization."""


def rfc3339(moment: datetime) -> str:
    """RFC3339 in UTC with a trailing Z."""
    if moment.tzinfo is None:
        raise NotCanonicalizable(
            "a timestamp carries a timezone; a naive datetime is ambiguous"
        )
    moment = moment.astimezone(timezone.utc)
    if moment.microsecond:
        return moment.strftime("%Y-%m-%dT%H:%M:%S.%f").rstrip("0") + "Z"
    return moment.strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def _encode_string(text: str) -> str:
    """Encode a string in Unicode normalization form C, with escapes."""
    text = unicodedata.normalize("NFC", text)
    out = ['"']
    for char in text:
        if char in _ESCAPES:
            out.append(_ESCAPES[char])
        elif ord(char) < 0x20:
            out.append(f"\\u{ord(char):04x}")
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def _sort_key(key: str) -> tuple[int, ...]:
    """Ascending by Unicode code point, independent of locale."""
    return tuple(ord(c) for c in unicodedata.normalize("NFC", key))


def _entity_sort_key(item: Any) -> tuple[int, ...]:
    """The sort key of an item in an unordered collection (RFC 3 Section 17.1).

    An entity sorts by its identifier, and every other item, a string
    included, by its canonical serialization. No other field is a sort key:
    sorting by a shared ``code`` or ``name`` left equal keys in input order,
    so one collection could serialize, and hash, two ways. Identifiers are
    unique within a revision (RFC 3 Section 4.2), so an entity's key never
    ties."""
    payload = item.as_dict() if hasattr(item, "as_dict") else item
    if isinstance(payload, Mapping) and isinstance(payload.get("id"), str):
        return _sort_key(payload["id"])
    return _sort_key(canonical_dumps(payload))


def _encode_number(value: float) -> str:
    """A bare number: the shortest decimal that round-trips to the same value,
    written positionally, with no exponent, no trailing zeros after the point,
    no point when the value is whole, and zero as 0 (RFC 3 Section 17.1).
    ``repr`` gives the shortest digits; the notation is fixed so that an
    encoder in any language writes the same bytes."""
    if not math.isfinite(value):
        raise NotCanonicalizable(f"{value!r} has no canonical serialization")
    if value == 0:
        return "0"
    text = format(Decimal(repr(value)), "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _encode(value: Any, *, ordered: bool) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _encode_string(value)
    if isinstance(value, Decimal):
        return _encode_string(_decimal_str(value))
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        # A physical magnitude never arrives here; it is a Decimal string.
        return _encode_number(value)
    if isinstance(value, datetime):
        return _encode_string(rfc3339(value))
    if isinstance(value, Mapping):
        items = sorted(value.items(), key=lambda kv: _sort_key(kv[0]))
        body = ",".join(
            f"{_encode_string(k)}:{_encode(v, ordered=k in ORDERED_COLLECTIONS)}"
            for k, v in items
        )
        return "{" + body + "}"
    if isinstance(value, (list, tuple)):
        entries = list(value)
        if not ordered:
            entries = sorted(entries, key=_entity_sort_key)
        return "[" + ",".join(_encode(v, ordered=False) for v in entries) + "]"
    if hasattr(value, "as_dict"):
        return _encode(value.as_dict(), ordered=ordered)

    raise NotCanonicalizable(
        f"{type(value).__name__} has no canonical serialization; "
        "give it an as_dict() or convert it before serializing"
    )


def canonical_dumps(value: Any, *, ordered: bool = False) -> str:
    """Serialize to canonical JSON text, with no trailing newline."""
    return _encode(value, ordered=ordered)


def canonical_bytes(value: Any) -> bytes:
    """Serialize to canonical JSON bytes: UTF-8, no BOM, LF, one trailing newline."""
    return (canonical_dumps(value) + "\n").encode("utf-8")


def canonical_record_stream(records: Iterable[Any]) -> bytes:
    """The canonical record stream.

    One canonically serialized object per line, ordered ascending by entity id,
    with no framing that varies between runs.
    """
    rendered = []
    for record in records:
        payload = record.as_dict() if hasattr(record, "as_dict") else record
        rendered.append((_entity_sort_key(payload), canonical_dumps(payload)))
    rendered.sort(key=lambda pair: pair[0])
    if not rendered:
        return b""
    return ("\n".join(line for _, line in rendered) + "\n").encode("utf-8")


def read_record_stream(data: bytes) -> list[dict]:
    """Read a record stream back. The logical root is reconstructible from it."""
    import json

    text = data.decode("utf-8")
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def content_hash(value: Any) -> str:
    """A content address for a snapshot, over its canonical bytes."""
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()
