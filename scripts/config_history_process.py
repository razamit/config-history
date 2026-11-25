"""Process helpers for the config-history plugin bootstrap.

Stdlib only and compatible with Python 3.9. The bootstrap depends on the small
runner and spawner interfaces here, so tests can pass fakes that never start a
real process.
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Mapping, Optional, Sequence

from config_history_state import PROGRAM_NAME

# Environment variables that would point a child Python at the wrong packages.
_PYTHON_PATH_VARIABLES = ("PYTHONPATH", "PYTHONHOME")


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0


def tool_environment(env: Mapping[str, str]) -> dict:
    """Environment for running the tool or the installer's child processes."""
    child_env = {key: value for key, value in env.items() if key not in _PYTHON_PATH_VARIABLES}
    child_env["CLAUDE_CFG_PROGRAM_NAME"] = PROGRAM_NAME
    return child_env


def session_hook_command(venv_python: str, hook_event: str) -> list:
    """Command that runs the tool's session hook isolated from the working directory."""
    return [venv_python, "-I", "-m", "claude_cfg", "session-hook", hook_event]


class SubprocessRunner:
    """Runs a command to completion and captures its output."""

    def run(
        self,
        args: Sequence[str],
        env: Mapping[str, str],
        timeout: float,
        cwd: Optional[str] = None,
    ) -> CommandResult:
        try:
            completed = subprocess.run(
                list(args),
                env=dict(env),
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return CommandResult(124, "", "timed out after {} seconds".format(timeout))
        except OSError as error:
            return CommandResult(127, "", str(error))
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)


class DetachedSpawner:
    """Starts a command in its own session so it outlives the hook."""

    def spawn(self, args: Sequence[str], env: Mapping[str, str], log_file: str, cwd: str) -> None:
        os.makedirs(os.path.dirname(log_file), mode=0o700, exist_ok=True)
        descriptor = os.open(log_file, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as log_handle:
            subprocess.Popen(
                list(args),
                env=dict(env),
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                close_fds=True,
                **_detach_options(),
            )


def _detach_options() -> dict:
    if os.name == "nt":
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
        return {"creationflags": flags}
    return {"start_new_session": True}
