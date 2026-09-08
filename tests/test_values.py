"""Spec: Value Status and Explicit Unknowns; Conflicting Values Are Preserved."""

import pytest

from fang.units import Quantity
from fang.values import Candidate, ConflictingValue, Value, ValueStatus


def test_unknown_is_explicitly_representable_and_carries_no_quantity():
    unknown = Value.unknown()
    assert unknown.status is ValueStatus.UNKNOWN
    assert unknown.quantity is None
    assert unknown.as_dict() == {"status": "unknown"}
    assert not unknown.known


def test_null_is_never_used_to_mean_unknown():
    # A value that does not apply is absent; one that is not known is present
    # with status unknown. There is no third spelling.
    with pytest.raises(ValueError):
        Value(ValueStatus.UNKNOWN, Quantity.scalar("1", "V"))


def test_an_inferred_value_carries_its_source_and_confidence():
    with pytest.raises(ValueError):
        Value(ValueStatus.INFERRED, Quantity.scalar("0.25", "W"))
    inferred = Value.inferred(Quantity.scalar("0.25", "W"), "EVD-1", "0.82")
    assert inferred.as_dict()["confidence"] == "0.82"


def test_an_assumed_value_carries_its_rationale():
    with pytest.raises(ValueError):
        Value(ValueStatus.ASSUMED, Quantity.scalar("1", "V"))
    assert Value.assumed(Quantity.scalar("1", "V"), "working value").rationale


def test_an_inferred_or_assumed_value_is_not_treated_as_explicit():
    assert not Value.inferred(Quantity.scalar("1", "V"), "EVD-1", "0.5").is_explicit
    assert not Value.assumed(Quantity.scalar("1", "V"), "why").is_explicit
    assert Value.explicit(Quantity.scalar("1", "V")).is_explicit


def test_competing_candidates_are_not_silently_reduced_to_one_winner():
    conflict = ConflictingValue(
        (
            Candidate(Value.explicit(Quantity.scalar("10", "kOhm")), "DS-A"),
            Candidate(Value.explicit(Quantity.scalar("12", "kOhm")), "DS-B"),
        )
    )
    assert not conflict.resolved
    assert conflict.chosen is None
    assert len(conflict.as_dict()["candidates"]) == 2


def test_a_resolution_records_the_choice_and_the_decision_that_made_it():
    conflict = ConflictingValue(
        (
            Candidate(Value.explicit(Quantity.scalar("10", "kOhm")), "DS-A"),
            Candidate(Value.explicit(Quantity.scalar("12", "kOhm")), "DS-B"),
        )
    )
    resolved = conflict.resolve("DS-A", "DEC-1")
    assert resolved.resolved and resolved.decision == "DEC-1"
    assert str(resolved.chosen.quantity) == "10 kOhm"
    # Both candidates survive the resolution.
    assert len(resolved.candidates) == 2


def test_a_resolution_naming_no_candidate_is_rejected():
    conflict = ConflictingValue(
        (
            Candidate(Value.explicit(Quantity.scalar("10", "kOhm")), "DS-A"),
            Candidate(Value.explicit(Quantity.scalar("12", "kOhm")), "DS-B"),
        )
    )
    with pytest.raises(ValueError):
        conflict.resolve("DS-C", "DEC-1")
