"""Safe subprocess execution.

Rules:
- Commands are argument lists, never shell strings, so there is no injection surface.
- Only binaries explicitly allow-listed by the calling plugin manifest may run.
- Output is captured and truncated; nothing is guessed.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CommandResult:
    command: list[str]
    resolved_path: str | None = None
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    duration_ms: int = 0
    error: str | None = None
    timed_out: bool = False
    output: str = field(default="")

    @property
    def ok(self) -> bool:
        return self.error is None and not self.timed_out and self.returncode == 0


def resolve_binary(name: str) -> str | None:
    """Resolve a bare executable name on PATH. Rejects paths."""
    if not name or "/" in name or "\\" in name or ":" in name:
        return None
    return shutil.which(name)


def run_command(
    binary: str,
    args: list[str] | tuple[str, ...] = (),
    *,
    timeout: float = 10.0,
    allowed_binaries: set[str] | None = None,
    cwd: Path | None = None,
) -> CommandResult:
    """Run a whitelisted binary with a list of arguments (no shell)."""
    command = [binary, *map(str, args)]

    if allowed_binaries is not None and binary not in allowed_binaries:
        return CommandResult(
            command=command,
            error=f"Binary '{binary}' is not declared in the plugin manifest.",
        )

    for token in command:
        if "\x00" in token:
            return CommandResult(command=command, error="Null byte in command argument.")
        if len(token) > 2048:
            return CommandResult(command=command, error="Command argument too long.")

    resolved = resolve_binary(binary)
    if resolved is None:
        return CommandResult(command=command, error=f"'{binary}' was not found on PATH.")

    started = time.perf_counter()
    try:
        completed = subprocess.run(
            [resolved, *map(str, args)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
            cwd=str(cwd) if cwd else None,
        )
        duration = int((time.perf_counter() - started) * 1000)
        return CommandResult(
            command=command,
            resolved_path=resolved,
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
            duration_ms=duration,
            output=(completed.stdout or "") or (completed.stderr or ""),
        )
    except subprocess.TimeoutExpired as exc:
        duration = int((time.perf_counter() - started) * 1000)
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        return CommandResult(
            command=command,
            resolved_path=resolved,
            duration_ms=duration,
            timed_out=True,
            error=f"Timed out after {timeout:g}s.",
            stdout=stdout or "",
        )
    except OSError as exc:
        duration = int((time.perf_counter() - started) * 1000)
        return CommandResult(
            command=command,
            resolved_path=resolved,
            duration_ms=duration,
            error=f"Failed to execute: {exc}",
        )


def minimal_env() -> dict[str, str]:
    """Environment for child processes: PATH plus OS essentials, no secrets."""
    keep = ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "HOME", "USERPROFILE")
    return {key: os.environ[key] for key in keep if key in os.environ}
