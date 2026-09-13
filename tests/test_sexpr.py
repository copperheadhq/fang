"""Spec: External Adapters Report Loss (the reader half)."""

import pytest

from fang.sexpr import Atom, Node, SExprError, parse, tokenize


def test_a_simple_list_parses():
    node = parse('(comp (ref "R1") (value "10k"))')
    assert node.head == "comp"
    assert node.value("ref") == "R1"
    assert node.value("value") == "10k"


def test_quoted_strings_keep_their_content_and_escapes():
    node = parse(r'(value "a \"quoted\" value")')
    assert node.value is not None
    assert node.atoms() == ['a "quoted" value']


def test_backslashes_are_unescaped():
    node = parse(r'(path "C:\\lib")')
    assert node.atoms() == ["C:\\lib"]


def test_unquoted_atoms_are_preserved():
    node = parse("(version E)")
    assert node.atoms() == ["E"]


def test_comments_are_ignored():
    node = parse('(comp ; this is a comment\n (ref "R1"))')
    assert node.value("ref") == "R1"


def test_nested_lists_are_reachable_by_head():
    node = parse('(export (design (source "a.py")) (components (comp (ref "R1"))))')
    assert node.child("design").value("source") == "a.py"
    assert len(node.child("components").children("comp")) == 1


def test_key_value_pairs_are_readable():
    node = parse('(node "ref" "R1" "pin" "2")')
    assert node.pairs() == {"ref": "R1", "pin": "2"}


def test_nested_fields_are_read_as_pairs():
    """KiCad writes each field as a list of its own."""
    node = parse('(net (code "1") (name "GND") (class "Default") (node (ref "R1") (pin "1")))')
    assert node.pairs() == {"code": "1", "name": "GND", "class": "Default"}


def test_a_nested_field_wins_over_a_flat_one():
    node = parse('(net "name" "flat" (name "nested") "code" "7")')
    assert node.pairs() == {"name": "nested", "code": "7"}


def test_a_child_that_is_not_a_key_and_one_atom_is_not_a_field():
    node = parse('(comp (ref "R1" "extra") (units (unit (name "A"))) (tstamps))')
    assert node.pairs() == {}


def test_a_malformed_file_is_reported_rather_than_guessed_at():
    for bad, message in (
        ("(unclosed", "ends inside a list"),
        (")", "no list to close"),
        ('(a "unterminated', "unterminated string"),
        ("", "empty"),
        ("(a) (b)", "more than one top-level"),
        ("atom", "top level is an atom"),
    ):
        with pytest.raises(SExprError) as caught:
            parse(bad)
        assert message in str(caught.value)


def test_tokenizing_separates_parentheses_from_atoms():
    assert tokenize('(a "b c")') == ["(", "a", '"b c"', ")"]


def test_a_missing_child_reads_as_none_rather_than_raising():
    node = parse("(comp)")
    assert node.child("ref") is None
    assert node.value("ref") is None
