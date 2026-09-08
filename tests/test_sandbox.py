"""Spec: Elaboration Sandbox Enforcement."""

import os
import random
import socket
from pathlib import Path

import pytest

from fang.diagnostics import FangError
from fang.sandbox import Inputs, Sandbox, SandboxViolation, hash_file


@pytest.fixture
def datasheet(tmp_path):
    path = tmp_path / "TPS62130.txt"
    path.write_text("Absolute maximum VIN is 17 V")
    return path


def test_a_network_call_during_elaboration_fails(datasheet):
    with Sandbox(Inputs.declare({"DS": datasheet})):
        with pytest.raises(SandboxViolation, match="no network access"):
            socket.socket()
        with pytest.raises(SandboxViolation):
            socket.create_connection(("example.invalid", 80))


def test_an_undeclared_file_input_is_unavailable(tmp_path, datasheet):
    other = tmp_path / "secret.txt"
    other.write_text("not declared")
    inputs = Inputs.declare({"DS": datasheet})

    with Sandbox(inputs):
        assert "17 V" in inputs.read_text("DS")
        with pytest.raises(SandboxViolation):
            open(other)
        with pytest.raises(SandboxViolation, match="was not declared"):
            inputs.read_text("MISSING")


def test_writing_outside_the_output_directory_is_refused(tmp_path, datasheet):
    with Sandbox(Inputs.declare({"DS": datasheet})):
        with pytest.raises(SandboxViolation, match="no write access"):
            open(tmp_path / "output.txt", "w")


def test_a_declared_input_is_hashed(datasheet):
    inputs = Inputs.declare({"DS": datasheet})
    declared = inputs.as_list()
    assert declared[0]["id"] == "DS"
    assert declared[0]["hash"] == hash_file(datasheet)
    assert declared[0]["hash"].startswith("sha256:")


def test_declaring_a_file_that_does_not_exist_is_refused(tmp_path):
    with pytest.raises(FangError):
        Inputs.declare({"DS": tmp_path / "absent.txt"})


def test_randomness_without_a_declared_seed_is_refused():
    with Sandbox():
        with pytest.raises(SandboxViolation, match="declared seed"):
            random.random()


def test_a_declared_seed_makes_randomness_reproducible():
    with Sandbox(seed=42):
        first = [random.random() for _ in range(3)]
    with Sandbox(seed=42):
        second = [random.random() for _ in range(3)]
    generator = random.Random(42)
    assert first == second == [generator.random() for _ in range(3)]


def test_the_sandbox_restores_everything_on_exit():
    import builtins

    real_open, real_socket, real_random = builtins.open, socket.socket, random.random
    with Sandbox():
        assert builtins.open is not real_open
    assert builtins.open is real_open
    assert socket.socket is real_socket
    assert random.random is real_random


def test_the_sandbox_restores_everything_even_when_elaboration_raises():
    import builtins

    real_open = builtins.open
    with pytest.raises(RuntimeError):
        with Sandbox():
            raise RuntimeError("elaboration blew up")
    assert builtins.open is real_open


def test_imports_still_work_inside_the_sandbox():
    """The interpreter carve-out is narrow but it must actually work."""
    with Sandbox():
        import json  # noqa: F401
        import xml.etree.ElementTree  # noqa: F401


def test_the_sandbox_records_what_it_declared(datasheet):
    sandbox = Sandbox(Inputs.declare({"DS": datasheet}), seed=7)
    recorded = sandbox.as_dict()
    assert recorded["seed"] == 7
    assert recorded["inputs"][0]["id"] == "DS"
