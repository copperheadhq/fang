"""Spec: Deterministic Canonical Serialization."""

import subprocess
import sys
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from fang.serialization import (
    canonical_bytes,
    canonical_dumps,
    canonical_record_stream,
    content_hash,
    read_record_stream,
    rfc3339,
)


def test_mapping_keys_sort_ascending_by_code_point():
    assert canonical_dumps({"b": 1, "A": 2, "a": 3}) == '{"A":2,"a":3,"b":1}'


def test_unordered_collections_sort_by_entity_id():
    payload = {"components": [{"id": "CMP-z"}, {"id": "CMP-a"}]}
    assert canonical_dumps(payload) == '{"components":[{"id":"CMP-a"},{"id":"CMP-z"}]}'


def test_a_collection_whose_order_carries_meaning_keeps_its_order():
    payload = {"provenance": [{"id": "z"}, {"id": "a"}], "rationale": ["second", "first"]}
    rendered = canonical_dumps(payload)
    assert '"provenance":[{"id":"z"},{"id":"a"}]' in rendered
    assert '"rationale":["second","first"]' in rendered


def test_a_magnitude_serializes_as_a_decimal_string():
    assert canonical_dumps({"v": Decimal("3.3")}) == '{"v":"3.3"}'
    assert canonical_dumps({"v": Decimal("3.30")}) == '{"v":"3.3"}'


def test_timestamps_are_rfc3339_utc_with_a_trailing_z():
    moment = datetime(2026, 9, 8, 11, 4, 22, tzinfo=timezone.utc)
    assert rfc3339(moment) == "2026-09-08T11:04:22Z"
    assert canonical_dumps({"t": moment}) == '{"t":"2026-09-08T11:04:22Z"}'


def test_a_naive_timestamp_is_refused():
    with pytest.raises(Exception):
        rfc3339(datetime(2026, 9, 8))


def test_canonical_bytes_are_utf8_lf_and_one_trailing_newline():
    data = canonical_bytes({"a": 1})
    assert data == b'{"a":1}\n'
    assert not data.startswith(b"\xef\xbb\xbf")
    assert data.count(b"\n") == 1
    assert b"\r" not in data


def test_strings_are_normalized_to_form_c():
    composed = canonical_dumps({"n": "é"})     # e + combining acute
    precomposed = canonical_dumps({"n": "é"})   # é
    assert composed == precomposed


def test_reserializing_unchanged_state_is_byte_identical():
    payload = {"b": [3, 1, 2], "a": {"y": Decimal("1.0"), "x": "s"}}
    assert canonical_bytes(payload) == canonical_bytes(payload)


def test_the_record_stream_is_one_object_per_line_ordered_by_id():
    stream = canonical_record_stream([{"id": "B", "x": 1}, {"id": "A", "y": 2}])
    assert stream == b'{"id":"A","y":2}\n{"id":"B","x":1}\n'
    assert len(stream.splitlines()) == 2


def test_the_logical_root_is_reconstructible_from_the_stream():
    records = [{"id": "A", "kind": "net"}, {"id": "B", "kind": "component"}]
    recovered = read_record_stream(canonical_record_stream(records))
    assert sorted(recovered, key=lambda r: r["id"]) == sorted(records, key=lambda r: r["id"])


def test_no_environment_derived_value_appears_in_output():
    import os

    rendered = canonical_dumps({"a": 1, "b": "text"})
    for leak in (os.getcwd(), str(os.getpid())):
        assert leak not in rendered


def test_byte_identity_holds_across_processes():
    # A single interpreter run can hide hash-order dependence; a second process
    # with a different hash seed cannot.
    script = (
        "from decimal import Decimal;"
        "from fang.serialization import canonical_bytes;"
        "import sys;"
        "sys.stdout.buffer.write(canonical_bytes("
        "{'z':1,'a':[{'id':'b'},{'id':'a'}],'q':Decimal('3.30')}))"
    )
    runs = {
        subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
            check=True,
        ).stdout
        for seed in ("0", "1", "12345")
    }
    assert len(runs) == 1


def test_content_hash_is_stable_for_unchanged_state():
    payload = {"id": "A", "v": Decimal("1.5")}
    assert content_hash(payload) == content_hash(dict(payload))
