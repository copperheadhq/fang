"""Spec: Deterministic Canonical Serialization, as copperhead RFC 3 version 1.6
Section 17.1 fixes it.

The conformance fixtures are the example records RFC 11 version 1.4 Section
6.13 publishes (tests/fixtures/rfc11/). They cite one another by content hash:
a layout input keys its footprint definitions by hash, a candidate names its
layout input, a placement diff its two sides, a set of layout operations its
candidate. The RFC repository's checker computed every cited hash, so the
kernel's encoder conforms only if it reproduces each one.
"""

import json
import math
from pathlib import Path

import pytest

from fang.serialization import NotCanonicalizable, canonical_dumps, content_hash

RFC11 = Path(__file__).parent / "fixtures" / "rfc11"
HASH_FIELDS = frozenset({"input", "layout", "candidate"})


def _example(name: str) -> dict:
    return json.loads((RFC11 / name).read_text())


def _single_record_examples() -> dict[str, dict]:
    return {p.name: json.loads(p.read_text()) for p in sorted(RFC11.glob("*.json"))}


def _cited(node, out=None):
    out = [] if out is None else out
    if isinstance(node, dict):
        for key, value in node.items():
            if key in HASH_FIELDS and isinstance(value, str) and value.startswith("sha256:"):
                out.append((key, value))
            else:
                _cited(value, out)
    elif isinstance(node, list):
        for value in node:
            _cited(value, out)
    return out


# --------------------------------------------------------------------------
# The published examples


def test_a_footprint_is_keyed_by_the_hash_of_its_definition():
    for name in ("layout-input.ldo-board.json", "layout-input.ldo-placed.json"):
        footprints = _example(name)["footprints"]
        assert footprints
        for key, definition in footprints.items():
            assert content_hash(definition) == key, f"{name}: {key}"


def test_every_hash_an_example_cites_is_the_hash_of_an_example():
    examples = _single_record_examples()
    hashes = {content_hash(record) for record in examples.values()}
    cited = [(name, key, value) for name, record in examples.items()
             for key, value in _cited(record)]
    assert len(cited) >= 8
    missing = [c for c in cited if c[2] not in hashes]
    assert not missing


def test_the_named_citations_hold():
    layout_input = content_hash(_example("layout-input.ldo-board.json"))
    candidate = content_hash(_example("candidate.ldo-board.json"))
    assert _example("snapshot.ldo-board.json")["input"] == layout_input
    assert _example("candidate.ldo-board.json")["input"] == layout_input
    diff = _example("placement-diff.ldo-board.json")
    assert diff["before"] == {"input": layout_input}
    assert diff["after"] == {"candidate": candidate}
    ops = _example("layout-ops.ldo-board.json")
    assert (ops["input"], ops["candidate"]) == (layout_input, candidate)
    route = _example("layout-ops.ldo-route.json")
    assert route["candidate"] == content_hash(_example("candidate.ldo-route.json"))


# --------------------------------------------------------------------------
# The rules the examples exercise


def test_an_item_without_an_identifier_sorts_by_its_whole_serialization():
    first = {"code": "PLC-0001", "message": "b"}
    second = {"code": "PLC-0001", "message": "a"}
    assert canonical_dumps({"findings": [first, second]}) == canonical_dumps(
        {"findings": [second, first]}
    )
    assert content_hash({"findings": [first, second]}) == content_hash(
        {"findings": [second, first]}
    )


def test_an_entity_sorts_by_its_identifier_and_no_other_field():
    later = {"id": "CMP-b", "name": "a"}
    earlier = {"id": "CMP-a", "name": "z"}
    assert canonical_dumps([later, earlier]).index("CMP-a") < canonical_dumps(
        [later, earlier]
    ).index("CMP-b")


@pytest.mark.parametrize(
    ("value", "text"),
    [
        (2.0, "2"),
        (0.5, "0.5"),
        (0.1, "0.1"),
        (-0.0, "0"),
        (1e-07, "0.0000001"),
        (1e16, "10000000000000000"),
        (-2.5e-05, "-0.000025"),
        (1.25, "1.25"),
    ],
)
def test_a_bare_number_is_the_shortest_decimal_written_positionally(value, text):
    assert canonical_dumps(value) == text
    assert float(text) == value


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan])
def test_a_non_finite_number_has_no_canonical_serialization(value):
    with pytest.raises(NotCanonicalizable):
        canonical_dumps({"metric": value})


@pytest.mark.parametrize("key", ["outline", "layers", "preserved", "phases", "order"])
def test_the_layout_records_ordered_collections_keep_their_order(key):
    forward = {key: [{"r": 2}, {"r": 1}]}
    backward = {key: [{"r": 1}, {"r": 2}]}
    assert canonical_dumps(forward) != canonical_dumps(backward)
    assert canonical_dumps(forward).index('"r":2') < canonical_dumps(forward).index('"r":1')
