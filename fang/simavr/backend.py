"""simavr, reached across a process boundary.

Spec: "Backends Are Reached Across A Process Boundary", "The Emulator Is
Reported, Never Substituted" and "Emulation Runs Are Deterministic And
Identified".

simavr is found by its `simavr` executable, and its headers and library are
read from the installation beside it, which `make install` and the
distributions' packages both lay out as one prefix. Its version is the one the
installed headers were generated with, and its build is the digest of the
library a runner links against, so two builds of one tag are told apart.

A run copies the bundle into a temporary directory, builds the runner there
from the source the bundle carries, against that installation, and runs it
without a shell, in a process group of its own, under a wall-clock limit that
ends every process the run started, as Renode's runs are. A missing compiler,
headers or library, or a runner that does not build, is reported unsupported
with the compiler's message before anything runs, never as a crashed run.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from ..renode.backend import _kill_group, _new_group
from .lowering import CONFIG, EVENTS, LOG, REFUSED_VERSIONS, RUNNER, SUPPORTED_VERSIONS

#: Where a library may be under a prefix: lib, lib64, or a multiarch folder.
_LIBRARY_NAMES = ("libsimavr.so", "libsimavr.dylib", "libsimavr.a")
_VERSION = re.compile(r'#define\s+CONFIG_SIMAVR_VERSION\s+"v?([^"]+)"')


class SimavrUnavailable(Exception):
    """simavr is missing, a version the lowering was not checked against, or
    an installation the runner cannot be built against."""


@dataclass(frozen=True)
class Installation:
    """One simavr installation: the prefix, its headers and its library."""

    prefix: Path
    include: Path
    library: Path

    @property
    def shared(self) -> bool:
        return self.library.suffix in (".so", ".dylib")


@dataclass(frozen=True)
class SimavrRun:
    """What one run left behind."""

    version: str
    build: str
    exit_status: int | None
    outcome: str                      # completed, halted, timeout, crashed
    events: bytes
    log: str
    arguments: tuple[str, ...]
    compiler: str = ""
    files: Mapping[str, bytes] = field(default_factory=dict)


@dataclass
class SimavrBackend:
    name: str = "simavr"
    executable: str = "simavr"

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def installation(self) -> Installation:
        """The installation the `simavr` executable belongs to."""
        found = shutil.which(self.executable)
        if found is None:
            raise SimavrUnavailable(f"{self.executable} is not installed")
        prefix = Path(found).resolve().parent.parent
        include = prefix / "include" / "simavr"
        if not (include / "sim_avr.h").is_file():
            raise SimavrUnavailable(
                f"simavr is installed at {prefix} without its headers ({include}/sim_avr.h), "
                "which fang builds its runner against; install them with simavr's "
                "`make install`, or a package of its development files"
            )
        folders = [prefix / "lib", prefix / "lib64"] + sorted((prefix / "lib").glob("*-*-*"))
        for folder in folders:
            for name in _LIBRARY_NAMES:
                if (folder / name).exists():
                    # As found, not resolved: libsimavr.so is a link to
                    # libsimavr.so.1, and the name says it is shared.
                    return Installation(prefix, include, folder / name)
        raise SimavrUnavailable(
            f"simavr is installed at {prefix} without its library (libsimavr under lib), "
            "which fang builds its runner against"
        )

    def identify(self) -> tuple[str, str]:
        """The version the installed headers were made with, and the build:
        the first twelve hex digits of the library's SHA-256."""
        installation = self.installation()
        config = installation.include / "sim_core_config.h"
        found = _VERSION.search(config.read_text(encoding="utf-8", errors="replace")) if config.is_file() else None
        if found is None:
            raise SimavrUnavailable(f"simavr at {installation.prefix} does not say its version in {config}")
        build = hashlib.sha256(installation.library.read_bytes()).hexdigest()[:12]
        return found.group(1), build

    def version(self) -> str:
        return self.identify()[0]

    def check(self) -> tuple[str, str]:
        """The version and build, refusing one the lowering was not checked
        against: by its known fault, where it has one."""
        version, build = self.identify()
        checked = ", ".join(sorted(SUPPORTED_VERSIONS))
        if version in REFUSED_VERSIONS:
            raise SimavrUnavailable(
                f"simavr {version} is installed, and the lowering was checked against {checked}: "
                f"{version} is refused because {REFUSED_VERSIONS[version]}"
            )
        if version not in SUPPORTED_VERSIONS:
            raise SimavrUnavailable(
                f"simavr {version} is installed, and the lowering was checked against {checked}; "
                "the run reports unsupported rather than trust a model whose behaviour may "
                "have moved"
            )
        return version, build

    def compiler(self) -> tuple[str, str]:
        """The C compiler a runner is built with, `$CC` or `cc`, and the first
        line it reports itself as."""
        named = os.environ.get("CC") or "cc"
        found = shutil.which(named)
        if found is None:
            raise SimavrUnavailable(
                f"no C compiler ({named}) is on the path to build the runner against simavr"
            )
        reported = subprocess.run(
            [found, "--version"], capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL
        )
        first = next((line.strip() for line in reported.stdout.splitlines() if line.strip()), named)
        return found, first

    def build(self, workspace: Path, installation: Installation, compiler: str) -> None:
        """Build the runner in `workspace`, refusing as unsupported a build
        that fails, with the compiler's message. A static library carries
        simavr's ELF loader, so it needs libelf beside it."""
        base = [compiler, "-std=gnu99", "-O2", "-I", str(installation.include), "-o", "fang-runner", RUNNER]
        if installation.shared:
            folder = str(installation.library.parent)
            attempts = [base + ["-L", folder, "-lsimavr", f"-Wl,-rpath,{folder}", "-lm"]]
        else:
            attempts = [base + [str(installation.library), "-lm", elf] for elf in ("-lelf", "-l:libelf.so.1")]
        message = ""
        for arguments in attempts:
            built = subprocess.run(
                arguments, cwd=workspace, capture_output=True, text=True, timeout=300,
                stdin=subprocess.DEVNULL,
            )
            if built.returncode == 0:
                return
            message = (built.stderr or built.stdout).strip()
        lines = message.splitlines()
        raise SimavrUnavailable(
            f"the runner did not build against simavr at {installation.prefix}: "
            + " / ".join(lines[-3:] if lines else ["the compiler gave no message"])
        )

    def run(self, files: Mapping[str, bytes], *, timeout: float = 120) -> SimavrRun:
        version, build = self.check()
        installation = self.installation()
        compiler, reported = self.compiler()
        with tempfile.TemporaryDirectory(prefix="fang-simavr-") as scratch:
            workspace = Path(scratch)
            for name, content in files.items():
                target = workspace / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            self.build(workspace, installation, compiler)
            arguments = ("./fang-runner", CONFIG)
            log_path = workspace / LOG
            with open(log_path, "wb") as log:
                process = subprocess.Popen(
                    arguments,
                    cwd=workspace,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    **_new_group(),
                )
                try:
                    exit_status: int | None = process.wait(timeout=timeout)
                    outcome = "completed"
                except subprocess.TimeoutExpired:
                    _kill_group(process)
                    exit_status = None
                    outcome = "timeout"
            events_path = workspace / EVENTS
            events = events_path.read_bytes() if events_path.exists() else b""
            if outcome == "completed":
                outcome = _ending(events) if exit_status == 0 else "crashed"
            return SimavrRun(
                version=version,
                build=build,
                exit_status=exit_status,
                outcome=outcome,
                events=events,
                log=log_path.read_text(encoding="utf-8", errors="replace"),
                arguments=arguments,
                compiler=reported,
            )


def _ending(events: bytes) -> str:
    """How a run that exited cleanly ended, from its run.end: completed at its
    bound, or halted before it; one with no run.end crashed."""
    last = events.rstrip(b"\n").rsplit(b"\n", 1)[-1]
    if b'"type":"run.end"' not in last:
        return "crashed"
    return "completed" if b'"reason":"completed"' in last else "halted"
