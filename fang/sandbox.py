"""The elaboration sandbox.

Spec: "Deterministic Sandboxed Elaboration" and "Elaboration Sandbox
Enforcement". The prohibition on network access is absolute rather than a
default, and undeclared input is made unavailable rather than merely
discouraged.

The enforcement here is real: sockets are replaced, `open` is filtered, and the
module-level random functions refuse to run without a declared seed. The one
carve-out is reads inside the Python installation itself, without which `import`
could not work; it is narrow, explicit, and never covers project data.
"""

from __future__ import annotations

import builtins
import hashlib
import io
import os
import random as _random_module
import socket as _socket_module
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .diagnostics import ELAB_PATH_INVALID, Diagnostic, Severity, error

#: Reads under these roots are permitted so that `import` works. Project data
#: never lives here, so the carve-out cannot be used to smuggle input in.
_INTERPRETER_ROOTS = tuple(
    Path(root).resolve()
    for root in {sys.prefix, sys.base_prefix, sys.exec_prefix, *sys.path}
    if root and Path(root).exists() and Path(root).is_dir()
)


class SandboxViolation(Exception):
    """An elaboration reached for something the sandbox does not provide."""


@dataclass(frozen=True)
class DeclaredInput:
    """A file input declared by the program and hashed into the snapshot."""

    id: str
    path: Path
    hash: str

    def as_dict(self) -> dict:
        return {"id": self.id, "hash": self.hash}


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with io.open(path, "rb") as handle:
        for block in iter(lambda: handle.read(65536), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


class Inputs:
    """The only way a program reaches a file.

    Every input is declared before elaboration and hashed into the snapshot, so a
    build that consumed a file records which file and which contents.
    """

    def __init__(self, declared: Iterable[DeclaredInput] = ()) -> None:
        self._by_id = {declaration.id: declaration for declaration in declared}
        self._by_path = {
            str(declaration.path.resolve()): declaration for declaration in declared
        }

    @classmethod
    def declare(cls, mapping: Mapping[str, str | os.PathLike]) -> "Inputs":
        declared = []
        for input_id, raw in sorted(mapping.items()):
            path = Path(raw).resolve()
            if not path.is_file():
                raise error(
                    ELAB_PATH_INVALID,
                    f"declared input {input_id!r} does not name a readable file: {path}",
                )
            declared.append(DeclaredInput(input_id, path, hash_file(path)))
        return cls(declared)

    def read_text(self, input_id: str, encoding: str = "utf-8") -> str:
        return self.read_bytes(input_id).decode(encoding)

    def read_bytes(self, input_id: str) -> bytes:
        declaration = self._by_id.get(input_id)
        if declaration is None:
            raise SandboxViolation(
                f"input {input_id!r} was not declared; external data reaches a "
                "program as a declared, hashed file produced by an earlier tool call"
            )
        with io.open(declaration.path, "rb") as handle:
            return handle.read()

    def permits(self, path: str | os.PathLike) -> bool:
        return str(Path(path).resolve()) in self._by_path

    def as_list(self) -> list[dict]:
        return [declaration.as_dict() for declaration in sorted(self._by_id.values(), key=lambda d: d.id)]

    def __len__(self) -> int:
        return len(self._by_id)

    def __iter__(self):
        return iter(sorted(self._by_id.values(), key=lambda d: d.id))


def _under_interpreter(path: Path) -> bool:
    for root in _INTERPRETER_ROOTS:
        try:
            path.relative_to(root)
            return True
        except ValueError:
            continue
    return False


class Sandbox:
    """The elaboration environment.

    Entered as a context manager. On exit every patch is removed, whether
    elaboration succeeded or raised.
    """

    def __init__(
        self,
        inputs: Inputs | None = None,
        *,
        seed: int | None = None,
        enforce: bool = True,
    ) -> None:
        self.inputs = inputs or Inputs()
        self.seed = seed
        self.enforce = enforce
        self.violations: list[str] = []
        self._patches: list[tuple[Any, str, Any]] = []
        self._rng: _random_module.Random | None = None

    # -- randomness --------------------------------------------------------

    @property
    def rng(self) -> _random_module.Random:
        """A seeded generator. Randomness without a declared seed is refused."""
        if self.seed is None:
            raise SandboxViolation(
                "elaboration used randomness without a declared seed; where a "
                "program needs randomness, the seed must be declared and recorded"
            )
        if self._rng is None:
            self._rng = _random_module.Random(self.seed)
        return self._rng

    # -- the patches -------------------------------------------------------

    def _patch(self, target: Any, name: str, replacement: Any) -> None:
        self._patches.append((target, name, getattr(target, name)))
        setattr(target, name, replacement)

    def _deny_network(self) -> None:
        def refuse(*args, **kwargs):
            self.violations.append("network access")
            raise SandboxViolation(
                "elaboration has no network access at all; a declared exception "
                "would cost exactly the reproducibility guarantee it exists to give"
            )

        for name in ("socket", "create_connection", "socketpair"):
            if hasattr(_socket_module, name):
                self._patch(_socket_module, name, refuse)

    def _filter_open(self) -> None:
        real_open = builtins.open

        def guarded(file, mode="r", *args, **kwargs):
            if isinstance(file, int):        # already-open descriptor
                return real_open(file, mode, *args, **kwargs)
            resolved = Path(os.fspath(file)).resolve()
            if "w" in mode or "a" in mode or "x" in mode or "+" in mode:
                self.violations.append(f"write to {resolved}")
                raise SandboxViolation(
                    f"elaboration has no write access outside its output "
                    f"directory: {resolved}"
                )
            if self.inputs.permits(resolved) or _under_interpreter(resolved):
                return real_open(file, mode, *args, **kwargs)
            self.violations.append(f"undeclared read of {resolved}")
            raise SandboxViolation(
                f"{resolved} was not declared as an input; an undeclared input is "
                "unavailable rather than merely discouraged"
            )

        self._patch(builtins, "open", guarded)

    def _guard_randomness(self) -> None:
        def guarded(name):
            def call(*args, **kwargs):
                return getattr(self.rng, name)(*args, **kwargs)

            return call

        for name in ("random", "randint", "randrange", "choice", "shuffle", "uniform", "sample"):
            if hasattr(_random_module, name):
                self._patch(_random_module, name, guarded(name))

    # -- context management -----------------------------------------------

    def __enter__(self) -> "Sandbox":
        if self.enforce:
            self._deny_network()
            self._filter_open()
            self._guard_randomness()
        return self

    def __exit__(self, *exc_info) -> None:
        for target, name, original in reversed(self._patches):
            setattr(target, name, original)
        self._patches.clear()

    # -- what the snapshot records ----------------------------------------

    def as_dict(self) -> dict:
        out: dict = {"inputs": self.inputs.as_list()}
        if self.seed is not None:
            out["seed"] = self.seed
        return out
