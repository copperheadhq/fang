"""Stable identity: canonical semantic paths and derived identifiers.

Spec: "Stable Entity Identity", "Canonical Semantic Paths", and "Renames
Preserve Identity Through Explicit Keys".

Nothing here reads the clock, the host, the process, or iteration order. A
derived identifier is a pure function of the project identifier, the entity
kind, the canonical semantic path, and — for collision lengthening only — the
revision's identifier set.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping, Sequence

from .diagnostics import ELAB_PATH_COLLISION, ELAB_PATH_INVALID, error

#: The fixed Copperhead EIR root namespace.
ROOT_NAMESPACE = uuid.UUID("453c7e27-7e71-4d31-af3e-9da6714fc2ba")

#: The short form is the first twelve hex digits, lengthened four at a time.
SHORT_FORM_DIGITS = 12
LENGTHEN_STEP = 4

_NAME = re.compile(r"^[A-Za-z0-9_]+$")
_SEGMENT = re.compile(r"^([A-Za-z0-9_]+)(?:\[(\d+)\])?$")


class Origin(Enum):
    """Where an entity's identity came from. Exactly one, and it is recorded."""

    AUTHORED = "authored"   # assigned by a human or carried in from a document
    DERIVED = "derived"     # computed by elaboration or generation
    IMPORTED = "imported"   # recovered from an external file


#: Entity kind to identifier prefix. The kind is also what goes into the derived
#: name, as the lowercase singular before the colon.
PREFIXES: Mapping[str, str] = {
    "requirement": "REQ",
    "assumption": "ASM",
    "decision": "DEC",
    "alternative": "ALT",
    "block": "BLK",
    "component": "CMP",
    "pin": "PIN",
    "net": "NET",
    "circuit": "CKT",
    "rail": "RAIL",
    "interface": "IF",
    "port": "PORT",
    "bus": "BUS",
    "domain": "DOM",
    "topology": "TOPO",
    "model": "MOD",
    "board": "PCB",
    "region": "REGION",
    "constraint": "RULE",
    "finding": "FIND",
    "artifact": "ART",
    "evidence": "EVD",
    "source": "SRC",
    "test": "TEST",
    "outcome": "OUTCOME",
    "calculation": "CALC",
    "waiver": "WVR",
    "verification": "VER",
}


# --------------------------------------------------------------------------
# Canonical semantic paths
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Segment:
    """One path segment: a name, optionally with a bracketed index."""

    name: str
    index: int | None = None

    def __post_init__(self) -> None:
        if not _NAME.match(self.name):
            raise error(
                ELAB_PATH_INVALID,
                f"segment name {self.name!r} is outside the grammar; "
                "transliterate it before it becomes a path",
            )
        if self.index is not None and self.index < 0:
            raise error(ELAB_PATH_INVALID, "a segment index is a non-negative integer")

    def __str__(self) -> str:
        return self.name if self.index is None else f"{self.name}[{self.index}]"


@dataclass(frozen=True)
class Path:
    """A canonical semantic path.

    It names an entity by its position in the engineering structure, not in a
    file. The grammar admits no escape sequence, so no two distinct names can be
    written as one path.
    """

    segments: tuple[Segment, ...]

    def __post_init__(self) -> None:
        if not self.segments:
            raise error(ELAB_PATH_INVALID, "a path has at least one segment")

    @classmethod
    def parse(cls, text: str) -> "Path":
        if not text or text.startswith(".") or text.endswith(".") or ".." in text:
            raise error(ELAB_PATH_INVALID, f"path {text!r} is not well formed")
        segments = []
        for raw in text.split("."):
            match = _SEGMENT.match(raw)
            if match is None:
                raise error(
                    ELAB_PATH_INVALID, f"path segment {raw!r} is not well formed"
                )
            name, index = match.group(1), match.group(2)
            segments.append(Segment(name, int(index) if index is not None else None))
        return cls(tuple(segments))

    def child(self, name: str, index: int | None = None) -> "Path":
        return Path(self.segments + (Segment(name, index),))

    @property
    def parent(self) -> "Path | None":
        return Path(self.segments[:-1]) if len(self.segments) > 1 else None

    @property
    def leaf(self) -> Segment:
        return self.segments[-1]

    def __str__(self) -> str:
        return ".".join(str(segment) for segment in self.segments)


def transliterate(name: str) -> str:
    """Steps 1 to 6 of the transliteration the spec fixes.

    The sibling tie-break of step 7 needs the whole sibling set and lives in
    `transliterate_siblings`.
    """
    text = unicodedata.normalize("NFKD", name).lower()
    text = "".join(c if ("a" <= c <= "z" or "0" <= c <= "9" or c == "_") else "_" for c in text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "x"


def transliterate_siblings(names: Sequence[str]) -> dict[str, str]:
    """Transliterate a set of siblings, applying the step 7 tie-break.

    Where two originals transliterate to the same form, the colliding siblings
    are taken in ascending order of their original names by Unicode code point:
    the first keeps the bare form and the rest get ``_2``, ``_3``, and so on. The
    result is therefore a function of the sibling set alone, not of the order the
    caller happened to supply.
    """
    grouped: dict[str, list[str]] = {}
    for name in names:
        grouped.setdefault(transliterate(name), []).append(name)

    result: dict[str, str] = {}
    for base, originals in grouped.items():
        for position, original in enumerate(sorted(originals)):
            result[original] = base if position == 0 else f"{base}_{position + 1}"
    return result


# --------------------------------------------------------------------------
# Derived identifiers
# --------------------------------------------------------------------------


def project_namespace(project_id: str) -> uuid.UUID:
    """UUIDv5 of the fixed root namespace and the project identifier."""
    return uuid.uuid5(ROOT_NAMESPACE, project_id)


def derive_uuid(project_id: str, kind: str, path: Path | str) -> uuid.UUID:
    """UUIDv5 of the project namespace and ``<entity-kind>:<canonical path>``."""
    return uuid.uuid5(project_namespace(project_id), f"{kind}:{path}")


def short_form(prefix: str, value: uuid.UUID, digits: int = SHORT_FORM_DIGITS) -> str:
    return f"{prefix}-{value.hex[:digits]}"


@dataclass(frozen=True)
class Identity:
    """An entity's identity, with the origin that produced it recorded.

    References carry ``id``. An authored identity has no uuid, and an imported
    one pairs a canonical identifier with an external mapping, so ``id`` is the
    only reference key the three origins share — which is why it must be unique
    within a revision across every origin.
    """

    id: str
    origin: Origin
    path: Path | None = None
    uuid: uuid.UUID | None = None
    key: str | None = None                 # explicit key, if identity is pinned
    external_id: str | None = None         # imported entities only
    display_name: str | None = None

    def __post_init__(self) -> None:
        if self.origin is Origin.DERIVED:
            if self.uuid is None or self.path is None:
                raise ValueError(
                    "a derived identity records the full uuid and the path it "
                    "was derived from; that is what makes the short form "
                    "reproducible"
                )
        if self.origin is Origin.IMPORTED and self.external_id is None:
            raise ValueError(
                "an imported identity records its external identifier in an "
                "explicit mapping; the external identifier never becomes the "
                "canonical one"
            )

    def as_dict(self) -> dict:
        out: dict = {"id": self.id, "origin": self.origin.value}
        if self.path is not None:
            out["path"] = str(self.path)
        if self.uuid is not None:
            out["uuid"] = str(self.uuid)
        if self.key is not None:
            out["key"] = self.key
        if self.external_id is not None:
            out["external_id"] = self.external_id
        if self.display_name is not None:
            out["display_name"] = self.display_name
        return out


def derive(
    project_id: str,
    kind: str,
    path: Path | str,
    *,
    taken: Iterable[str] = (),
    key: str | None = None,
    display_name: str | None = None,
) -> Identity:
    """Derive an identity, lengthening the short form only as far as it must.

    ``taken`` is the revision's existing identifier set. Lengthening is a
    function of that set alone, so re-deriving the same project state reproduces
    the same lengths.
    """
    if kind not in PREFIXES:
        raise ValueError(f"no identifier prefix is allocated for entity kind {kind!r}")

    derivation_path = Path.parse(str(path)) if not isinstance(path, Path) else path
    if key is not None:
        # An explicit key replaces the leaf name in the path used for derivation,
        # so a rename of the entity leaves the identity untouched.
        parent = derivation_path.parent
        pinned = Segment(key, derivation_path.leaf.index)
        derivation_path = Path((parent.segments if parent else ()) + (pinned,))

    value = derive_uuid(project_id, kind, derivation_path)
    prefix = PREFIXES[kind]
    existing = set(taken)

    digits = SHORT_FORM_DIGITS
    while digits <= 32:
        candidate = short_form(prefix, value, digits)
        if candidate not in existing:
            return Identity(
                candidate,
                Origin.DERIVED,
                path=derivation_path,
                uuid=value,
                key=key,
                display_name=display_name,
            )
        digits += LENGTHEN_STEP

    raise error(
        ELAB_PATH_COLLISION,
        f"the whole uuid for {kind}:{derivation_path} collides with an existing "
        "identifier, which means two entities share a path",
    )


def authored(id: str, *, display_name: str | None = None) -> Identity:
    """An identity assigned by a human or carried in from a source document."""
    return Identity(id, Origin.AUTHORED, display_name=display_name)


def imported(
    id: str, external_id: str, *, path: Path | None = None, display_name: str | None = None
) -> Identity:
    """An identity recovered from an external file, with its mapping recorded."""
    return Identity(
        id, Origin.IMPORTED, path=path, external_id=external_id, display_name=display_name
    )
