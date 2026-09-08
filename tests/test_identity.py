"""Spec: Stable Entity Identity; Canonical Semantic Paths; Renames."""

import uuid

import pytest

from fang.diagnostics import FangError
from fang.identity import (
    Origin,
    Path,
    ROOT_NAMESPACE,
    derive,
    derive_uuid,
    imported,
    project_namespace,
    transliterate,
    transliterate_siblings,
)


def test_derived_identity_is_uuid5_over_the_fixed_root_namespace():
    assert ROOT_NAMESPACE == uuid.UUID("453c7e27-7e71-4d31-af3e-9da6714fc2ba")
    expected = uuid.uuid5(
        project_namespace("PRJ-1"), "component:system.power.buck_3v3.U1"
    )
    assert derive_uuid("PRJ-1", "component", "system.power.buck_3v3.U1") == expected


def test_the_short_form_is_twelve_hex_digits_and_the_full_uuid_is_recorded():
    identity = derive("PRJ-1", "component", "system.power.buck_3v3.U1")
    assert identity.id.startswith("CMP-")
    assert len(identity.id.split("-", 1)[1]) == 12
    assert identity.uuid is not None
    assert identity.id.split("-", 1)[1] == identity.uuid.hex[:12]
    assert identity.origin is Origin.DERIVED


def test_the_same_project_state_yields_the_same_identifier_on_every_run():
    first = derive("PRJ-1", "component", "system.power.buck_3v3.U1")
    second = derive("PRJ-1", "component", "system.power.buck_3v3.U1")
    assert first.id == second.id and first.uuid == second.uuid


def test_a_short_form_collision_is_lengthened_four_digits_at_a_time():
    base = derive("PRJ-1", "component", "system.power.buck_3v3.U1")
    lengthened = derive("PRJ-1", "component", "system.power.buck_3v3.U1", taken={base.id})
    assert len(lengthened.id.split("-", 1)[1]) == 16
    # Lengthening is a function of the identifier set alone, so it reproduces.
    again = derive("PRJ-1", "component", "system.power.buck_3v3.U1", taken={base.id})
    assert again.id == lengthened.id


def test_a_collision_surviving_the_whole_uuid_is_rejected():
    identity = derive("PRJ-1", "component", "system.power.buck_3v3.U1")
    taken = {
        f"CMP-{identity.uuid.hex[:digits]}" for digits in range(12, 33, 4)
    }
    with pytest.raises(FangError) as caught:
        derive("PRJ-1", "component", "system.power.buck_3v3.U1", taken=taken)
    assert caught.value.diagnostic.code == "ELAB-0002"


def test_identity_is_not_derived_from_declaration_order_or_coordinates():
    ordered = [derive("PRJ-1", "component", f"system.x.u{i}") for i in range(3)]
    reversed_order = [derive("PRJ-1", "component", f"system.x.u{i}") for i in (2, 1, 0)]
    assert {i.id for i in ordered} == {i.id for i in reversed_order}


def test_a_path_may_begin_with_a_digit_and_carry_a_bracketed_index():
    assert str(Path.parse("system.power.3v3")) == "system.power.3v3"
    assert str(Path.parse("system.power.feedback[0]")) == "system.power.feedback[0]"


def test_a_malformed_path_is_rejected():
    for bad in ("", ".leading", "trailing.", "a..b", "a.b c"):
        with pytest.raises(FangError):
            Path.parse(bad)


def test_transliteration_follows_the_specified_steps():
    assert transliterate("Bücher/Test Name.1") == "bu_cher_test_name_1"
    assert transliterate("///") == "x"
    assert transliterate("__a__b__") == "a_b"


def test_the_sibling_tie_break_takes_originals_in_code_point_order():
    result = transliterate_siblings(["A/b", "A b", "zzz"])
    # "A b" sorts before "A/b" by code point, so it keeps the bare form.
    assert result["A b"] == "a_b"
    assert result["A/b"] == "a_b_2"
    assert result["zzz"] == "zzz"
    # The result is a function of the set, not of the order supplied.
    assert transliterate_siblings(["zzz", "A/b", "A b"]) == result


def test_an_explicit_key_pins_identity_across_a_rename():
    before = derive("PRJ-1", "component", "system.power.regulator", key="buck_main")
    after = derive("PRJ-1", "component", "system.power.renamed_part", key="buck_main")
    assert before.id == after.id


def test_an_external_identifier_never_becomes_canonical_identity():
    identity = imported("CMP-imported-1", external_id="/kicad/uuid/abc")
    assert identity.external_id == "/kicad/uuid/abc"
    assert identity.id != identity.external_id
    with pytest.raises(ValueError):
        from fang.identity import Identity

        Identity("CMP-x", Origin.IMPORTED)
