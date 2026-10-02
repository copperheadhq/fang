"""Renode, reached across a process boundary.

Spec: "Backends Are Reached Across A Process Boundary", "The Emulator Is
Reported, Never Substituted" and "Security And Trust Boundaries".

The bundle is copied into a temporary directory and Renode runs there, without
a shell, in a process group of its own, so that a wall-clock limit ends every
process the run started: the group, on a POSIX system, and on Windows the
process tree, which `taskkill /T` ends. Whatever events were recorded before the end are
kept. The isolation is only this — temporary copies, a time limit and a
recorded invocation — and the outcome says the run was local; network and
resource limits belong to a hosted runner.
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from .lowering import EVENTS, SCRIPT, SUPPORTED_VERSIONS


class RenodeUnavailable(Exception):
    """Renode is missing, or is a version the lowering was not checked against."""


@dataclass(frozen=True)
class RenodeRun:
    """What one run left behind."""

    version: str
    build: str
    exit_status: int | None
    outcome: str                      # completed, timeout, crashed
    events: bytes
    log: str
    arguments: tuple[str, ...]
    files: Mapping[str, bytes] = field(default_factory=dict)


@dataclass
class RenodeBackend:
    name: str = "renode"
    executable: str = "renode"

    def available(self) -> bool:
        return shutil.which(self.executable) is not None

    def identify(self) -> tuple[str, str]:
        """The version Renode reports, and its full build line."""
        if not self.available():
            raise RenodeUnavailable(f"{self.executable} is not installed")
        completed = subprocess.run(
            [self.executable, "--version"],
            capture_output=True,
            text=True,
            timeout=60,
            stdin=subprocess.DEVNULL,
        )
        lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
        version = ""
        build = ""
        for line in lines:
            if line.startswith("Renode v"):
                version = line.removeprefix("Renode v").strip()
            elif line.startswith("build:"):
                build = line.removeprefix("build:").strip()
        if not version:
            raise RenodeUnavailable(
                f"{self.executable} did not report a version: {completed.stdout!r}"
            )
        return version, build

    def version(self) -> str:
        return self.identify()[0]

    def check(self) -> tuple[str, str]:
        """The version and build, refusing one the lowering was not checked against."""
        version, build = self.identify()
        if version not in SUPPORTED_VERSIONS:
            raise RenodeUnavailable(
                f"Renode {version} is installed, and the lowering was checked against "
                f"{', '.join(sorted(SUPPORTED_VERSIONS))}; the run reports unsupported "
                "rather than giving it a script whose meaning may have moved"
            )
        return version, build

    def run(self, files: Mapping[str, bytes], *, timeout: float = 120) -> RenodeRun:
        version, build = self.check()
        _check_scratch(tempfile.gettempdir())
        with tempfile.TemporaryDirectory(prefix="fang-renode-") as scratch:
            workspace = Path(scratch)
            for name, content in files.items():
                target = workspace / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            arguments = (self.executable, "--console", "--disable-gui", "-p", SCRIPT)
            log_path = workspace / "renode.log"
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
            if outcome == "completed" and (exit_status != 0 or b'"type":"run.end"' not in events):
                outcome = "crashed"
            return RenodeRun(
                version=version,
                build=build,
                exit_status=exit_status,
                outcome=outcome,
                events=events,
                log=log_path.read_text(encoding="utf-8", errors="replace"),
                arguments=arguments,
            )


def _check_scratch(root: str) -> None:
    """Refuse a temporary directory Renode cannot run from.

    Renode's launcher includes the script as `i $CWD/run.resc`, and its
    monitor splits a path at whitespace, so from a directory whose path has a
    space in it the include fails and the run ends with no events. That is
    reported by name before anything starts, rather than as a crash.
    """
    if any(c.isspace() for c in root):
        raise RenodeUnavailable(
            f"renode cannot run from the temporary directory {root!r}: its monitor "
            "splits a path at a space, so the run's script cannot be included; set "
            "TMPDIR (TEMP on Windows) to a directory whose path has no space"
        )


def _new_group() -> dict:
    """Popen options that start a run in a group of its own.

    Windows has no process groups to signal, and ignores `start_new_session`;
    a new process group there is what keeps the run from sharing the console's.
    """
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def _kill_group(process: subprocess.Popen) -> None:
    """End the run and every process it started."""
    if os.name == "nt":
        # /T ends the tree the process heads, /F without asking it first.
        # Should taskkill not reach it, the run itself is still ended.
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            capture_output=True,
            check=False,
        )
        if process.poll() is None:
            process.kill()
    else:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait()
